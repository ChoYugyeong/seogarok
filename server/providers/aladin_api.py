"""알라딘 공식 OpenAPI 어댑터 (TTBKey 필요).

키가 있으면 이 경로가 "정답"이다. 없으면 ingest/books 의 공개 페이지 수집(research 모드)을 쓴다.
  ALADIN_TTBKEY=... python -m server.providers.aladin_api --category 1 --pages 5 --out data/catalog_api.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://www.aladin.co.kr/ttb/api"


class AladinAPIError(RuntimeError):
    pass


class AladinOpenAPI:
    def __init__(self, ttbkey: str | None = None, timeout: int = 20):
        self.ttbkey = (ttbkey or os.getenv("ALADIN_TTBKEY", "")).strip()
        self.timeout = timeout

    def _get(self, path: str, **params) -> dict:
        if not self.ttbkey:
            raise AladinAPIError("ALADIN_TTBKEY 가 없습니다. https://www.aladin.co.kr/ttb/apiguide.aspx 참고")
        params = {k: v for k, v in params.items() if v not in (None, "")}
        params.update({"ttbkey": self.ttbkey, "output": "js", "Version": "20131101"})
        url = f"{BASE}/{path}?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "seoga/0.2"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            raise AladinAPIError(f"JSON 파싱 실패: {body[:200]}")
        if "errorCode" in data:
            raise AladinAPIError(f"{data.get('errorCode')}: {data.get('errorMessage')}")
        return data

    # --- endpoints ---
    def search(self, query: str, max_results: int = 50, start: int = 1, **kw) -> dict:
        return self._get("ItemSearch.aspx", Query=query, MaxResults=max_results, start=start,
                         SearchTarget="Book", **kw)

    def item_list(self, category_id: int = 0, max_results: int = 50, start: int = 1, **kw) -> dict:
        return self._get("ItemList.aspx", QueryType="Bestseller", MaxResults=max_results,
                         start=start, SearchTarget="Book", CategoryId=category_id, **kw)

    def lookup(self, item_id: str) -> dict:
        return self._get("ItemLookUp.aspx", ItemId=item_id, ItemIdType="ItemId", OptResult="ebookList")

    def categories(self) -> dict:
        return self._get("CategoryList.aspx")


def item_to_row(item: dict) -> dict:
    """알라딘 item -> 카탈로그 JSONL row"""
    return {
        "id": "aladin:" + str(item.get("itemId") or item.get("isbn13") or item.get("title")),
        "source": "aladin_api",
        "title": item.get("title"),
        "subtitle": item.get("subTitle") or None,
        "author": item.get("author"),
        "publisher": item.get("publisher"),
        "pubdate": item.get("pubDate"),
        "isbn13": item.get("isbn13") or None,
        "item_code": str(item.get("itemId") or ""),
        "price": item.get("priceSales"),
        "price_list": item.get("priceStandard"),
        "rating": item.get("customerReviewRank"),
        "cover_url": item.get("cover"),
        "link": item.get("link"),
        "category": item.get("categoryName"),
        "description": item.get("description"),
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", help="키워드 검색")
    ap.add_argument("--category", type=int, default=0, help="카테고리 ID 베스트셀러")
    ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--page-size", type=int, default=50)
    ap.add_argument("--out", default="data/catalog_api.jsonl")
    args = ap.parse_args(argv)

    api = AladinOpenAPI()
    rows = []
    for p in range(args.pages):
        start = p * args.page_size + 1
        if args.query:
            data = api.search(args.query, args.page_size, start)
        else:
            data = api.item_list(args.category, args.page_size, start)
        items = data.get("item") or []
        rows.extend(item_to_row(i) for i in items if i.get("title"))
        print(f"page {p+1}/{args.pages}: +{len(items)} (total {len(rows)})")
        time.sleep(1.0)  # 예의

    with open(args.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("wrote", args.out, len(rows), "rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
