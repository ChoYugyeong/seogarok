# -*- coding: utf-8 -*-
"""verify.py — catalog.jsonl 검증 리포트(UTF-8) 생성.

사용:
    python -m ingest.books.verify --file data/catalog.jsonl \
        --report ingest/books/_research/verify_report.txt

검사 항목: 행 수 / 필수키 / 결측률 / 중복(id·item_code·title+author) / 카테고리 분포 /
가격·별점·발행연도 통계 / 한글 정상 여부 / 샘플 5권 원문 그대로.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import statistics
import sys
from collections import Counter

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(PKG_DIR))
RESEARCH_DIR = os.path.join(PKG_DIR, "_research")

FIELDS = ["id", "source", "title", "subtitle", "author", "publisher", "pubdate", "isbn13",
          "item_code", "price", "price_list", "rating", "cover_url", "link", "category",
          "description", "collected_at"]
REQUIRED = ["id", "source", "title", "link", "collected_at"]
HANGUL = re.compile(r"[\uac00-\ud7a3]")


def load_rows(path: str) -> list[dict]:
    rows: list[dict] = []
    with io.open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit("line %d JSON parse error: %s" % (i, e))
    return rows


def _missing(row: dict, key: str) -> bool:
    return row.get(key) in (None, "", [], {})


def build_report(rows: list[dict], path: str) -> tuple[str, dict]:
    n = len(rows)
    out: list[str] = []
    L = out.append
    L("# catalog.jsonl 검증 리포트")
    L("")
    L("- 파일: `%s`" % os.path.abspath(path))
    L("- 행 수: **%d**" % n)
    if n == 0:
        return "\n".join(out) + "\n", {"rows": 0}

    # 키 검사
    key_counter = Counter()
    for r in rows:
        key_counter.update(r.keys())
    L("- 필수키 누락: %s" % ([k for k in REQUIRED if key_counter.get(k, 0) != n] or "없음"))
    extra = sorted(set(key_counter) - set(FIELDS))
    L("- 스키마 외 추가키: %s" % (extra or "없음"))
    L("")

    # 결측률
    L("## 결측률")
    L("")
    L("| 필드 | 결측 | 결측률 |")
    L("|---|---:|---:|")
    miss_pct = {}
    for f in FIELDS:
        m = sum(1 for r in rows if _missing(r, f))
        pct = 100.0 * m / n
        miss_pct[f] = round(pct, 2)
        L("| %s | %d | %.2f%% |" % (f, m, pct))
    L("")

    # 중복
    L("## 중복")
    L("")
    for keyname, keyfn in [
        ("id", lambda r: r.get("id")),
        ("item_code", lambda r: r.get("item_code")),
        ("title+author", lambda r: (r.get("title") or "") + "|" + (r.get("author") or "")),
    ]:
        c = Counter(keyfn(r) for r in rows if keyfn(r) not in (None, "", "|"))
        dups = {k: v for k, v in c.items() if v > 1}
        L("- %s 중복: %d종 / 초과행 %d" % (keyname, len(dups), sum(v - 1 for v in dups.values())))
    L("")

    # 카테고리 분포
    L("## 카테고리 분포")
    L("")
    L("### 2단계 그룹 요약 (국내도서>장르)")
    L("")
    cat2 = Counter(">".join((r.get("category") or "(none)").split(">")[:2]) for r in rows)
    for cat, cnt in cat2.most_common(40):
        L("- %-30s %4d (%.1f%%)" % (cat, cnt, 100.0 * cnt / n))
    L("")
    L("### 상세(세분류 포함)")
    L("")
    cats = Counter(r.get("category") or "(none)" for r in rows)
    for cat, cnt in cats.most_common(30):
        L("- %-56s %4d (%.1f%%)" % (cat, cnt, 100.0 * cnt / n))
    L("- ... 외 %d개 세분류" % max(0, len(cats) - 30))
    L("")

    # 숫자 통계
    L("## 수치 통계")
    L("")

    def stats(field, fmt="%s"):
        vals = [r.get(field) for r in rows if isinstance(r.get(field), (int, float))]
        if not vals:
            return "없음(n=0)"
        vals_sorted = sorted(vals)
        return "n=%d min=%s median=%s max=%s mean=%.2f" % (
            len(vals), fmt % vals_sorted[0], fmt % statistics.median(vals_sorted),
            fmt % vals_sorted[-1], sum(vals) / len(vals))

    L("- price: %s" % stats("price"))
    L("- price_list: %s" % stats("price_list"))
    L("- rating: %s" % stats("rating"))
    years = Counter((r.get("pubdate") or "")[:4] for r in rows if r.get("pubdate"))
    L("- pubdate 연도 분포: %s" % dict(years.most_common(12)))
    L("- source 분포: %s" % dict(Counter(r.get("source") for r in rows).most_common()))
    L("")

    # 한글 정상 여부
    L("## 한글/URL 정상성")
    L("")
    title_ko = sum(1 for r in rows if HANGUL.search(r.get("title") or ""))
    author_ko = sum(1 for r in rows if HANGUL.search(r.get("author") or ""))
    cover_ok = sum(1 for r in rows if (r.get("cover_url") or "").startswith("http"))
    link_ok = sum(1 for r in rows if (r.get("link") or "").startswith("http"))
    L("- title에 한글 포함: %d/%d (%.1f%%)" % (title_ko, n, 100.0 * title_ko / n))
    L("- author에 한글 포함: %d/%d (%.1f%%)" % (author_ko, n, 100.0 * author_ko / n))
    L("- cover_url http(s): %d/%d (%.1f%%)" % (cover_ok, n, 100.0 * cover_ok / n))
    L("- link http(s): %d/%d (%.1f%%)" % (link_ok, n, 100.0 * link_ok / n))
    noimg = [r for r in rows if r.get("cover_url") and "Noimg" in r["cover_url"]]
    L("- Noimg 표지: %d" % len(noimg))
    L("")

    # 샘플 5권 (원문 JSONL 라인 그대로)
    L("## 샘플 5권 (JSONL 원문 라인)")
    L("")
    L("```jsonl")
    for r in rows[:5]:
        L(json.dumps({k: r.get(k) for k in FIELDS}, ensure_ascii=False))
    L("```")
    L("")

    # 수용 기준 판정
    L("## 수용 기준 판정")
    L("")
    L("- 행 수 ≥ 1500: %s (%d)" % ("PASS" if n >= 1500 else "FAIL", n))
    L("- title 결측률 < 3%%: %s (%.2f%%)" % ("PASS" if miss_pct["title"] < 3 else "FAIL", miss_pct["title"]))
    L("- cover_url 결측률 < 3%%: %s (%.2f%%)" % ("PASS" if miss_pct["cover_url"] < 3 else "FAIL", miss_pct["cover_url"]))
    L("- id 중복 0: %s" % ("PASS" if len({r.get('id') for r in rows}) == n else "FAIL"))

    summary = {
        "rows": n,
        "missing_pct": miss_pct,
        "unique_ids": len({r.get("id") for r in rows}),
        "categories": dict(cats.most_common(40)),
        "source": dict(Counter(r.get("source") for r in rows).most_common()),
        "title_hangul_pct": round(100.0 * title_ko / n, 2),
        "cover_http_pct": round(100.0 * cover_ok / n, 2),
    }
    return "\n".join(out) + "\n", summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="catalog.jsonl 검증 리포트")
    ap.add_argument("--file", default=os.path.join(PROJECT_ROOT, "data", "catalog.jsonl"))
    ap.add_argument("--report", default=os.path.join(RESEARCH_DIR, "verify_report.txt"))
    ap.add_argument("--json", default=os.path.join(RESEARCH_DIR, "verify_report.json"))
    args = ap.parse_args(argv)

    rows = load_rows(args.file)
    text, summary = build_report(rows, args.file)
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with io.open(args.report, "w", encoding="utf-8") as f:
        f.write(text)
    with io.open(args.json, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print("wrote %s (%d rows)" % (args.report, len(rows)))
    print("wrote %s" % args.json)
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
