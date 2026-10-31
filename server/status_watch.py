# -*- coding: utf-8 -*-
"""절판·품절 상태 감시.

YES24 Open API는 '곧 절판' 사전 신호를 주지 않는다. 대신 구독자가 감시하는 책의
itemStatus를 매일 확인해 '판매중 → 품절/절판/판매중지/예약판매'로 바뀐 순간을 알린다.
첫 실행은 기준선만 저장하고 알림을 보내지 않는다.
"""
from __future__ import annotations

import time
from urllib.parse import quote

from . import on_demand, push, store

STATUS_PATH = "status/watch.json"
ALERT_STATUSES = {"품절", "절판", "판매중지", "예약판매"}


def _code(book_id: str) -> str:
    b = str(book_id or "")
    return b.split(":", 1)[1] if b.startswith("yes24:") else ""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def run(dry: bool = False, limit: int = 120) -> dict:
    subs = push.list_subscriptions()
    by_book: dict[str, list[dict]] = {}
    for sub in subs:
        for bid in (sub.get("watches") or []):
            bid = str(bid)
            if _code(bid):
                by_book.setdefault(bid, []).append(sub)

    prev_doc = store.read_json(STATUS_PATH) or {}
    prev = prev_doc.get("items") or {}
    current = dict(prev)
    ids = list(by_book.keys())[: max(1, min(int(limit), 300))]
    checked = failed = 0
    changes: list[dict] = []

    for bid in ids:
        detail = on_demand.fetch_detail(_code(bid))
        if not detail:
            failed += 1
            continue
        checked += 1
        status = (detail.get("item_status") or "판매중").strip()
        title = detail.get("title") or bid
        old = prev.get(bid) or {}
        old_status = old.get("status")
        current[bid] = {"status": status, "title": title, "checked_at": _now()}
        if old_status and old_status != status and status in ALERT_STATUSES:
            changes.append({
                "book_id": bid,
                "title": title,
                "old": old_status,
                "status": status,
                "url": f"/book/{quote(bid, safe='')}",
            })

    store.write_json(STATUS_PATH, {"items": current, "updated_at": _now()})

    sent = send_failed = 0
    if not dry:
        for ch in changes:
            payload = {
                "title": f"절판·품절 알림 · {ch['status']}",
                "body": f"「{ch['title']}」이 {ch['old']} → {ch['status']} 상태가 됐어요",
                "url": ch["url"],
                "tag": "status:" + ch["book_id"],
                "kind": "status",
            }
            for sub in by_book.get(ch["book_id"], []):
                ok, _err = push.send_push_result(sub, payload)
                sent += 1 if ok else 0
                send_failed += 0 if ok else 1

    return {
        "ok": True,
        "dry": dry,
        "subscriptions": len(subs),
        "watched_books": len(by_book),
        "checked": checked,
        "failed": failed,
        "changes": changes,
        "sent": sent,
        "send_failed": send_failed,
        "updated_at": _now(),
    }
