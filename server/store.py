"""JSON 오브젝트 저장소 — GCS(REPORTS_BUCKET) 또는 로컬 .tmp 폴백.

런타임 DB는 읽기 전용이므로 로그인/서재 같은 쓰기 데이터는 GCS에 저장한다.
(푸시 구독과 동일한 패턴)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_LOCAL = Path(__file__).resolve().parent.parent / ".tmp" / "store"


def _bucket():
    name = os.getenv("REPORTS_BUCKET")
    if not name:
        raise RuntimeError("REPORTS_BUCKET not set")
    from google.cloud import storage  # 지연 임포트

    return storage.Client().bucket(name)


def _local_path(path: str) -> Path:
    p = _LOCAL / path
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def read_json(path: str) -> dict | None:
    try:
        raw = _bucket().blob(path).download_as_bytes(timeout=8)
        return json.loads(raw.decode("utf-8"))
    except Exception:
        pass
    try:
        return json.loads(_local_path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def write_json(path: str, obj) -> bool:
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    ok = False
    try:
        _bucket().blob(path).upload_from_string(body, content_type="application/json", timeout=10)
        ok = True
    except Exception:
        pass
    try:
        _local_path(path).write_bytes(body)
        ok = True
    except Exception:
        pass
    return ok


def delete(path: str) -> None:
    try:
        _bucket().blob(path).delete()
    except Exception:
        pass
    try:
        _local_path(path).unlink(missing_ok=True)
    except Exception:
        pass


def list_prefix(prefix: str, limit: int = 500) -> list[str]:
    names: list[str] = []
    try:
        for blob in _bucket().list_blobs(prefix=prefix, max_results=limit):
            names.append(blob.name)
        return names
    except Exception:
        pass
    try:
        for p in _LOCAL.glob(prefix + "*"):
            names.append(str(p.relative_to(_LOCAL)))
    except Exception:
        pass
    return names[:limit]
