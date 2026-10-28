"""YES24 Open API 수집기 (공식 · Basic 무료).

정책 준수 (https://developers.yes24.com 운영정책 2026-09-17):
  - **출처 표기** 필수 → row 에 source="yes24_api", link 를 반드시 보관
  - **상품 상세페이지 링크** 필수 → link / addOnLink 그대로 저장
  - 캐싱은 "서비스 제공에 필요한 범위" 내에서만 → **베스트/신상/스테디 인기 캐시**만 받는다.
    (전체 도서 DB 축적·제3자 재배포 금지 → 카탈로그 전체를 긁지 않고, 서비스 노출용 인기분만 유지)
  - API Key 공동 사용 금지 → Key 는 .env / GitHub Secrets 에만 둔다.

사용:
  python -m ingest.books.yes24_api --out data/catalog.jsonl --per-category 40 --categories 12
  python -m ingest.books.yes24_api --search "한강" --out data/one.jsonl   # 단건 확인용
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BASE = "https://apis.yes24.com"
CACHE_DIR = ROOT / "ingest" / "books" / "_cache_api"
UA = "seoga/0.4 (+book availability layer; contact: local)"
MIN_INTERVAL = 0.35  # 예의: 초당 ~3회


def load_env(path: Path = ROOT / ".env") -> dict:
    env = dict(os.environ)
    if path.exists():
        for line in io.open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env.setdefault(k.strip(), v.strip())
    return env


class Yes24API:
    def __init__(self, key: str | None = None, cache: bool = True):
        self.key = key or load_env().get("YES24_API_KEY", "")
        if not self.key:
            raise SystemExit("YES24_API_KEY 가 없습니다 (.env 또는 환경변수)")
        self.cache = cache
        self._last = 0.0
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _get(self, path: str, params: dict | None = None) -> dict:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        cache_key = hashlib.sha1((path + "?" + urllib.parse.urlencode(params)).encode()).hexdigest()[:16]
        cache_file = CACHE_DIR / f"{cache_key}.json"
        if self.cache and cache_file.exists():
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass

        # 레이트리밋
        wait = MIN_INTERVAL - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()

        url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, headers={"X-Api-Key": self.key, "Accept": "application/json",
                                                   "User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                raise RuntimeError(f"YES24 API HTTP {e.code}: {body[:200]}") from None
        if self.cache and data.get("success"):
            cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data

    # ---- endpoints ----
    def search(self, query: str, page: int = 1, page_size: int = 50) -> list[dict]:
        d = self._get("/v1/goods/itemList", {"query": query, "page": page, "pageSize": page_size})
        return (d.get("data") or {}).get("items") or []

    def categories(self) -> list[dict]:
        d = self._get("/v1/category/list")
        data = (d.get("data") or {})
        return data.get("data") or []

    def bestseller(self, category_id: str, page: int = 1, page_size: int = 50) -> list[dict]:
        return self._list("/v1/category/bestseller", category_id, page, page_size)

    def newproduct(self, category_id: str, page: int = 1, page_size: int = 50) -> list[dict]:
        return self._list("/v1/category/newproduct", category_id, page, page_size)

    def steady(self, category_id: str, page: int = 1, page_size: int = 50) -> list[dict]:
        return self._list("/v1/category/bestsellerSteady", category_id, page, page_size)

    def _list(self, path: str, category_id: str, page: int, page_size: int) -> list[dict]:
        d = self._get(path, {"categoryId": category_id, "page": page, "pageSize": page_size})
        return (d.get("data") or {}).get("items") or []


def _date(v) -> str | None:
    s = str(v or "").strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s or None


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _desc(item: dict) -> str | None:
    cd = item.get("contentDetail") or {}
    text = cd.get("bookIntroduction") if isinstance(cd, dict) else None
    if not text:
        return None
    text = " ".join(str(text).split())
    return text[:2000] or None


def to_row(item: dict) -> dict | None:
    if not item.get("title") or not item.get("itemId"):
        return None
    if item.get("itemStatus") and item["itemStatus"] != "판매중":
        return None
    cat = item.get("goodsSortNm") or ""
    return {
        "id": f"yes24:{item['itemId']}",
        "source": "yes24_api",
        "title": item.get("title"),
        "subtitle": None,
        "author": (item.get("author") or "").strip() or None,
        "publisher": (item.get("publisher") or "").strip() or None,
        "pubdate": _date(item.get("publishDate")),
        "isbn13": item.get("isbn13") or None,
        "item_code": str(item.get("itemId")),
        "price": _int(item.get("salePrice")),
        "price_list": _int(item.get("shopPrice")),
        "rating": None,
        "cover_url": item.get("cover") or None,
        "link": item.get("link") or None,
        "addon_link": item.get("addOnLink") or None,
        "category": cat.replace("-", ">") if cat else None,
        "description": _desc(item),
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


def discover_categories(api: Yes24API, limit: int = 24, root: str = "국내도서") -> list[str]:
    """국내도서 하위 2단계 카테고리 ID 를 고른다.

    앞에서 몇 개만 자르면 특정 분야(한국사/어린이)로 쏠려 검색 커버리지가 무너진다.
    → 주요 분야를 우선순위로 먼저 담고, 나머지로 limit 을 채운다.
    """
    PRIORITY = [
        "소설", "시/희곡", "에세이", "인문", "경제경영", "자기계발",
        "역사", "자연과학", "사회정치", "예술", "여행", "청소년",
        "국어와외국어", "컴퓨터/IT", "가정살림", "건강취미", "종교", "어린이",
    ]
    cats = api.categories()
    pool: list[tuple[str, str]] = []
    for c in cats:
        path = c.get("categoryFullPath") or ""
        parts = [p.strip() for p in path.split(">")]
        if len(parts) == 2 and parts[0] == root:
            pool.append((str(c.get("categoryId")), parts[1]))

    picked: list[str] = []

    def add(name: str) -> None:
        for cid, nm in pool:
            if nm == name and cid not in picked:
                picked.append(cid)
                return
        for cid, nm in pool:
            if name in nm and cid not in picked:
                picked.append(cid)
                return

    for name in PRIORITY:
        if len(picked) >= limit:
            break
        add(name)
    for cid, _ in pool:
        if len(picked) >= limit:
            break
        if cid not in picked:
            picked.append(cid)
    return picked[:limit]


def collect(api: Yes24API, category_ids: list[str], per_category: int = 40) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    kinds = (("bestseller", api.bestseller), ("newproduct", api.newproduct), ("steady", api.steady))
    for cid in category_ids:
        for name, fn in kinds:
            try:
                items = fn(cid, page=1, page_size=per_category)
            except RuntimeError as exc:
                print(f"  [{cid}/{name}] 실패: {exc}")
                continue
            added = 0
            for it in items:
                row = to_row(it)
                if not row or row["id"] in seen:
                    continue
                seen.add(row["id"])
                rows.append(row)
                added += 1
            print(f"  [{cid}/{name}] +{added} (누적 {len(rows)})")
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="YES24 Open API → catalog JSONL")
    ap.add_argument("--out", default=str(ROOT / "data" / "catalog.jsonl"))
    ap.add_argument("--per-category", type=int, default=40, help="카테고리×종류별 수집 수")
    ap.add_argument("--categories", type=int, default=12, help="자동 선택할 카테고리 수")
    ap.add_argument("--search", default=None, help="검색어로만 수집 (테스트용)")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args(argv)

    api = Yes24API(cache=not args.no_cache)

    if args.search:
        rows = [r for r in (to_row(i) for i in api.search(args.search, 1, args.per_category)) if r]
        print(f"[yes24] search '{args.search}' → {len(rows)}건")
    else:
        cats = discover_categories(api, args.categories)
        print(f"[yes24] categories({len(cats)}): {cats}")
        rows = collect(api, cats, args.per_category)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[yes24] wrote {out} rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
