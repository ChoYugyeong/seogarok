"""익명 1st-party 이벤트 수집·집계 (KPI).

- 개인정보 없음: 세션 랜덤 ID + 이벤트명/속성만, IP는 해시로만 보관(선택)
- 저장: GCS `analytics/events/{YYYY-MM-DD}/{ts}-{rand}.json` (로컬/.tmp 폴백)
- 집계: /api/kpi?days=N (cron secret 인증)
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import time
from collections import Counter, defaultdict

EVENTS_PREFIX = "analytics/events/"
MAX_BATCH = 20
MAX_PROPS = 20
MAX_STR = 200

ALLOWED = {
    "view",
    "search",
    "search_zero",
    "result_click",
    "drawer_open",
    "outbound_click",
    "collection_open",
    "genre_click",
    "rank_kind",
    "rank_cat",
    "alert_toggle",
    "alert_enable",
    "alert_lead",
    "push_opened",
    "share",
    "report",
}


def _gcs_bucket():
    name = os.getenv("REPORTS_BUCKET")
    if not name:
        raise RuntimeError("REPORTS_BUCKET not set")
    from google.cloud import storage

    return storage.Client().bucket(name)


def _local_dir(sub: str = "") -> str:
    base = os.getenv("ANALYTICS_DIR") or os.path.join(os.getcwd(), ".analytics-cache")
    path = os.path.join(base, sub) if sub else base
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".w")
        with open(probe, "w") as f:
            f.write("1")
        os.remove(probe)
        return path
    except Exception:
        alt = os.path.join("/tmp/seogarok-analytics", sub) if sub else "/tmp/seogarok-analytics"
        os.makedirs(alt, exist_ok=True)
        return alt


KST_OFFSET = 9 * 3600


def _today() -> str:
    # 한국 사용자 기준 날짜 버킷 (KST)
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() + KST_OFFSET))


def _clean_events(raw) -> list[dict]:
    out = []
    for item in (raw or [])[:MAX_BATCH]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name not in ALLOWED:
            continue
        props_in = item.get("props") or {}
        props = {}
        if isinstance(props_in, dict):
            for k, v in list(props_in.items())[:MAX_PROPS]:
                key = str(k)[:40]
                if isinstance(v, (int, float, bool)):
                    props[key] = v
                else:
                    props[key] = str(v)[:MAX_STR]
        out.append({"name": name, "props": props, "ts": int(item.get("ts") or time.time() * 1000)})
    return out


def record_events(payload: dict, ip_hash: str = "", ua: str = "") -> int:
    events = _clean_events(payload.get("events"))
    if not events:
        return 0
    session = str(payload.get("session") or "")[:48]
    record = {
        "received_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "session": session,
        "ip_hash": ip_hash,
        "ua": ua[:120],
        "events": events,
    }
    body = json.dumps(record, ensure_ascii=False).encode("utf-8")
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    name = f"{stamp}-{random.randint(1000, 9999)}.json"
    path = f"{EVENTS_PREFIX}{_today()}/{name}"
    try:
        _gcs_bucket().blob(path).upload_from_string(body, content_type="application/json", timeout=10)
        return len(events)
    except Exception:
        pass
    try:
        day_dir = _local_dir(os.path.join(EVENTS_PREFIX.strip("/"), _today()))
        with open(os.path.join(day_dir, name), "wb") as f:
            f.write(body)
        return len(events)
    except Exception:
        return 0


def _read_day(date: str, cap: int = 5000) -> list[dict]:
    records = []
    prefix = f"{EVENTS_PREFIX}{date}/"
    try:
        blobs = list(_gcs_bucket().list_blobs(prefix=prefix, max_results=cap))
        for blob in blobs:
            try:
                records.append(json.loads(blob.download_as_bytes(timeout=8).decode("utf-8")))
            except Exception:
                continue
        if records:
            return records
    except Exception:
        pass
    try:
        d = _local_dir(EVENTS_PREFIX.strip("/"))
        d = os.path.join(d, date)
        for name in sorted(os.listdir(d))[:cap]:
            try:
                with open(os.path.join(d, name), encoding="utf-8") as f:
                    records.append(json.load(f))
            except Exception:
                continue
    except Exception:
        pass
    return records


def _dates(days: int) -> list[str]:
    now = time.time() + KST_OFFSET
    return [time.strftime("%Y-%m-%d", time.gmtime(now - i * 86400)) for i in range(days - 1, -1, -1)]


def summarize(days: int = 7, top: int = 10) -> dict:
    days = max(1, min(int(days or 7), 90))
    dates = _dates(days)
    counts = Counter()
    sessions = set()
    daily = defaultdict(lambda: {"sessions": 0, "views": 0, "searches": 0, "clicks": 0, "drawer": 0, "outbound": 0, "alerts": 0})
    queries = Counter()
    books = Counter()
    sources = Counter()
    search_with_result = 0
    search_total = 0
    sessions_with_search = set()
    sessions_with_click = set()
    sessions_with_outbound = set()
    raw_events = 0

    for date in dates:
        for rec in _read_day(date):
            sid = rec.get("session") or "?"
            sessions.add(sid)
            day = daily[date]
            day["sessions_set"] = day.get("sessions_set", set())
            day["sessions_set"].add(sid)
            for ev in rec.get("events") or []:
                raw_events += 1
                name = ev.get("name")
                props = ev.get("props") or {}
                counts[name] += 1
                if name == "view":
                    day["views"] += 1
                elif name == "search":
                    day["searches"] += 1
                    search_total += 1
                    sessions_with_search.add(sid)
                    q = str(props.get("q") or "").strip()
                    if q:
                        queries[q[:40]] += 1
                    try:
                        n = int(props.get("n") or 0)
                    except (TypeError, ValueError):
                        n = 0
                    if n > 0:
                        search_with_result += 1
                elif name == "result_click":
                    day["clicks"] += 1
                    sessions_with_click.add(sid)
                    sources[str(props.get("src") or "?")] += 1
                    b = str(props.get("book") or "").strip()
                    if b:
                        books[b] += 1
                elif name == "drawer_open":
                    day["drawer"] += 1
                elif name == "outbound_click":
                    day["outbound"] += 1
                    sessions_with_outbound.add(sid)
                elif name in ("alert_enable", "alert_toggle"):
                    day["alerts"] += 1

    for date, row in daily.items():
        row["sessions"] = len(row.pop("sessions_set", set()))
    search_sessions = len(sessions_with_search)
    return {
        "period_days": days,
        "dates": dates,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "raw_events": raw_events,
        "sessions": len(sessions),
        "counts": dict(counts),
        "funnel": {
            "search_sessions": search_sessions,
            "result_click_sessions": len(sessions_with_click),
            "outbound_sessions": len(sessions_with_outbound),
            "search_to_click_rate": round(len(sessions_with_click) / search_sessions, 3) if search_sessions else 0.0,
            "click_to_outbound_rate": round(len(sessions_with_outbound) / len(sessions_with_click), 3) if sessions_with_click else 0.0,
        },
        "search": {
            "total": search_total,
            "with_results": search_with_result,
            "zero_result": search_total - search_with_result,
            "success_rate": round(search_with_result / search_total, 3) if search_total else 0.0,
        },
        "ctr_by_source": {k: v for k, v in sources.most_common(top)},
        "top_queries": [{"q": q, "n": n} for q, n in queries.most_common(top)],
        "top_books": [{"book": b, "n": n} for b, n in books.most_common(top)],
        "daily": daily,
    }
