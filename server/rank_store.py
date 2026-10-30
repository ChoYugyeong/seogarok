"""랭킹 일별 스냅샷 저장/조회 (어제 대비 순위 변동 계산용).

- GCS: REPORTS_BUCKET 이 있으면 gs://{bucket}/rank/{YYYY-MM-DD}/{kind}-{cat}.json
- 로컬: RANK_CACHE_DIR(기본 .rank-cache) 디렉터리 사용
- /tmp 폴백: 컨테이너에서 GCS 실패 시
"""
from __future__ import annotations

import json
import os
import time

_MAX_LOOKBACK_DAYS = 7


def _local_dir() -> str:
    """쓰기 가능한 로컬 디렉터리. Cloud Run(/app read-only)에서는 /tmp 사용."""
    d = os.getenv("RANK_CACHE_DIR")
    if d:
        try:
            os.makedirs(d, exist_ok=True)
            return d
        except Exception:
            pass
    for cand in (os.path.join(os.getcwd(), ".rank-cache"), "/tmp/seogarok-rank"):
        try:
            os.makedirs(cand, exist_ok=True)
            probe = os.path.join(cand, ".write-test")
            with open(probe, "w") as f:
                f.write("ok")
            os.remove(probe)
            return cand
        except Exception:
            continue
    return "/tmp"


def _today_utc() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _prev_days(n: int = _MAX_LOOKBACK_DAYS):
    now = time.time()
    for i in range(1, n + 1):
        yield time.strftime("%Y-%m-%d", time.gmtime(now - i * 86400))


def _gcs_bucket():
    name = os.getenv("REPORTS_BUCKET")
    if not name:
        raise RuntimeError("REPORTS_BUCKET not set")
    from google.cloud import storage  # 지연 임포트

    return storage.Client().bucket(name)


def _object_path(date: str, kind: str, cat: str) -> str:
    safe = "".join(ch for ch in cat if ch.isalnum() or ch in "-_")
    return f"rank/{date}/{kind}-{safe}.json"


def save_snapshot(kind: str, cat: str, items: list[dict]) -> str:
    """오늘자 랭킹 스냅샷 저장. 저장 위치 반환."""
    date = _today_utc()
    body = json.dumps(
        {
            "date": date,
            "kind": kind,
            "category": cat,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "items": [
                {"rank": x.get("rank"), "id": x.get("id"), "title": x.get("title")}
                for x in items
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")

    try:
        bucket = _gcs_bucket()
        path = _object_path(date, kind, cat)
        bucket.blob(path).upload_from_string(body, content_type="application/json", timeout=10)
        return f"gs://{bucket.name}/{path}"
    except Exception:
        path = os.path.join(_local_dir(), f"{date}__{kind}__{cat}.json")
        try:
            with open(path, "wb") as f:
                f.write(body)
            return path
        except Exception:
            fallback = f"/tmp/seogarok-rank-{date}-{kind}-{cat}.json"
            try:
                with open(fallback, "wb") as f:
                    f.write(body)
            except Exception:
                return ""
            return fallback


def load_previous(kind: str, cat: str) -> dict[str, int]:
    """가장 최근(어제 이전) 스냅샷의 {id: rank} 매핑. 없으면 빈 dict."""
    for date in _prev_days():
        raw = None
        try:
            bucket = _gcs_bucket()
            raw = bucket.blob(_object_path(date, kind, cat)).download_as_bytes(timeout=10)
        except Exception:
            pass
        if raw is None:
            paths = []
            try:
                paths.append(os.path.join(_local_dir(), f"{date}__{kind}__{cat}.json"))
            except Exception:
                pass
            paths.append(f"/tmp/seogarok-rank-{date}-{kind}-{cat}.json")
            for path in paths:
                try:
                    with open(path, "rb") as f:
                        raw = f.read()
                    break
                except Exception:
                    continue
        if not raw:
            continue
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            continue
        mapping = {}
        for it in data.get("items") or []:
            if it.get("id") is not None and it.get("rank") is not None:
                mapping[str(it["id"])] = int(it["rank"])
        return mapping
    return {}


def attach_deltas(items: list[dict], kind: str, cat: str) -> list[dict]:
    """각 항목에 prev_rank / delta / is_new 부여.

    delta > 0  → 순위 상승(숫자 감소)
    delta < 0  → 순위 하락
    delta == 0 → 변동 없음
    """
    try:
        prev = load_previous(kind, cat)
    except Exception:
        prev = {}
    for it in items:
        try:
            rid = str(it.get("id"))
            before = prev.get(rid)
            if before is None:
                it["prev_rank"] = None
                it["delta"] = None
                it["is_new"] = bool(prev)  # 이전 스냅샷이 있는데 없던 책이면 NEW
            else:
                it["prev_rank"] = before
                it["delta"] = before - int(it.get("rank") or 0)
                it["is_new"] = False
        except Exception:
            it.setdefault("prev_rank", None)
            it.setdefault("delta", None)
            it.setdefault("is_new", False)
    return items



def load_latest(kind: str, cat: str) -> list[dict]:
    """가장 최근(오늘 포함) 스냅샷 items. 없으면 빈 리스트.

    YES24 API가 429/장애일 때 홈 랭킹을 스냅샷으로 계속 보여주기 위한 폴백.
    """
    dates = [time.strftime("%Y-%m-%d", time.gmtime())]
    dates += list(_prev_days())
    for date in dates:
        raw = None
        try:
            bucket = _gcs_bucket()
            raw = bucket.blob(_object_path(date, kind, cat)).download_as_bytes(timeout=10)
        except Exception:
            pass
        if raw is None:
            for path in (
                os.path.join(_local_dir(), f"{date}__{kind}__{cat}.json"),
                f"/tmp/seogarok-rank-{date}-{kind}-{cat}.json",
            ):
                try:
                    with open(path, "rb") as f:
                        raw = f.read()
                    break
                except Exception:
                    continue
        if not raw:
            continue
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            continue
        items = data.get("items") or []
        if items:
            return items
    return []
