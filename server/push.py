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
SUB_LABEL = {"millie": "밀리", "ridiselect": "리디셀렉트", "sam": "교보 sam", "willa": "윌라"}


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


def save_subscription(record: dict) -> bool:
    endpoint = ((record.get("subscription") or {}).get("endpoint") or "").strip()
    if not endpoint:
        return False
    key = _sub_key(endpoint)
    record["key"] = key
    record["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return _write_json(SUB_PREFIX + key + ".json", record)


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


def build_digest(conn, sub: dict, within_days: int = 3) -> list[dict]:
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
        if d is None or d < 0 or d > within_days:
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


def message_for(messages: list[dict]) -> dict | None:
    if not messages:
        return None
    m = messages[0]
    extra = f" 외 {len(messages) - 1}권" if len(messages) > 1 else ""
    day = "오늘" if m["days"] == 0 else f"{m['days']}일 뒤"
    return {
        "title": f"{m['platform_label']} · 『{m['title']}』 {day} 종료",
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
        webpush(
            subscription_info=sub["subscription"],
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=keys["private_pem"],
            vapid_claims={"sub": "mailto:hello@seogarok.com"},
            ttl=86400,
            timeout=10,
        )
        return True
    except Exception:
        return False


def run_cron(conn, dry: bool = False, within_days: int = 3) -> dict:
    subs = list_subscriptions()
    sent = 0
    skipped = 0
    errors = 0
    samples = []
    for sub in subs:
        try:
            msgs = build_digest(conn, sub, within_days=within_days)
        except Exception:
            errors += 1
            continue
        payload = message_for(msgs)
        if not payload:
            skipped += 1
            continue
        samples.append({"key": sub.get("key"), "title": payload["title"], "dry": dry})
        if dry:
            continue
        if send_push(sub, payload):
            sent += 1
            try:
                sub["last_sent_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                sub["last_sent_title"] = payload["title"]
                save_subscription(sub)
            except Exception:
                pass
        else:
            errors += 1
    return {"subscriptions": len(subs), "sent": sent, "skipped": skipped, "errors": errors, "dry": dry, "samples": samples[:10]}
