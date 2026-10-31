# -*- coding: utf-8 -*-
"""AI/검색 크롤러 데일리 리포트 생성."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def read_json(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--surfaces", default="/tmp/surfaces.json")
    ap.add_argument("--gsc", default="/tmp/gsc.json")
    ap.add_argument("--indexnow", default="/tmp/indexnow.txt")
    ap.add_argument("--out", default="/tmp/ai-report.md")
    args = ap.parse_args()

    surfaces = read_json(args.surfaces)
    gsc = read_json(args.gsc)
    try:
        indexnow = Path(args.indexnow).read_text(encoding="utf-8").strip()
    except Exception:
        indexnow = "(IndexNow 출력 없음)"

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"# AI crawl daily · {today}", ""]

    lines += ["## AI/search surfaces", ""]
    labels = {
        "robots": "robots.txt",
        "llms": "llms.txt",
        "llms_full": "llms-full.txt",
        "sitemap_index": "sitemap-index.xml",
        "sitemap_books": "sitemap-books.xml",
    }
    for key, label in labels.items():
        n = surfaces.get(key)
        lines.append(f"- {label}: " + (f"{n:,} bytes" if isinstance(n, int) else "**missing**"))
    lines += ["", "## IndexNow", "", "```", indexnow[:1200], "```", ""]

    lines += ["## Google Search Console", ""]
    if not gsc:
        lines.append("- GSC 응답 없음")
    elif gsc.get("error") == "gsc_reauth":
        lines.append(f"- ⚠️ 재연결 필요: `{gsc.get('message')}`")
        lines.append("- `/api/auth/gsc/start` 재승인 후 사이트맵 자동 제출이 켜진다.")
    elif gsc.get("error"):
        lines.append(f"- ⚠️ GSC 오류: `{gsc.get('error')}`")
    else:
        subs = gsc.get("sitemaps_submitted") or []
        ok = sum(1 for x in subs if x.get("ok"))
        lines.append(f"- 사이트맵 자동 제출: {ok}/{len(subs)} 성공")
        for s in subs:
            lines.append(f"  - `{s.get('feed')}` → HTTP {s.get('status')}")
        for sm in gsc.get("sitemaps") or []:
            contents = sm.get("contents") or []
            lines.append(f"- 제출된 사이트맵: `{sm.get('path')}` · downloaded {str(sm.get('lastDownloaded'))[:10]}")
            for c in contents:
                lines.append(f"  - submitted {c.get('submitted')} / indexed {c.get('indexed')}")
        by_date = (gsc.get("analytics") or {}).get("by_date") or []
        clicks = sum(x.get("clicks", 0) for x in by_date)
        impr = sum(x.get("impressions", 0) for x in by_date)
        lines.append(f"- 검색 성과(최근 7일): clicks {clicks} · impressions {impr}")
        verdicts = gsc.get("index_verdicts") or {}
        if verdicts:
            lines.append("- URL 검사 표본 verdict: " + ", ".join(f"{k} {v}" for k, v in verdicts.items()))
        for x in (gsc.get("inspected") or [])[:6]:
            lines.append(f"  - {x.get('verdict')} · {x.get('coverage')} · {x.get('url')}")

    lines += ["", "## 다음 액션", ""]
    lines.append("- [ ] GSC 재연결(쓰기 scope) 후 사이트맵 자동 제출 확인")
    lines.append("- [ ] 색인 안 된 대표 책 URL Inspect → 색인 요청 (Google UI)")
    lines.append("- [ ] 네이버 서치어드바이저 사이트맵/수집 요청")
    lines.append("- [ ] 절판/품절 감시 cron 결과 확인 (status-watch)")

    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"report: {args.out} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
