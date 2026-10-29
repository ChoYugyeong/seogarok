"""IndexNow 제출 (Bing/Yandex/Seznam 등) — 표준 라이브러리만 사용.

사용:
  python scripts/submit_indexnow.py            # 핵심 URL + 책 표본
  python scripts/submit_indexnow.py --limit 200
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

HOST = "seogarok.com"
KEY = "c7f1e2a9b4d64f3e8a05c2b7d19e6f4a"
KEY_LOCATION = f"https://{HOST}/{KEY}.txt"
ENDPOINT = "https://api.indexnow.org/indexnow"


def fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "seogarok-indexnow/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def sitemap_urls(limit: int) -> list[str]:
    try:
        xml = fetch(f"https://{HOST}/sitemap-books.xml")
        locs = re.findall(r"<loc>(.*?)</loc>", xml)
    except Exception as exc:
        print("[indexnow] sitemap 조회 실패:", exc, file=sys.stderr)
        locs = []
    random.seed(42)
    random.shuffle(locs)
    return locs[:limit]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="IndexNow URL 제출")
    ap.add_argument("--limit", type=int, default=100, help="책 URL 표본 수")
    args = ap.parse_args(argv)

    core = [
        f"https://{HOST}/",
        f"https://{HOST}/books?page=1",
        f"https://{HOST}/sitemap-index.xml",
        f"https://{HOST}/llms.txt",
    ]
    urls = core + sitemap_urls(max(0, args.limit))

    payload = {
        "host": HOST,
        "key": KEY,
        "keyLocation": KEY_LOCATION,
        "urlList": urls,
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "seogarok-indexnow/1"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            code = r.status
            body = r.read().decode("utf-8", "ignore")[:200]
    except urllib.error.HTTPError as exc:
        code = exc.code
        body = exc.read().decode("utf-8", "ignore")[:200]
    except Exception as exc:
        print("[indexnow] 전송 실패:", exc, file=sys.stderr)
        return 1

    print(f"[indexnow] status={code} urls={len(urls)} body={body}")
    return 0 if code in (200, 202) else 1


if __name__ == "__main__":
    raise SystemExit(main())
