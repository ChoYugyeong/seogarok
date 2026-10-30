"""개인정보 열람/삭제 등 요청(DSR) 접수 — GCS 저장 + 운영 알림은 GitHub Actions가 담당."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time

from . import store

REQUEST_TYPES = {
    "access": "열람",
    "correct": "정정",
    "delete": "삭제",
    "stop": "처리정지",
    "other": "기타",
}
PREFIX = "privacy/requests/"
_RATE: dict = {}
_RATE_WINDOW = 3600
_RATE_MAX = 5
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,120}\.[A-Za-z]{2,}$")


def _ip_hash(handler) -> str:
    ip = (handler.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    if not ip:
        ip = (handler.client_address[0] if getattr(handler, "client_address", None) else "") or "unknown"
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def _rate_ok(ip_hash: str) -> bool:
    now = time.time()
    arr = [t for t in (_RATE.get(ip_hash) or []) if now - t < _RATE_WINDOW]
    if len(arr) >= _RATE_MAX:
        _RATE[ip_hash] = arr
        return False
    arr.append(now)
    _RATE[ip_hash] = arr[-20:]
    return True


def _new_ref() -> str:
    return "P-" + time.strftime("%Y%m%d", time.gmtime()) + "-" + secrets.token_hex(2).upper()


def handle_privacy_request(handler, method: str) -> None:
    if method != "POST":
        return handler._json({"error": "method_not_allowed"}, 405)
    iph = _ip_hash(handler)
    if not _rate_ok(iph):
        return handler._json({"error": "rate_limited", "message": "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요."}, 429)
    body = handler._read_json_body() or {}
    if str(body.get("website") or "").strip():
        return handler._json({"error": "invalid_request"}, 400)
    rtype = str(body.get("type") or "").strip()
    email = str(body.get("email") or "").strip()[:200]
    message = str(body.get("message") or "").strip()[:2000]
    if rtype not in REQUEST_TYPES:
        return handler._json({"error": "invalid_type"}, 400)
    if not EMAIL_RE.match(email):
        return handler._json({"error": "invalid_email"}, 400)
    if len(message) < 10:
        return handler._json({"error": "message_too_short"}, 400)
    ref = _new_ref()
    record = {
        "ref": ref,
        "type": rtype,
        "type_label": REQUEST_TYPES[rtype],
        "email": email,
        "message": message,
        "status": "new",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ip_hash": iph,
        "ua": (handler.headers.get("User-Agent") or "")[:120],
    }
    ok = store.write_json(PREFIX + ref + ".json", record)
    if not ok:
        return handler._json({"error": "storage_failed"}, 500)
    return handler._json(
        {
            "ok": True,
            "ref": ref,
            "message": "접수됐습니다. 처리 결과는 입력하신 이메일로 회신해 드립니다(7일 이내).",
        }
    )


def list_requests(limit: int = 200) -> list[dict]:
    out: list[dict] = []
    for name in store.list_prefix(PREFIX, limit=limit):
        if not name.endswith(".json"):
            continue
        rec = store.read_json(name)
        if rec:
            out.append(rec)
    out.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return out
