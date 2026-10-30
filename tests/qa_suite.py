# -*- coding: utf-8 -*-
"""서가록 경쟁력 QA — 서버/SEO/정적/PWA/부하 (라이브 대상).

실행: python _qa/qa_suite.py [base_url]
결과: JSON 출력 + _qa/qa_report.json 저장
"""
from __future__ import annotations
from pathlib import Path

import concurrent.futures
import json
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://seogarok.com").rstrip("/")
OUT = {}
FAILS = []
WARNS = []


def fetch(path, method="GET", body=None, timeout=30):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Accept": "application/json,text/html", "User-Agent": "seogarok-qa/1.0", "Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return {"status": r.status, "ms": round((time.time() - t0) * 1000, 1), "headers": dict(r.headers), "body": raw, "ctype": r.headers.get("Content-Type", "")}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "ms": round((time.time() - t0) * 1000, 1), "headers": dict(e.headers), "body": e.read(), "ctype": e.headers.get("Content-Type", "")}
    except Exception as e:
        return {"status": 0, "ms": round((time.time() - t0) * 1000, 1), "headers": {}, "body": str(e).encode(), "ctype": ""}


# ---------------- 1) API smoke ----------------
smoke = [
    "/livez", "/readyz", "/api/health", "/metrics",
    "/api/search?q=" + urllib.parse.quote("한강") + "&mode=hybrid&limit=5",
    "/api/search?q=" + urllib.parse.quote("ㅎㄱ") + "&mode=hybrid&limit=5",
    "/api/suggest?q=" + urllib.parse.quote("김초"),
    "/api/overview", "/api/pick", "/api/stats",
    "/api/notices?limit=5",
    "/api/collections",
    "/api/collection?slug=snu-100&limit=5",
    "/api/rank?cat=" + urllib.parse.quote("종합") + "&kind=best&limit=10",
    "/api/rank?cat=" + urllib.parse.quote("소설") + "&kind=steady&limit=10",
    "/api/book?id=" + urllib.parse.quote("yes24:197068949"),
    "/api/book?id=" + urllib.parse.quote("yes24:199519618"),
    "/book/" + urllib.parse.quote("yes24:197068949", safe=""),
    "/book/" + urllib.parse.quote("yes24:197068949", safe="") + ".md",
    "/sitemap-books.xml",
    "/sitemap-index.xml",
    "/llms.txt",
    "/llms-full.txt",
    "/index.md",
    "/api/push/key",
    "/api/nope",  # 404 기대
]
results = []
for path in smoke:
    samples = [fetch(path) for _ in range(3)]
    s = samples[-1]
    expected = 404 if path == "/api/nope" else 200
    ok = s["status"] == expected
    if path.endswith("199519618") and s["status"] == 404:
        ok = True
        WARNS.append("온디맨드 외부 도서 404 (YES24 한도/미제공) — 허용")
    if path == "/api/push/key" and s["status"] == 503:
        ok = True
        WARNS.append("푸시 키 미구성(503) — cryptography/pywebpush 설치 확인")
    if not ok:
        FAILS.append(f"API {path} → {s['status']} (기대 {expected})")
    results.append({
        "path": path,
        "status": s["status"],
        "ms_p50": round(statistics.median([x["ms"] for x in samples]), 1),
        "ok": ok,
        "ctype": s["ctype"][:40],
    })
OUT["api_smoke"] = results

# ---------------- 2) 보안 헤더 ----------------
home = fetch("/")
hdrs = {k.lower(): v for k, v in home["headers"].items()}
want = {
    "x-content-type-options": "nosniff",
    "referrer-policy": None,
    "x-frame-options": None,
    "permissions-policy": None,
}
sec = {}
for k in want:
    sec[k] = hdrs.get(k)
    if not hdrs.get(k):
        FAILS.append(f"보안 헤더 누락: {k}")
    else:
        # 기능 확인용 존재만 체크 … 값이 비정상이면 WARN
        pass
sec["content-encoding"] = hdrs.get("content-encoding")
sec["cache_control_html"] = hdrs.get("cache-control")
sec["server"] = hdrs.get("server")
if "hsts" not in "".join(hdrs.keys()) and "strict-transport-security" not in hdrs:
    WARNS.append("Strict-Transport-Security(HSTS) 헤더 없음 (Cloud Run 기본 미설정)")
OUT["security_headers"] = sec

# ---------------- 3) SEO / 메타 ----------------
html = home["body"].decode("utf-8", "ignore")
meta = {}
for key, needle in [
    ("title", "<title>"),
    ("description", 'name="description"'),
    ("canonical", 'rel="canonical"'),
    ("og_title", 'property="og:title"'),
    ("og_image", 'property="og:image"'),
    ("og_url", 'property="og:url"'),
    ("twitter", 'name="twitter:card"'),
    ("jsonld", 'application/ld+json'),
    ("og_site", 'property="og:site_name"'),
]:
    meta[key] = needle in html
    if key in ("title", "description", "canonical", "og_title", "og_image", "jsonld"):
        if not meta[key]:
            FAILS.append(f"SEO 누락: {key}")
if html.count("<h1") != 1:
    WARNS.append(f"h1 개수 {html.count('<h1')} (1개 권장)")
meta["h1_count"] = html.count("<h1")
meta["html_bytes"] = len(home["body"])
OUT["seo"] = meta

# robots / sitemap
robots = fetch("/robots.txt")
_robots_txt = robots["body"].decode("utf-8", "ignore")
OUT["robots"] = {
    "status": robots["status"],
    "bytes": len(robots["body"]),
    "content_signal": "Content-Signal:" in _robots_txt,
    "ai_groups": any(tok in _robots_txt for tok in ("GPTBot", "ClaudeBot", "PerplexityBot")),
    "sitemap_index": "sitemap-index.xml" in _robots_txt,
}
if not OUT["robots"]["content_signal"]:
    FAILS.append("robots.txt Content-Signal 누락")
if not OUT["robots"]["ai_groups"]:
    WARNS.append("robots.txt AI 에이전트 그룹 없음")
if not OUT["robots"]["sitemap_index"]:
    WARNS.append("robots.txt sitemap-index 미선언")
if robots["status"] != 200:
    FAILS.append("robots.txt 404")
sm = fetch("/sitemap.xml")
sitemap = {"status": sm["status"], "urls": 0, "valid_xml": False}
if sm["status"] == 200:
    try:
        root = ET.fromstring(sm["body"])
        urls = [u for u in root.iter() if u.tag.endswith("loc")]
        sitemap["valid_xml"] = True
        sitemap["urls"] = len(urls)
    except Exception as e:
        FAILS.append(f"sitemap.xml 파싱 실패: {e}")
else:
    FAILS.append("sitemap.xml 404")
books_sm = fetch("/sitemap-books.xml")
if books_sm["status"] == 200:
    try:
        brows = ET.fromstring(books_sm["body"])
        sitemap["book_urls"] = len([u for u in brows.iter() if u.tag.endswith("loc")])
    except Exception:
        FAILS.append("sitemap-books.xml 파싱 실패")
else:
    FAILS.append("sitemap-books.xml 404")
OUT["sitemap"] = sitemap

# ---------------- 4) 정적 자산 ----------------
assets = ["/styles.css", "/app.js", "/data.js", "/manifest.webmanifest", "/sw.js", "/icons/icon-192.png", "/icons/icon-512.png", "/404.html", "/about.html", "/legal.html"]
asset_rows = []
for a in assets:
    r = fetch(a)
    ok = r["status"] == 200 and len(r["body"]) > 0
    if not ok:
        FAILS.append(f"정적 자산 {a} → {r['status']}")
    asset_rows.append({"path": a, "status": r["status"], "bytes": len(r["body"]), "ctype": r["ctype"][:30]})
OUT["assets"] = asset_rows

# llms.txt 규칙 (claude-seo Lighthouse llms-txt)
try:
    _llms_resp = fetch("/llms.txt")
    st, _b = _llms_resp["status"], _llms_resp["body"]
except Exception:
    st = 0
if st == 200:
    _txt = _b.decode("utf-8", "ignore")
    _ok = bool(__import__("re").search(r"^\s*#\s+.+", _txt, __import__("re").M)) and "](" in _txt and len(_txt) >= 50
    OUT["llms_txt"] = {"status": st, "bytes": len(_txt), "valid": _ok}
    if not _ok:
        FAILS.append("llms.txt H1/링크/길이 규칙 미충족")
else:
    OUT["llms_txt"] = {"status": st, "valid": False}
    FAILS.append("llms.txt 404")

# PWA manifest
man = fetch("/manifest.webmanifest")
manifest_ok = False
if man["status"] == 200:
    try:
        m = json.loads(man["body"].decode("utf-8"))
        icons = m.get("icons") or []
        manifest_ok = bool(m.get("name") and m.get("start_url") and m.get("display") and icons)
        OUT["pwa"] = {
            "name": m.get("name"),
            "display": m.get("display"),
            "start_url": m.get("start_url"),
            "icons": len(icons),
            "theme": m.get("theme_color"),
            "bg": m.get("background_color"),
            "sw_cached": "seogarok" in fetch("/sw.js")["body"].decode("utf-8", "ignore"),
        }
        if not manifest_ok:
            FAILS.append("manifest 필수 필드 누락")
    except Exception as e:
        FAILS.append(f"manifest 파싱 실패: {e}")
else:
    FAILS.append("manifest 404")

# ---------------- 5) 부하 테스트 ----------------
load_paths = [
    "/api/search?q=" + urllib.parse.quote(q) + "&mode=hybrid&limit=10"
    for q in ["한강", "김초엽", "SF", "에세이", "심리", "역사", "경제", "여행"]
] + ["/api/rank?cat=" + urllib.parse.quote("종합") + "&kind=best&limit=10"] * 4 + ["/api/overview"] * 2
lat = []
errors = 0


def one(i):
    p = load_paths[i % len(load_paths)]
    r = fetch(p, timeout=30)
    return r["status"], r["ms"]


t0 = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
    for status, ms in ex.map(one, range(48)):
        lat.append(ms)
        if status != 200:
            errors += 1
dur = time.time() - t0
lat_sorted = sorted(lat)
p95 = lat_sorted[int(len(lat_sorted) * 0.95) - 1]
OUT["load"] = {
    "requests": len(lat),
    "workers": 12,
    "seconds": round(dur, 2),
    "rps": round(len(lat) / dur, 1),
    "p50_ms": round(statistics.median(lat), 1),
    "p95_ms": round(p95, 1),
    "max_ms": round(max(lat), 1),
    "errors": errors,
}
if errors:
    FAILS.append(f"부하 테스트 오류 {errors}건")
if p95 > 1500:
    WARNS.append(f"검색 p95 {p95}ms — 1.5s 초과")

OUT["fails"] = FAILS
OUT["warns"] = WARNS
print(json.dumps(OUT, ensure_ascii=False, indent=2)[:12000])

with open(str(Path(__file__).resolve().parent / "qa_report.json"), "w", encoding="utf-8") as f:
    json.dump(OUT, f, ensure_ascii=False, indent=2)
print("\nQA_SUMMARY", json.dumps({
    "fails": len(FAILS),
    "warns": len(WARNS),
    "api": len(results),
    "load_p95": OUT["load"]["p95_ms"],
    "fails_list": FAILS,
}, ensure_ascii=False))

if FAILS:
    print(f"\n❌ QA FAIL ({len(FAILS)}건)")
    raise SystemExit(1)
print(f"\n✅ QA PASS (warn {len(WARNS)}건)")
