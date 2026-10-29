"""카탈로그 설명 배치 보강 (YES24 itemDetail).

설명이 비어 있는 책에 대해:
1) YES24 상세 API의 책소개(bookIntroduction)/요약(bookSummary) 사용
2) 소개가 없고 목차(tableOfContents)가 있으면 목차 기반 사실 요약문 생성
3) pages/rating/subtitle 등 부가 필드도 함께 보강

사용:
  python -m ingest.books.enrich_descriptions                       # 전체 누락분
  python -m ingest.books.enrich_descriptions --limit 800 --workers 8 --timeout 180
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

API_BASE = "https://apis.yes24.com"


def _key() -> str:
    key = (os.getenv("YES24_API_KEY") or "").strip()
    if key:
        return key
    env_path = Path(__file__).resolve().parents[2] / ".env"
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("YES24_API_KEY="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


def _clean_text(value) -> str:
    text = str(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;?", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _toc_summary(row: dict, toc: str) -> str | None:
    """목차 기반 사실 요약문 — 출판사 제공 목차에서 구성만 발췌."""
    parts = [p.strip(" ·•-–—") for p in re.split(r"[>\n/|]+", toc) if p.strip()]
    parts = [p for p in parts if 2 <= len(p) <= 40]
    if not parts:
        return None
    first = " · ".join(parts[:6])
    title = (row.get("title") or "").strip()
    author = (row.get("author") or "저자 미상").split("/")[0].replace(" 저", "").strip()
    publisher = (row.get("publisher") or "").strip()
    who = f"{author}의 책" if author else "책"
    where = f"{publisher}에서 출간되었습니다. " if publisher else ""
    return (
        f"『{title}』은(는) {who}으로, {where}"
        f"목차는 «{first[:400]}» 등으로 구성되어 있습니다."
    )


def fetch_detail(key: str, row: dict) -> dict:
    isbn = (row.get("isbn13") or "").strip()
    item = (row.get("item_code") or "").strip()
    if isbn:
        params = {"searchType": "ISBN13", "query": isbn, "detail": "Y"}
    elif item:
        params = {"searchType": "ItemId", "query": item, "detail": "Y"}
    else:
        return {}
    url = API_BASE + "/v1/goods/itemDetail?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, headers={"X-Api-Key": key, "Accept": "application/json", "User-Agent": "seogarok-enrich/1"}
    )
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            items = (data.get("data") or {}).get("items") or []
            if not items:
                return {}
            it = items[0]
            cd = it.get("contentDetail") or {}
            return {
                "intro": _clean_text(cd.get("bookIntroduction"))[:2000] or None,
                "summary": _clean_text(cd.get("bookSummary"))[:800] or None,
                "toc": _clean_text(cd.get("tableOfContents"))[:4000] or None,
                "pages": it.get("pages"),
                "star": it.get("starScore"),
                "subtitle": (it.get("subTitle") or "").strip() or None,
            }
        except Exception:
            if attempt == 0:
                time.sleep(0.4)
    return {}


def enrich_html(rows: list[dict], workers: int = 3, timeout: int = 0, min_interval: float = 1.1, limit: int = 0) -> dict:
    """남은 누락 책을 YES24 HTML 상세페이지에서 보강 (robots 준수).

    - 워커별 Fetcher(요청 간 min_interval) 사용, cache 공유
    - robots Disallow면 건너뜀
    """
    import sys
    import threading

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ingest.books import yes24_html
    from ingest.books.fetch_base import Fetcher, RobotsPolicy

    targets = [r for r in rows if len(_clean_text(r.get("description"))) <= 20]
    if limit:
        targets = targets[:limit]
    if not targets:
        return {"targets": 0, "filled": 0, "skipped": 0, "failed": 0}
    ua = "seogarok-enrich/1 (contact: seogarok.com)"
    cache_dir = str(Path(__file__).resolve().parents[2] / ".cache" / "yes24-enrich")
    probe = Fetcher(ua=ua, min_interval=min_interval, cache_dir=cache_dir)
    robots_res = probe.get("https://www.yes24.com/robots.txt", allow_disallowed=True)
    policy = RobotsPolicy(robots_res.text, ua, "https://www.yes24.com/robots.txt")
    local = threading.local()

    def fetcher() -> Fetcher:
        f = getattr(local, "f", None)
        if f is None:
            f = Fetcher(ua=ua, min_interval=min_interval, cache_dir=cache_dir)
            local.f = f
        return f

    filled = 0
    skipped = 0
    failed = 0
    t0 = time.time()

    def work(row):
        nonlocal filled, skipped, failed
        if timeout and time.time() - t0 > timeout:
            return
        item = str(row.get("item_code") or "").strip()
        if not item:
            skipped += 1
            return
        url = yes24_html.detail_url(item)
        if not policy.can_fetch(url):
            skipped += 1
            return
        try:
            res = fetcher().get(url, policy=policy)
            info = yes24_html.parse_detail_page(res.text)
        except Exception:
            failed += 1
            return
        desc = _clean_text(info.get("description"))
        if desc:
            row["description"] = desc[:2000]
            filled += 1
        else:
            failed += 1
        if info.get("pages"):
            row["pages"] = info["pages"]
        if info.get("isbn13") and not row.get("isbn13"):
            row["isbn13"] = info["isbn13"]
        row["enriched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(work, targets))
    return {"targets": len(targets), "filled": filled, "skipped": skipped, "failed": failed, "seconds": round(time.time() - t0, 1)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="YES24 설명 배치 보강")
    ap.add_argument("--catalog", default=str(Path(__file__).resolve().parents[2] / "data" / "catalog.jsonl"))
    ap.add_argument("--out", default="")
    ap.add_argument("--limit", type=int, default=0, help="누락분 중 최대 N권 (0=전체)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--timeout", type=int, default=0, help="초 (0=무제한)")
    ap.add_argument("--min-desc", type=int, default=20, help="이 길이 이하 설명은 누락으로 간주")
    ap.add_argument("--html", action="store_true", help="API로 안 되는 책은 HTML 상세페이지에서 보강")
    ap.add_argument("--html-workers", type=int, default=3)
    ap.add_argument("--html-interval", type=float, default=1.1, help="HTML 요청 간 최소 간격(초)")
    args = ap.parse_args(argv)

    key = _key()
    if not key:
        print("[enrich] YES24_API_KEY 없음 — 스킵", file=sys.stderr)
        return 0

    src = Path(args.catalog)
    out = Path(args.out) if args.out else src
    if not src.exists():
        print(f"[enrich] catalog 없음: {src}", file=sys.stderr)
        return 1

    rows = []
    with src.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    print(f"[enrich] rows={len(rows)}")

    targets = [
        r for r in rows
        if len(_clean_text(r.get("description"))) <= args.min_desc
    ]
    if args.limit:
        targets = targets[: args.limit]
    print(f"[enrich] targets={len(targets)} (전체 누락)")

    filled_api = 0
    filled_toc = 0
    failed = 0
    t0 = time.time()

    def work(row):
        nonlocal filled_api, filled_toc, failed
        if args.timeout and time.time() - t0 > args.timeout:
            return
        d = fetch_detail(key, row)
        if not d:
            failed += 1
            return
        if d.get("intro") or d.get("summary"):
            row["description"] = d["intro"] or d["summary"]
            filled_api += 1
        elif d.get("toc"):
            row["description"] = _toc_summary(row, d["toc"])
            if row.get("description"):
                filled_toc += 1
        if d.get("pages"):
            row["pages"] = d["pages"]
        if d.get("subtitle") and not row.get("subtitle"):
            row["subtitle"] = d["subtitle"]
        if d.get("star") not in (None, 0):
            row["rating"] = float(d["star"])
        row["enriched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        list(ex.map(work, targets))

    tmp = out.with_suffix(out.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(out)

    with_desc = sum(1 for r in rows if len(_clean_text(r.get("description"))) > args.min_desc)
    print(
        f"[enrich] API done in {time.time() - t0:.1f}s · api={filled_api} toc={filled_toc} failed={failed} "
        f"· coverage {with_desc}/{len(rows)} ({with_desc * 100 // max(1, len(rows))}%)"
    )

    if args.html:
        h = enrich_html(rows, workers=args.html_workers, timeout=args.timeout, min_interval=args.html_interval, limit=args.limit)
        print(f"[enrich] HTML {h}")
        tmp = out.with_suffix(out.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.replace(out)
        with_desc = sum(1 for r in rows if len(_clean_text(r.get("description"))) > args.min_desc)
        print(
            f"[enrich] final coverage {with_desc}/{len(rows)} "
            f"({with_desc * 100 // max(1, len(rows))}%)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
