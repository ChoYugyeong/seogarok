# -*- coding: utf-8 -*-
"""run.py — 서가(seoga) 실도서 카탈로그 수집 CLI.

기본 사용:
    python -m ingest.books.run --out data/catalog.jsonl --target 2000

기본 소스는 **예스24 공개 목록(SSR)** 이다 (robots.txt `User-agent: * / Allow: /`).
알라딘은 robots.txt fallback 그룹이 `Disallow: /` 라서 **기본 비활성**이며,
`--source aladin --allow-disallowed` 를 명시해야만 동작한다(사용자가 제휴/키를 확보한 경우 전용).

산출물: 1줄 1권 JSONL (UTF-8). 실행 리포트는 `ingest/books/_cache/run_report.json` 과
`ingest/books/_research/run_report.txt` 에 UTF-8로 남는다(한글 콘솔 깨짐 회피).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from collections import Counter, OrderedDict

# `python -m ingest.books.run` 과 `python ingest/books/run.py` 둘 다 지원
try:
    from . import fetch_base, yes24_html
except ImportError:  # pragma: no cover - 직접 실행 경로
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from ingest.books import fetch_base, yes24_html  # type: ignore

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(PKG_DIR, "_cache")
RESEARCH_DIR = os.path.join(PKG_DIR, "_research")
PROJECT_ROOT = os.path.dirname(os.path.dirname(PKG_DIR))
REPORT_JSON = os.path.join(CACHE_DIR, "run_report.json")
REPORT_TXT = os.path.join(RESEARCH_DIR, "run_report.txt")

FIELDS = ["id", "source", "title", "subtitle", "author", "publisher", "pubdate", "isbn13",
          "item_code", "price", "price_list", "rating", "cover_url", "link", "category",
          "description", "collected_at"]


def now_iso() -> str:
    return fetch_base._now_iso()


class RunReport:
    def __init__(self):
        self.lines: list[str] = []
        self.data: dict = {"started_at": now_iso()}

    def log(self, *a):
        line = " ".join(str(x) for x in a)
        self.lines.append(line)
        # 콘솔은 ASCII 안전하게(한글 콘솔 깨짐 회피): 파일에만 한글 그대로 기록
        try:
            print(line.encode("ascii", "backslashreplace").decode("ascii"))
        except Exception:
            pass

    def flush(self, path: str = REPORT_TXT):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with io.open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(self.lines) + "\n")


def load_robots(fetcher: fetch_base.Fetcher, robots_url: str, ua: str) -> fetch_base.RobotsPolicy:
    res = fetcher.get(robots_url)
    if res.status != 200:
        # robots.txt 없음/오류 → RFC 9309 기준 전체 허용으로 간주하되 리포트에 남긴다.
        policy = fetch_base.RobotsPolicy("", ua, robots_url)
        return policy
    return fetch_base.RobotsPolicy(res.text, ua, robots_url)


# --------------------------------------------------------------------------- #
# 예스24 수집
# --------------------------------------------------------------------------- #
def crawl_yes24(args, report: RunReport) -> tuple[OrderedDict, fetch_base.Fetcher, fetch_base.RobotsPolicy | None]:
    ua = args.user_agent
    fetcher = fetch_base.Fetcher(cache_dir=args.cache_dir, ua=ua,
                                 min_interval=args.min_interval, logger=report.log)
    policy = load_robots(fetcher, yes24_html.ROBOTS_URL, ua)
    summary = policy.summary()
    report.log("[robots] %s" % json.dumps(summary, ensure_ascii=False))

    categories = args.categories or yes24_html.DEFAULT_CATEGORY_ORDER
    planned = [c for c in categories if c]
    catalog: "OrderedDict[str, dict]" = OrderedDict()
    seen_keys: set[str] = set()
    pages_ok = pages_empty = pages_blocked = 0
    dupes = 0
    stop = False
    for cid in planned:
        label = yes24_html.GENRE_CATEGORIES.get(cid, cid)
        for page in range(1, args.pages_per_cat + 1):
            url = yes24_html.page_url(cid, page, args.page_size)
            if yes24_html.is_forbidden(url) or not policy.can_fetch(url):
                pages_blocked += 1
                report.log("[robots] BLOCKED %s" % url)
                continue
            try:
                res = fetcher.get(url, policy=policy)
            except fetch_base.RobotsDisallowed as e:
                pages_blocked += 1
                report.log("[robots] BLOCKED %s (%s)" % (url, e))
                continue
            except Exception as e:
                report.log("[warn] fetch failed %s: %s: %s" % (url, type(e).__name__, e))
                continue
            if res.status != 200:
                report.log("[warn] HTTP %s for %s" % (res.status, url))
                continue
            items = yes24_html.parse_list_page(res.text, cid, label, collected_at=res.fetched_at)
            if not items:
                pages_empty += 1
                report.log("[page] %s p%d -> 0 items (구조 변경/페이지 범위 초과?) skip" % (label, page))
                break
            pages_ok += 1
            added = 0
            for it in items:
                if it["id"] in catalog:
                    dupes += 1
                    continue
                key = yes24_html._norm_key(it["title"], it["author"] or "")
                if key in seen_keys:
                    dupes += 1
                    continue
                seen_keys.add(key)
                catalog[it["id"]] = it
                added += 1
            report.log("[page] %-14s p%-2d items=%-3d new=%-3d total=%d" %
                       (label, page, len(items), added, len(catalog)))
            if len(catalog) >= args.target:
                report.log("[stop] target reached: %d >= %d" % (len(catalog), args.target))
                stop = True
                break
        if stop:
            break

    report.log("[crawl] pages_ok=%d pages_empty=%d pages_blocked=%d dupes=%d unique=%d"
               % (pages_ok, pages_empty, pages_blocked, dupes, len(catalog)))
    report.data.update({
        "pages_ok": pages_ok, "pages_empty": pages_empty, "pages_blocked": pages_blocked,
        "duplicates_skipped": dupes, "unique_after_lists": len(catalog),
    })
    return catalog, fetcher, policy


def enrich_details(catalog: OrderedDict, fetcher: fetch_base.Fetcher,
                   policy: fetch_base.RobotsPolicy, args, report: RunReport) -> dict:
    """상위 N권 상세페이지에서 isbn13/description/카테고리/발행일 보강."""
    if args.detail_top <= 0:
        return {"detail_pages": 0, "isbn13_filled": 0, "description_filled": 0}
    ids = list(catalog.keys())[:args.detail_top]
    fetched = isbn_filled = desc_filled = detail_errors = 0
    t0 = time.monotonic()
    for i, book_id in enumerate(ids, 1):
        goods_no = catalog[book_id]["item_code"]
        url = yes24_html.detail_url(goods_no)
        if yes24_html.is_forbidden(url) or not policy.can_fetch(url):
            report.log("[robots] detail BLOCKED %s" % url)
            continue
        try:
            res = fetcher.get(url, policy=policy)
        except fetch_base.RobotsDisallowed:
            report.log("[robots] detail BLOCKED %s" % url)
            continue
        except Exception as e:
            detail_errors += 1
            report.log("[warn] detail fetch failed %s: %s" % (url, e))
            continue
        if res.status != 200:
            detail_errors += 1
            continue
        fetched += 1
        info = yes24_html.parse_detail_page(res.text)
        item = catalog[book_id]
        if info.get("isbn13"):
            item["isbn13"] = info["isbn13"]
            isbn_filled += 1
        if info.get("description"):
            item["description"] = info["description"]
            desc_filled += 1
        if info.get("category_path"):
            path = info["category_path"]
            if not path.startswith("국내도서"):
                path = "국내도서>" + path
            item["category"] = path
        if info.get("pubdate"):
            item["pubdate"] = info["pubdate"]
        if i % 25 == 0 or i == len(ids):
            report.log("[detail] %d/%d fetched=%d isbn=%d desc=%d elapsed=%.1fs"
                       % (i, len(ids), fetched, isbn_filled, desc_filled, time.monotonic() - t0))
    report.data.update({"detail_pages": fetched, "isbn13_filled": isbn_filled,
                        "description_filled": desc_filled, "detail_errors": detail_errors})
    return report.data


# --------------------------------------------------------------------------- #
# 알라딘(비활성 소스)
# --------------------------------------------------------------------------- #
def crawl_aladin(args, report: RunReport):
    try:
        from . import aladin_html
    except ImportError:  # pragma: no cover
        from ingest.books import aladin_html  # type: ignore

    if not args.allow_disallowed:
        robots_path = os.path.join(RESEARCH_DIR, "run_report_robots_blocked.txt")
        os.makedirs(RESEARCH_DIR, exist_ok=True)
        msg = (
            "BLOCKED: 알라딘(www.aladin.co.kr) robots.txt fallback 그룹이 `User-agent: * / Disallow: /` 이므로\n"
            "seoga-research-bot 수집이 금지되어 있습니다. (2026-10-27 실측: https://www.aladin.co.kr/robots.txt)\n"
            "필요 시 사용자가 알라딘 제휴/TTBKey를 확보한 뒤 `--allow-disallowed` 를 명시해야 합니다.\n"
        )
        with io.open(robots_path, "w", encoding="utf-8") as f:
            f.write(msg)
        report.log("[robots] " + msg.replace("\n", " "))
        report.flush()
        return None, None, None
    # 명시적 승인 시에만 도달 (현재는 미검증 경로)
    report.log("[aladin] --allow-disallowed 지정됨: 알라딘 수집 경로 진입(미검증)")
    return aladin_html.crawl(args, report)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def write_catalog(path: str, catalog: dict) -> int:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for item in catalog.values():
            row = {k: item.get(k) for k in FIELDS}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    return len(catalog)


def build_stats(catalog: dict) -> dict:
    n = len(catalog)
    rows = list(catalog.values())

    def miss(k):
        return sum(1 for r in rows if r.get(k) in (None, "", []))

    cats = Counter(r.get("category") or "(none)" for r in rows)
    return {
        "rows": n,
        "missing": {k: miss(k) for k in ["title", "cover_url", "author", "publisher", "pubdate",
                                         "price", "price_list", "rating", "isbn13", "description"]},
        "missing_pct": {k: round(100.0 * miss(k) / n, 2) if n else None
                        for k in ["title", "cover_url", "author", "publisher", "pubdate",
                                  "price", "price_list", "rating", "isbn13", "description"]},
        "category_distribution": dict(cats.most_common()),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="서가(seoga) 실도서 카탈로그 수집")
    ap.add_argument("--out", default=os.path.join(PROJECT_ROOT, "data", "catalog.jsonl"))
    ap.add_argument("--target", type=int, default=2000)
    ap.add_argument("--source", choices=["yes24", "aladin"], default="yes24")
    ap.add_argument("--allow-disallowed", action="store_true",
                    help="robots Disallow 소스(알라딘)를 사용자가 명시 승인한 경우에만")
    ap.add_argument("--pages-per-cat", type=int, default=2)
    ap.add_argument("--page-size", type=int, default=yes24_html.DEFAULT_PAGE_SIZE)
    ap.add_argument("--categories", nargs="*", default=None,
                    help="예스24 categoryNumber 목록 (미지정 시 상위 장르 전체)")
    ap.add_argument("--detail-top", type=int, default=200,
                    help="상세페이지에서 isbn13/description 보강할 상위 권수 (0=비활성)")
    ap.add_argument("--min-interval", type=float, default=1.2, help="요청 간 최소 간격(초)")
    ap.add_argument("--user-agent", default=fetch_base.DEFAULT_UA)
    ap.add_argument("--cache-dir", default=CACHE_DIR)
    ap.add_argument("--report-json", default=REPORT_JSON)
    args = ap.parse_args(argv)

    os.makedirs(args.cache_dir, exist_ok=True)
    os.makedirs(RESEARCH_DIR, exist_ok=True)
    report = RunReport()
    report.log("=== seoga catalog run | source=%s target=%d out=%s ==="
               % (args.source, args.target, args.out))
    report.log("started_at=%s" % report.data["started_at"])
    t0 = time.monotonic()
    fetcher = None

    if args.source == "aladin":
        catalog, fetcher, policy = crawl_aladin(args, report)
        if catalog is None:
            report.log("EXIT: robots Disallowed (알라딘 비활성). 0 rows written.")
            return 3
    else:
        catalog, fetcher, policy = crawl_yes24(args, report)
        if catalog:
            enrich_details(catalog, fetcher, policy, args, report)
            # 상세 보강 후 카테고리 경로가 세분화되므로 중복(동일 title+author) 재점검
            deduped: "OrderedDict[str, dict]" = OrderedDict()
            seen = set()
            for k, v in catalog.items():
                key = yes24_html._norm_key(v["title"], v["author"] or "")
                if key in seen:
                    report.log("[dedupe] drop %s (%s)" % (v["title"], k))
                    continue
                seen.add(key)
                deduped[k] = v
            catalog = deduped

    n = write_catalog(args.out, catalog)
    elapsed = time.monotonic() - t0
    stats = build_stats(catalog)
    report.data.update({
        "finished_at": now_iso(),
        "elapsed_seconds": round(elapsed, 1),
        "out": os.path.abspath(args.out),
        "rows_written": n,
        "target": args.target,
        "source": args.source,
        "request_count": getattr(fetcher, "request_count", 0) if fetcher else 0,
        "cache_hits": getattr(fetcher, "cache_hits", 0) if fetcher else 0,
        "stats": stats,
    })
    report.log("rows_written=%d (target %d) elapsed=%.1fs requests=%d cache_hits=%d"
               % (n, args.target, elapsed, report.data["request_count"], report.data["cache_hits"]))
    report.log("missing_pct=%s" % json.dumps(stats["missing_pct"], ensure_ascii=False))
    report.log("category_distribution=%s" % json.dumps(stats["category_distribution"], ensure_ascii=False))

    os.makedirs(os.path.dirname(args.report_json), exist_ok=True)
    with io.open(args.report_json, "w", encoding="utf-8") as f:
        json.dump(report.data, f, ensure_ascii=False, indent=1)
    report.log("report_json=%s" % args.report_json)
    report.flush()

    if n == 0:
        report.log("EXIT: 0 rows (페이지 구조 변경/차단 가능성). 경고 후 0건 처리.")
        return 4
    if n < 1500:
        report.log("WARN: rows(%d) < 1500 (수용 기준 미달)" % n)
    if fetcher is not None:
        fetcher.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
