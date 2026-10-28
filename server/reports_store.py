"""제보 영속화: GCS 버킷에 제보 원본을 JSON 오브젝트로 저장.

Cloud Run 컨테이너 FS 는 인메모리라 재시작 시 사라진다.
REPORTS_BUCKET 환경변수가 있으면 GCS 로, 없으면 /tmp 폴백.
"""
from __future__ import annotations

import json
import os
import time

_client = None
_bucket = None


def _gcs():
    global _client, _bucket
    if _bucket is not None:
        return _bucket
    name = os.getenv("REPORTS_BUCKET")
    if not name:
        raise RuntimeError("REPORTS_BUCKET not set")
    from google.cloud import storage  # 지연 임포트 (미설치 환경 대비)

    if _client is None:
        _client = storage.Client()
    _bucket = _client.bucket(name)
    return _bucket


def persist_report(record: dict) -> str:
    """제보 1건을 GCS 에 저장. 저장 경로를 반환."""
    ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    day = time.strftime("%Y/%m/%d", time.gmtime())
    path = f"reports/{day}/{ts}-{record.get('platform', 'x')}-{abs(hash(record.get('book_id', ''))) % 10**8}.json"
    body = json.dumps(record, ensure_ascii=False).encode("utf-8")
    try:
        bucket = _gcs()
        blob = bucket.blob(path)
        blob.upload_from_string(body, content_type="application/json")
        return f"gs://{bucket.name}/{path}"
    except Exception:
        # GCS 미구성/권한 없음 → /tmp (인스턴스 수명 동안만 유지)
        with open("/tmp/seogarok_reports.jsonl", "a", encoding="utf-8") as f:
            f.write(body.decode("utf-8") + "\n")
        return "/tmp/seogarok_reports.jsonl"
