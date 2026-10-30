"""Google Search Console URL Inspection API로 색인 상태 확인.

사용:
  python scripts/gsc_index_status.py                 # 핵심 URL + 책 표본 20
  python scripts/gsc_index_status.py --limit 50
  python scripts/gsc_index_status.py --urls https://seogarok.com/ ...

인증:
  gcloud auth print-access-token (로컬 로그인 또는 CI의 Workload Identity)
  ※ GSC 속성(sc-domain:seogarok.com)에 실행 계정이 사용자로 추가되어 있어야 함
"""
from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
import urllib.error
import urllib.request

SITE = "sc-domain:seogarok.com"
API = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"


def token() -> str:
    """우선순위: refresh token 교환 → GSC_ACCESS_TOKEN → gcloud."""
    refresh = (os.getenv("GSC_REFRESH_TOKEN") or "").strip()
    cid = (os.getenv("GSC_CLIENT_ID") or "").strip()
    csec = (os.getenv("GSC_CLIENT_SECRET") or "").strip()
    if refresh and cid and csec:
        data = urllib.parse.urlencode(
            {
                "client_id": cid,
                "client_secret": csec,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            }
        ).encode()
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode()).get("access_token", "")
        except Exception as exc:
            print(
                f"[gsc] refresh token 교환 실패: {str(exc)[:120]} — 재승인 필요(GSC 연결 링크 재발급)",
                file=sys.stderr,
            )
            sys.exit(2)

    env_tok = (os.getenv("GSC_ACCESS_TOKEN") or "").strip()
    if env_tok:
        return env_tok

    import shutil

    exe = None
    for cand in ("gcloud.cmd", "gcloud"):
        exe = shutil.which(cand)
        if exe:
            break
    if not exe:
        print("[gsc] gcloud 없음", file=sys.stderr)
        return ""
    out = subprocess.run(
        [exe, "auth", "print-access-token"], capture_output=True, text=True, timeout=60
    )
    return out.stdout.strip()


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "seogarok-gsc/1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "ignore")


def default_urls(limit: int) -> list[str]:
    core = ["https://seogarok.com/", "https://seogarok.com/books?page=1"]
    try:
        xml = fetch("https://seogarok.com/sitemap-books.xml")
        locs = re.findall(r"<loc>(.*?)</loc>", xml)
    except Exception:
        locs = []
    random.seed(42)
    random.shuffle(locs)
    return core + locs[:limit]


def inspect(tok: str, url: str) -> dict:
    payload = json.dumps({"inspectionUrl": url, "siteUrl": SITE}).encode("utf-8")
    req = urllib.request.Request(
        API,
        data=payload,
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="GSC URL Inspection")
    ap.add_argument("--limit", type=int, default=20, help="책 URL 표본")
    ap.add_argument("--urls", nargs="*", default=None)
    args = ap.parse_args(argv)

    tok = token()
    if not tok:
        print("[gsc] access token 없음 — gcloud auth login 필요")
        return 1
    urls = args.urls if args.urls else default_urls(args.limit)
    print(f"[gsc] inspecting {len(urls)} URLs (property {SITE})")

    counts: dict[str, int] = {}
    rows = []
    for url in urls:
        try:
            data = inspect(tok, url)
            res = (data.get("inspectionResult") or {}).get("indexStatusResult") or {}
            verdict = res.get("verdict") or "UNKNOWN"
            coverage = res.get("coverageState") or ""
            last = (res.get("lastCrawlTime") or "")[:10]
            counts[verdict] = counts.get(verdict, 0) + 1
            rows.append({"url": url, "verdict": verdict, "coverage": coverage, "last_crawl": last})
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "ignore")[:200]
            hint = ""
            if exc.code == 403:
                hint = " → GSC 속성에 실행 계정을 사용자로 추가하세요 (Search Console → 설정 → 사용자 및 권한)"
            print(f"[gsc] {url} HTTP {exc.code}{hint} {body}")
            if exc.code == 403:
                return 0
        except Exception as exc:
            print(f"[gsc] {url} ERR {str(exc)[:100]}")

    print("\n[gsc] verdict counts:", counts)
    for row in rows:
        print(f"  {row['verdict']:10s} | {row['last_crawl'] or '-':10s} | {row['url']}")
        print(f"             coverage: {row['coverage']}")

    out = {"site": SITE, "counts": counts, "rows": rows}
    with open("gsc_index_status.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n[gsc] saved gsc_index_status.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
