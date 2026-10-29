"""카탈로그에 없는 책 온디맨드 조회 (YES24 Open API).

검색 품질 보강: 카탈로그(약 19k)에 없는 책도 실시간 조회로 찾아 보여준다.
- 인메모리 TTL 캐시(600s)로 반복 호출 비용 최소화
- API 키는 환경변수 YES24_API_KEY (없으면 기능 비활성 → 기존 동작 유지)
- 응답 스키마는 serialize_book 과 동일하게 맞춘다 (프론트 공통 사용)
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import urllib.request

BASE = "https://apis.yes24.com"
UA = "seogarok/0.5 (+book availability layer)"
TIMEOUT = 5.0
CACHE_TTL = 600.0
CACHE_MAX = 256

_lock = threading.Lock()
_cache: dict[str, tuple[float, object]] = {}


def enabled() -> bool:
    return bool(os.getenv("YES24_API_KEY"))


def _cache_get(key: str):
    with _lock:
        hit = _cache.get(key)
        if not hit:
            return None
        ts, val = hit
        if time.time() - ts > CACHE_TTL:
            _cache.pop(key, None)
            return None
        return val


def _cache_put(key: str, val) -> None:
    with _lock:
        if len(_cache) >= CACHE_MAX:
            try:
                oldest = min(_cache.items(), key=lambda kv: kv[1][0])[0]
                _cache.pop(oldest, None)
            except ValueError:
                pass
        _cache[key] = (time.time(), val)


def _get(path: str, params: dict) -> dict:
    key = os.getenv("YES24_API_KEY")
    if not key:
        raise RuntimeError("YES24_API_KEY not set")
    url = BASE + path + "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(
        url, headers={"X-Api-Key": key, "Accept": "application/json", "User-Agent": UA}
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    if not data.get("success"):
        raise RuntimeError("YES24 API error")
    return data.get("data") or {}


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _date(v) -> str | None:
    s = str(v or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s or None


def _desc(item: dict) -> str | None:
    cd = item.get("contentDetail") or {}
    text = cd.get("bookIntroduction") if isinstance(cd, dict) else None
    if not text:
        return None
    return " ".join(str(text).split())[:2000] or None


def to_payload(item: dict) -> dict | None:
    if not item.get("itemId") or not item.get("title"):
        return None
    if item.get("itemStatus") and item["itemStatus"] != "판매중":
        return None
    cat = item.get("goodsSortNm") or ""
    goods = str(item["itemId"])
    return {
        "id": f"yes24:{goods}",
        "title": (item.get("title") or "").strip(),
        "subtitle": None,
        "author": (item.get("author") or "").strip() or "저자 미상",
        "publisher": (item.get("publisher") or "").strip() or None,
        "pubdate": _date(item.get("publishDate")),
        "isbn13": item.get("isbn13") or None,
        "item_code": goods,
        "price": _int(item.get("salePrice")),
        "price_list": _int(item.get("shopPrice")),
        "rating": None,
        "cover_url": item.get("cover") or f"https://image.yes24.com/goods/{goods}/L",
        "link": item.get("link") or f"https://www.yes24.com/Product/Goods/{goods}",
        "category": cat.replace("-", ">") if cat else None,
        "description": _desc(item),
        "av": {},
        "av_origin": {},
        "notices": [],
        "real": True,
        "live": True,
    }


def search(query: str, limit: int = 12) -> list[dict]:
    """실시간 검색 (카탈로그 미수록 책)."""
    q = (query or "").strip()
    if not q or not enabled():
        return []
    ck = f"search:{q}:{limit}"
    hit = _cache_get(ck)
    if hit is not None:
        return hit  # type: ignore[return-value]
    data = _get("/v1/goods/itemList", {"query": q, "page": 1, "pageSize": max(limit, 10)})
    items = data.get("items") or []
    out = [p for p in (to_payload(it) for it in items) if p][:limit]
    _cache_put(ck, out)
    # 상세(/api/book)에서 재사용할 수 있게 id 별로도 캐시
    for p in out:
        _cache_put(f"id:{p['item_code']}", p)
    return out


def fetch_detail(goods: str) -> dict | None:
    """상품 상세 API(itemDetail, detail=Y)로 풍부한 단건 정보 조회 (캐시 10분)."""
    if not goods or not enabled():
        return None
    ck = f"detail:{goods}"
    hit = _cache_get(ck)
    if hit is not None:
        return hit  # type: ignore[return-value]
    try:
        data = _get("/v1/goods/itemDetail", {
            "searchType": "ItemId", "query": str(goods), "detail": "Y",
        })
    except Exception:
        return None
    items = data.get("items") or []
    if not items:
        return None
    item = items[0]
    payload = to_payload(item)
    if not payload:
        # 예약판매·절판 등 '판매중'이 아닌 상태도 상세는 열리게 최소 페이로드 구성
        goods2 = str(item.get("itemId") or "").strip()
        title2 = str(item.get("title") or "").strip()
        if not goods2 or not title2:
            return None
        payload = {
            "id": f"yes24:{goods2}",
            "title": title2,
            "subtitle": None,
            "author": (item.get("author") or "").strip() or "저자 미상",
            "publisher": (item.get("publisher") or "").strip() or None,
            "pubdate": _date(item.get("publishDate")),
            "isbn13": item.get("isbn13") or None,
            "item_code": goods2,
            "price": _int(item.get("salePrice")),
            "price_list": _int(item.get("shopPrice")),
            "rating": None,
            "cover_url": item.get("cover") or f"https://image.yes24.com/goods/{goods2}/L",
            "link": item.get("link") or f"https://www.yes24.com/Product/Goods/{goods2}",
            "category": (item.get("goodsSortNm") or "").replace("-", ">") or None,
            "description": _desc(item),
            "av": {},
            "av_origin": {},
            "notices": [],
            "real": True,
            "live": True,
        }
    payload["item_status"] = (item.get("itemStatus") or "").strip() or None
    # 확장 필드
    try:
        payload["rating"] = float(item["starScore"]) if item.get("starScore") is not None else None
    except (TypeError, ValueError):
        payload["rating"] = None
    payload["subtitle"] = (item.get("subTitle") or "").strip() or None
    payload["pages"] = _int(item.get("pages"))
    payload["sale_point"] = _int(item.get("salePoint"))
    payload["weight"] = _int(item.get("weight"))
    payload["size"] = (
        f"{item['width']}×{item['length']}mm"
        if item.get("width") and item.get("length")
        else None
    )
    series = item.get("series") or []
    payload["series"] = [
        {"id": x.get("seriesId"), "name": x.get("seriesName")}
        for x in series
        if isinstance(x, dict) and x.get("seriesName")
    ][:5]
    summary = ((item.get("contentDetail") or {}).get("bookSummary") or "").strip()
    payload["summary"] = " ".join(summary.split())[:600] or None
    _cache_put(ck, payload)
    return payload


def fetch_extras(book: dict) -> dict:
    """DB 책 상세에 붙일 예스24 확장 정보(평점·쪽수 등) — ISBN13 기준, 실패 시 빈 dict."""
    if not enabled():
        return {}
    isbn = (book.get("isbn13") or "").strip()
    goods = ""
    if isbn:
        ck = f"extras-isbn:{isbn}"
        hit = _cache_get(ck)
        if hit is not None:
            return hit  # type: ignore[return-value]
        try:
            data = _get("/v1/goods/itemDetail", {"searchType": "ISBN13", "query": isbn, "detail": "Y"})
            items = data.get("items") or []
            if not items:
                return {}
            item = items[0]
            goods = str(item.get("itemId") or "")
            _d = _desc(item)
            out = {
                "description": (_d[:800] if _d else None),
                "rating": float(item["starScore"]) if item.get("starScore") is not None else None,
                "pages": _int(item.get("pages")),
                "sale_point": _int(item.get("salePoint")),
                "size": (
                    f"{item['width']}×{item['length']}mm"
                    if item.get("width") and item.get("length")
                    else None
                ),
                "weight": _int(item.get("weight")),
                "item_code": goods or None,
            }
            _cache_put(ck, out)
            return out
        except Exception:
            return {}
    return {}


def fetch_book(book_id: str) -> dict | None:
    """온디맨드 상세: id가 yes24:XXXX 형태일 때 검색으로 찾아 반환."""
    if not book_id.startswith("yes24:") or not enabled():
        return None
    goods = book_id.split(":", 1)[1].strip()
    if not goods:
        return None
    # 1) 검색 결과 캐시 우선 (클릭 직후 상세 조회)
    hit_id = _cache_get(f"id:{goods}")
    if hit_id is not None:
        return hit_id  # type: ignore[return-value]
    ck = f"book:{goods}"
    hit = _cache_get(ck)
    if hit is not None:
        return hit  # type: ignore[return-value]
    # 1) 단건 상세 API 우선 (평점·쪽수 등 풍부)
    detail = fetch_detail(goods)
    if detail:
        _cache_put(ck, detail)
        return detail
    # 2) 검색 결과에서 매칭
    data = _get("/v1/goods/itemList", {"query": goods, "page": 1, "pageSize": 10})
    items = data.get("items") or []
    found = None
    for it in items:
        if str(it.get("itemId")) == goods:
            found = to_payload(it)
            break
    if not found and items:
        found = to_payload(items[0])
    _cache_put(ck, found)
    return found
