"""가용성(어느 구독사에서 읽을 수 있는가) 조립.

⚠️ 서점 메타데이터(예스24 API)에는 "어느 구독 플랫폼이 이 책을 제공하는가" 정보가 없다.
이 정보는 플랫폼 제휴/공지 수집으로만 얻을 수 있다. 그래서 두 모드를 둔다.

  SEOG_AVAIL=simulated (데모·기본)
      - 실제 공지가 있으면 origin="notice"
      - 없으면 책 id 해시 기반 시뮬레이션 → origin="simulated"
  SEOG_AVAIL=real (운영)
      - **실수집(notice)만** 구독 가용성으로 표시
      - 나머지 구독사는 origin="unknown" → UI 는 "가용성 미확인"으로 표시 (허위 표시 금지)
      - 구매 정보(예스24 가격/링크)는 API 실데이터이므로 origin="api"
"""
from __future__ import annotations

import os
import random
import zlib

SUB_PLATFORMS = ["millie", "ridiselect", "sam", "willa"]

MODE = (os.getenv("SEOG_AVAIL", "simulated") or "simulated").strip().lower()

# 데모용 커버리지 (실제 시장 커버리지와 무관한 시뮬레이션 값)
_SUB_PROB = {"millie": 0.40, "ridiselect": 0.10, "sam": 0.44, "willa": 0.46}
_END_PROB = 0.10


def simulated_av(book: dict) -> dict:
    seed = zlib.crc32(str(book.get("id", "")).encode("utf-8"))
    rnd = random.Random(seed)
    av: dict = {}
    for p in SUB_PLATFORMS:
        if rnd.random() < _SUB_PROB[p]:
            if rnd.random() < _END_PROB:
                av[p] = {"s": "ending", "d": rnd.choice([2, 4, 6, 9, 13, 17, 21, 27])}
            else:
                av[p] = {"s": "on"}
    price = book.get("price") or 15000
    av["aladin"] = {"buy": int(price)}
    if rnd.random() < 0.35:
        av["library"] = {"wait": rnd.choice([0, 0, 1, 2, 3, 5, 7])}
    if rnd.random() < 0.08:
        av["gongu"] = {"s": "on"}
    return av


def _days_left(ends_at: str | None) -> int | None:
    if not ends_at:
        return None
    import datetime as _dt

    try:
        d = _dt.date.fromisoformat(str(ends_at)[:10])
    except ValueError:
        return None
    return (d - _dt.date.today()).days


def build_availability(book: dict, stored: list[dict], notices: list[dict]) -> tuple[dict, dict]:
    """(av, origins). av 는 data.js 와 동일한 형태."""
    if MODE == "real":
        return _real_availability(book, stored, notices)

    av = simulated_av(book)
    origins = {p: "simulated" for p in av}

    # 실제 공지가 있으면 덮어쓴다 (fixture 는 실데이터가 아니므로 제외)
    for n in notices or []:
        if (n.get("source_kind") or "") == "fixture":
            continue
        platform = n.get("platform")
        if platform not in SUB_PLATFORMS:
            continue
        d = _days_left(n.get("ends_at"))
        av[platform] = {"s": "ending", "d": d if d is not None and d >= 0 else None, "ends_at": n.get("ends_at")}
        origins[platform] = "notice"

    # DB availability 테이블(공지 기반) 우선
    for row in stored or []:
        platform = row.get("platform")
        if platform not in SUB_PLATFORMS or row.get("origin") != "notice":
            continue
        d = _days_left(row.get("ends_at"))
        av[platform] = {"s": row.get("status") or "ending", "d": d, "ends_at": row.get("ends_at")}
        origins[platform] = "notice"

    return av, origins


def _real_availability(book: dict, stored: list[dict], notices: list[dict]) -> tuple[dict, dict]:
    """운영 모드: 실수집 데이터만 사실로 표시하고 나머지는 '미확인'."""
    av: dict = {}
    origins: dict = {p: "unknown" for p in SUB_PLATFORMS}

    # 구매 정보는 YES24 Open API 실데이터
    price = book.get("price")
    if price:
        av["yes24"] = {"buy": int(price)}
        origins["yes24"] = "api"

    for n in notices or []:
        if (n.get("source_kind") or "") == "fixture":
            continue
        platform = n.get("platform")
        if platform not in SUB_PLATFORMS:
            continue
        d = _days_left(n.get("ends_at"))
        av[platform] = {"s": "ending", "d": d if d is not None and d >= 0 else None, "ends_at": n.get("ends_at")}
        origins[platform] = "notice"

    for row in stored or []:
        platform = row.get("platform")
        if platform not in SUB_PLATFORMS or row.get("origin") != "notice":
            continue
        d = _days_left(row.get("ends_at"))
        av[platform] = {"s": row.get("status") or "ending", "d": d, "ends_at": row.get("ends_at")}
        origins[platform] = "notice"

    return av, origins


def has_real_availability(origins: dict) -> bool:
    return any(v == "notice" for v in origins.values())
