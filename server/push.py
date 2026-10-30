"""웹푸시 종료 알림 — VAPID 키·구독 저장(GCS)·다이제스트 계산·발송.

- 키/구독은 GCS(REPORTS_BUCKET) 또는 로컬/.tmp 폴백에 JSON으로 저장
- 발송은 pywebpush(런타임 의존성) 사용, 미설치/실패 시 조용히 스킵
- 다이제스트: 구독자가 저장한 책(watches) 중 종료 공지가 N일 이내인 것
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from datetime import date

VAPID_PATH = "push/vapid.json"
SUB_PREFIX = "push/subs/"
USER_PREFIX = "push/users/"
SUB_LABEL = {"millie": "밀리", "ridiselect": "리디셀렉트", "sam": "교보 sam", "willa": "윌라"}
STATS_PATH = "push/stats.json"
DEFAULT_LEADS = [7, 3, 1, 0]


def _gcs_bucket():
    name = os.getenv("REPORTS_BUCKET")
    if not name:
        raise RuntimeError("REPORTS_BUCKET not set")
    from google.cloud import storage  # 지연 임포트

    return storage.Client().bucket(name)


def _local_dir(sub: str = "") -> str:
    base = os.getenv("PUSH_CACHE_DIR") or os.path.join(os.getcwd(), ".push-cache")
    path = os.path.join(base, sub) if sub else base
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".w")
        with open(probe, "w") as f:
            f.write("1")
        os.remove(probe)
        return path
    except Exception:
        alt = os.path.join("/tmp/seogarok-push", sub) if sub else "/tmp/seogarok-push"
        os.makedirs(alt, exist_ok=True)
        return alt


def _read_json(path: str) -> dict | None:
    raw = None
    try:
        raw = _gcs_bucket().blob(path).download_as_bytes(timeout=8)
    except Exception:
        pass
    if raw is None:
        try:
            with open(os.path.join(_local_dir(), path.replace("/", "__")), "rb") as f:
                raw = f.read()
        except Exception:
            return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def _write_json(path: str, obj) -> bool:
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    try:
        _gcs_bucket().blob(path).upload_from_string(body, content_type="application/json", timeout=10)
        return True
    except Exception:
        pass
    try:
        with open(os.path.join(_local_dir(), path.replace("/", "__")), "wb") as f:
            f.write(body)
        return True
    except Exception:
        return False


# ---------------- VAPID ----------------
def vapid_keys() -> dict | None:
    cached = _read_json(VAPID_PATH)
    if cached and cached.get("private_pem") and cached.get("public_key"):
        return cached
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
    except Exception:
        return None
    priv = ec.generate_private_key(ec.SECP256R1())
    pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    pub = priv.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    data = {
        "private_pem": pem,
        "public_key": base64.urlsafe_b64encode(pub).rstrip(b"=").decode("ascii"),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _write_json(VAPID_PATH, data)
    return data


# ---------------- 구독 ----------------
def _sub_key(endpoint: str) -> str:
    return hashlib.sha256((endpoint or "").encode("utf-8")).hexdigest()[:24]


def normalize_lead_days(value) -> list[int]:
    out = []
    for v in value or DEFAULT_LEADS:
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if 0 <= n <= 30 and n not in out:
            out.append(n)
    return sorted(out or DEFAULT_LEADS, reverse=True)


def save_subscription(record: dict) -> bool:
    endpoint = ((record.get("subscription") or {}).get("endpoint") or "").strip()
    if not endpoint:
        return False
    key = _sub_key(endpoint)
    record["key"] = key
    record["lead_days"] = normalize_lead_days(record.get("lead_days"))
    record["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return _write_json(SUB_PREFIX + key + ".json", record)


def link_user_subscription(record: dict) -> bool:
    """로그인 사용자와 푸시 구독을 연결(기기별 구독을 계정 아래 인덱싱)."""
    sub = str(record.get("user_sub") or "").strip()
    key = str(record.get("key") or "").strip()
    if not sub or not key:
        return False
    path = USER_PREFIX + sub + ".json"
    data = _read_json(path) or {"keys": []}
    keys = [k for k in (data.get("keys") or []) if k]
    if key not in keys:
        keys.append(key)
    data["keys"] = keys[-20:]
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return _write_json(path, data)


def list_user_subscriptions(sub: str) -> list[dict]:
    data = _read_json(USER_PREFIX + str(sub) + ".json") or {}
    out: list[dict] = []
    for key in data.get("keys") or []:
        rec = _read_json(SUB_PREFIX + str(key) + ".json")
        if rec:
            out.append(rec)
    return out


def delete_user_subscriptions(sub: str) -> int:
    data = _read_json(USER_PREFIX + str(sub) + ".json") or {}
    removed = 0
    for key in data.get("keys") or []:
        if delete_subscription_by_key(str(key)):
            removed += 1
    try:
        _gcs_bucket().blob(USER_PREFIX + str(sub) + ".json").delete()
    except Exception:
        pass
    try:
        os.remove(os.path.join(_local_dir(), ("push" + "__" + "users" + "__" + str(sub) + ".json")))
    except Exception:
        pass
    return removed


def delete_subscription_by_key(key: str) -> bool:
    path = SUB_PREFIX + key + ".json"
    try:
        _gcs_bucket().blob(path).delete()
        return True
    except Exception:
        pass
    try:
        os.remove(os.path.join(_local_dir(), path.replace("/", "__")))
        return True
    except Exception:
        return False


def delete_subscription(endpoint: str) -> bool:
    key = _sub_key(endpoint)
    path = SUB_PREFIX + key + ".json"
    try:
        _gcs_bucket().blob(path).delete()
        return True
    except Exception:
        pass
    try:
        os.remove(os.path.join(_local_dir(), path.replace("/", "__")))
        return True
    except Exception:
        return False


def list_subscriptions(limit: int = 5000) -> list[dict]:
    out: list[dict] = []
    try:
        bucket = _gcs_bucket()
        for blob in bucket.list_blobs(prefix=SUB_PREFIX, max_results=limit):
            try:
                out.append(json.loads(blob.download_as_bytes(timeout=8).decode("utf-8")))
            except Exception:
                continue
        if out:
            return out
    except Exception:
        pass
    # 로컬 폴백
    try:
        d = _local_dir()
        for name in os.listdir(d):
            if name.startswith(SUB_PREFIX.replace("/", "__")) and name.endswith(".json"):
                try:
                    with open(os.path.join(d, name), encoding="utf-8") as f:
                        out.append(json.load(f))
                except Exception:
                    continue
    except Exception:
        pass
    return out


# ---------------- 다이제스트 ----------------
def _days_left(ends_at: str | None) -> int | None:
    try:
        return (date.fromisoformat(str(ends_at)[:10]) - date.today()).days
    except Exception:
        return None


def build_digest(conn, sub: dict, within_days: int | None = None, exact_days: int | None = None) -> list[dict]:
    """구독자의 감시 책 중 종료 예정 공지를 뽑는다.

    within_days=None & exact_days=N 이면 정확히 N일 남은 공지만.
    """
    watches = [str(w) for w in (sub.get("watches") or []) if w]
    platforms = set(sub.get("platforms") or [])
    if not watches:
        return []
    qmarks = ",".join("?" for _ in watches)
    rows = conn.execute(
        f"SELECT n.platform, n.ends_at, b.id AS book_id, b.title "
        f"FROM notices n JOIN books b ON b.id = n.book_id "
        f"WHERE b.id IN ({qmarks}) AND n.ends_at IS NOT NULL",
        watches,
    ).fetchall()
    out = []
    for r in rows:
        d = _days_left(r["ends_at"])
        if d is None or d < 0:
            continue
        if exact_days is not None:
            if d != exact_days:
                continue
        elif within_days is not None and d > within_days:
            continue
        plat = r["platform"]
        if platforms and plat not in platforms:
            continue
        out.append({
            "book_id": r["book_id"],
            "title": r["title"],
            "platform": plat,
            "platform_label": SUB_LABEL.get(plat, plat),
            "days": d,
            "ends_at": str(r["ends_at"])[:10],
        })
    out.sort(key=lambda x: x["days"])
    return out[:3]


def message_for(messages: list[dict], lead: int | None = None) -> dict | None:
    if not messages:
        return None
    m = messages[0]
    extra = f" 외 {len(messages) - 1}권" if len(messages) > 1 else ""
    days = m["days"] if lead is None else lead
    day = "오늘" if days == 0 else f"{days}일 뒤"
    return {
        "title": f"{m['platform_label']} · 『{m['title']}』 {day} 종료",
        "lead": days,
        "body": f"지금 읽어두세요{extra}",
        "url": f"/#book={m['book_id']}",
        "messages": messages,
    }


def send_push(sub: dict, payload: dict) -> bool:
    try:
        from pywebpush import webpush
    except Exception:
        return False
    keys = vapid_keys()
    if not keys:
        return False
    try:
        # pywebpush는 PEM 문자열을 DER로 해석하므로 Vapid 객체로 변환해 전달
        from py_vapid import Vapid

        vapid_obj = Vapid.from_pem(keys["private_pem"].encode("utf-8"))
        webpush(
            subscription_info=sub["subscription"],
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=vapid_obj,
            vapid_claims={"sub": "mailto:privacy@seogarok.com"},
            ttl=86400,
            timeout=10,
        )
        return True
    except Exception as exc:
        try:
            from .api import log_event

            log_event(level="warn", msg="push_send_failed", error=str(exc)[:200])
        except Exception:
            pass
        return False


# ---------------- 통계 ----------------
def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _stats() -> dict:
    data = _read_json(STATS_PATH) or {}
    if not isinstance(data.get("days"), dict):
        data["days"] = {}
    return data


def _save_stats(data: dict) -> None:
    # 최근 120일만 유지
    days = data.get("days") or {}
    if len(days) > 120:
        for key in sorted(days)[:-120]:
            days.pop(key, None)
    _write_json(STATS_PATH, data)


def _day_bucket(data: dict) -> dict:
    return data["days"].setdefault(_today(), {"sent": 0, "subs": 0, "opens": 0})


def record_send(sent: int, subs: int) -> None:
    try:
        data = _stats()
        b = _day_bucket(data)
        b["sent"] = int(b.get("sent", 0)) + max(0, int(sent))
        b["subs"] = max(int(b.get("subs", 0)), int(subs))
        _save_stats(data)
    except Exception:
        pass


def record_open() -> None:
    try:
        data = _stats()
        b = _day_bucket(data)
        b["opens"] = int(b.get("opens", 0)) + 1
        _save_stats(data)
    except Exception:
        pass


def stats_summary(period_days: int = 7) -> dict:
    data = _stats()
    days = data.get("days") or {}
    keys = sorted(days)[-period_days:]
    sent = sum(int(days[k].get("sent", 0)) for k in keys)
    opens = sum(int(days[k].get("opens", 0)) for k in keys)
    subs = max([int(days[k].get("subs", 0)) for k in keys] or [0])
    return {
        "period_days": period_days,
        "subscribers": subs,
        "sent": sent,
        "opens": opens,
        "open_rate": round(opens / sent, 3) if sent else 0.0,
        "days": {k: days[k] for k in keys},
    }


# ---------------- 발송 ----------------
def run_cron(conn, dry: bool = False, within_days: int | None = None) -> dict:
    subs = list_subscriptions()
    sent = 0
    skipped = 0
    errors = 0
    samples = []
    today = time.strftime("%Y-%m-%d", time.gmtime())
    for sub in subs:
        leads = normalize_lead_days(sub.get("lead_days"))
        sent_log = sub.get("sent_log") if isinstance(sub.get("sent_log"), dict) else {}
        changed = False
        for lead in leads:
            mark = f"{today}:{lead}"
            if mark in sent_log:
                continue
            try:
                msgs = build_digest(conn, sub, exact_days=lead)
            except Exception:
                errors += 1
                continue
            payload = message_for(msgs, lead=lead)
            if not payload:
                continue
            samples.append({"key": sub.get("key"), "lead": lead, "title": payload["title"], "dry": dry})
            if dry:
                continue
            if send_push(sub, payload):
                sent += 1
                sent_log[mark] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                changed = True
            else:
                errors += 1
        if changed:
            # 최근 20개 로그만 유지
            if len(sent_log) > 20:
                for key in sorted(sent_log)[:-20]:
                    sent_log.pop(key, None)
            sub["sent_log"] = sent_log
            sub["last_sent_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            try:
                save_subscription(sub)
            except Exception:
                pass
        if not any(f"{today}:{lead}" in sent_log for lead in leads) and not any(
            s.get("key") == sub.get("key") for s in samples
        ):
            skipped += 1
    if not dry:
        try:
            record_send(sent, len(subs))
        except Exception:
            pass
    return {
        "subscriptions": len(subs),
        "sent": sent,
        "skipped": skipped,
        "errors": errors,
        "dry": dry,
        "samples": samples[:10],
        "leads": DEFAULT_LEADS,
    }
