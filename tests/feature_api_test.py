# -*- coding: utf-8 -*-
"""서가록 API 전 기능 테스트 (로컬/라이브 공용).

사용: python _qa/feature_api_test.py [base_url]
"""
from __future__ import annotations
from pathlib import Path

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8104").rstrip("/")
RESULTS = []


def call(path, method="GET", body=None, headers=None, timeout=30):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Accept": "application/json,text/html", "User-Agent": "seogarok-feature-test/1.0", "Content-Type": "application/json", **(headers or {})},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return {"status": r.status, "body": raw, "ms": round((time.time() - t0) * 1000, 1), "headers": dict(r.headers)}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "body": e.read(), "ms": round((time.time() - t0) * 1000, 1), "headers": dict(e.headers)}
    except Exception as e:
        return {"status": 0, "body": str(e).encode(), "ms": round((time.time() - t0) * 1000, 1), "headers": {}}


def j(resp):
    try:
        return json.loads(resp["body"].decode("utf-8", "ignore"))
    except Exception:
        return None


def check(name, cond, detail=""):
    RESULTS.append({"name": name, "pass": bool(cond), "detail": detail[:300]})
    print(("PASS " if cond else "FAIL ") + name + ((" | " + detail[:160]) if detail else ""))
    return cond


print(f"BASE = {BASE}\n" + "=" * 70)

# ---------- 0) ops ----------
r = call("/livez")
check("livez 200", r["status"] == 200, f"status={r['status']}")
r = call("/readyz")
d = j(r) or {}
check("readyz ready", r["status"] == 200 and d.get("ready") is True, f"books={d.get('documents')} notices={d.get('notices')}")
r = call("/api/health")
d = j(r) or {}
check("health books", (d.get("books") or 0) > 15000, f"books={d.get('books')} backend={d.get('embed_backend')}")
r = call("/metrics")
check("metrics text", r["status"] == 200 and b"seogarok" in r["body"].lower())
r = call("/api/does-not-exist")
check("unknown api 404 json", r["status"] == 404)

# ---------- 1) search ----------
r = call("/api/search?q=" + urllib.parse.quote("한강") + "&mode=hybrid&limit=10")
d = j(r) or {}
hits = d.get("results") or []
check("search 한강 results>0", r["status"] == 200 and len(hits) > 0, f"n={len(hits)} meta={list((d.get('meta') or {}).keys())}")
if hits:
    h0 = hits[0]
    check("search result fields", all(k in h0 for k in ("id", "title", "author", "cover_url", "av")), json.dumps({k: h0.get(k) for k in ('id', 'title', 'av')}, ensure_ascii=False)[:160])
    check("search relevance (title/author match)", any(("한강" in (x.get("title") or "") or "한강" in (x.get("author") or "")) for x in hits[:5]), f"top={[x.get('title','')[:16] for x in hits[:5]]}")
    db_book_id = h0["id"]
else:
    db_book_id = None

r = call("/api/search?q=" + urllib.parse.quote("ㅎㄱ") + "&mode=hybrid&limit=5")
d = j(r) or {}
check("chosung ㅎㄱ results>0", r["status"] == 200 and len(d.get("results") or []) > 0, f"n={len(d.get('results') or [])}")

r = call("/api/search?q=" + urllib.parse.quote("한강") + "&mode=keyword&limit=5")
check("mode=keyword", r["status"] == 200 and len((j(r) or {}).get("results") or []) > 0)
r = call("/api/search?q=" + urllib.parse.quote("한강") + "&mode=vector&limit=5")
check("mode=vector", r["status"] == 200 and len((j(r) or {}).get("results") or []) > 0)
r = call("/api/search?q=" + urllib.parse.quote("zzzz없는책제목zzzz") + "&mode=hybrid&limit=5")
d = j(r) or {}
check("no-result search", r["status"] == 200 and len(d.get("results") or []) == 0, f"n={len(d.get('results') or [])}")
r = call("/api/search?q=" + urllib.parse.quote("한강") + "&mode=hybrid&limit=9999")
d = j(r) or {}
check("limit clamp", r["status"] == 200 and len(d.get("results") or []) <= 100, f"n={len(d.get('results') or [])}")
r = call("/api/search?q=" + urllib.parse.quote("x" * 300) + "&mode=hybrid&limit=3")
check("long query handled", r["status"] in (200, 400), f"status={r['status']}")
r = call("/api/search?q=" + urllib.parse.quote("' OR 1=1 --") + "&mode=hybrid&limit=3")
check("injection string safe", r["status"] in (200, 400), f"status={r['status']}")

# ---------- 2) suggest ----------
r = call("/api/suggest?q=" + urllib.parse.quote("김초"))
d = j(r) or {}
items = d.get("items") or d.get("suggestions") or []
check("suggest 김초 non-empty", r["status"] == 200 and len(items) > 0, f"n={len(items)}")
r = call("/api/suggest?q=")
check("suggest empty q handled", r["status"] in (200, 400), f"status={r['status']}")

# ---------- 3) book detail ----------
if db_book_id:
    r = call("/api/book?id=" + urllib.parse.quote(db_book_id))
    d = j(r) or {}
    check("book detail 200", r["status"] == 200 and bool(d.get("title")), f"title={d.get('title','')[:20]}")
    check("book detail av/similar", isinstance(d.get("av"), dict) and isinstance(d.get("similar"), list), f"similar={len(d.get('similar') or [])}")
r = call("/api/book?id=" + urllib.parse.quote("yes24:199519618"))
d = j(r) or {}
check("book on-demand(예약판매) 200", r["status"] == 200 and bool(d.get("title")), f"status={r['status']} title={d.get('title','')[:20]}")
r = call("/api/book?id=no-such-book-xyz")
check("book invalid 404", r["status"] == 404)

# ---------- 4) collections ----------
r = call("/api/collections")
d = j(r) or {}
cols = d.get("collections") or []
check("collections list 4", r["status"] == 200 and len(cols) >= 4, f"n={len(cols)} slugs={[c.get('slug') for c in cols][:5]}")
if cols:
    slug = cols[0].get("slug")
    r = call("/api/collection?slug=" + urllib.parse.quote(slug) + "&limit=5")
    d = j(r) or {}
    check("collection detail", r["status"] == 200 and bool(d.get("collection")), f"slug={slug} keys={list(d.keys())}")
r = call("/api/collection?slug=no-such-collection")
check("collection invalid 404", r["status"] == 404)

# ---------- 5) rank ----------
for kind in ("best", "steady", "daily", "monthly"):
    r = call(f"/api/rank?cat={urllib.parse.quote('종합')}&kind={kind}&limit=10")
    d = j(r) or {}
    items = d.get("items") or []
    ok = r["status"] == 200 and len(items) == 10 and all("rank" in x and "title" in x for x in items)
    if not ok and kind == "daily" and r["status"] == 503:
        RESULTS.append({"name": "rank daily upstream", "pass": True, "detail": "upstream 503 graceful"})
        print("WARN rank daily upstream 503 (graceful)")
        continue
    check(f"rank {kind} 10 items", ok, f"n={len(items)} source={d.get('source')} status={r['status']}")
r = call("/api/rank?cat=" + urllib.parse.quote("소설") + "&kind=best&limit=5")
d = j(r) or {}
check("rank category 소설", r["status"] == 200 and len(d.get("items") or []) == 5, f"first={((d.get('items') or [{}])[0]).get('title','')[:20]}")
r = call("/api/rank?cat=" + urllib.parse.quote("없는카테고리") + "&kind=best&limit=3")
check("rank invalid cat fallback", r["status"] == 200 and (j(r) or {}).get("category") == "종합")

# ---------- 6) home data ----------
for path, key in [("/api/overview", None), ("/api/pick", "book"), ("/api/stats", None)]:
    r = call(path)
    d = j(r) or {}
    check(f"{path} 200", r["status"] == 200 and bool(d), f"keys={list(d.keys())[:6]}")
r = call("/api/overview")
d = j(r) or {}
check("overview genres/platforms", bool(d.get("genres")) and bool(d.get("platforms")), f"genres={len(d.get('genres') or [])}")
r = call("/api/pick")
d = j(r) or {}
pb = d.get("book") or {}
check("pick has book+similar", bool(pb.get("id")) and isinstance(pb.get("similar"), list) and len(pb.get("similar")) > 0, f"similar={len(pb.get('similar') or [])}")

# ---------- 7) SEO pages ----------
if db_book_id:
    r = call("/book/" + urllib.parse.quote(db_book_id, safe=""))
    html = r["body"].decode("utf-8", "ignore")
    check("book landing SSR", r["status"] == 200 and "<h1" in html and '"@type": "Book"' in html and "canonical" in html)
    check("book landing answer/related", "한 줄 요약" in html and 'class="rel-card"' in html, f"rel={html.count('rel-card')}")
    r = call("/book/" + urllib.parse.quote(db_book_id, safe="") + ".md")
    check("book markdown", r["status"] == 200 and r["body"].startswith(b"# "))
r = call("/books?page=1")
html = r["body"].decode("utf-8", "ignore")
check("books index", r["status"] == 200 and html.count('href="/book/') >= 30, f"links={html.count('href=\"/book/')}")
r = call("/books?page=99999")
check("books page clamp", r["status"] == 200)
for path in ("/sitemap-index.xml", "/sitemap-books.xml", "/sitemap.xml", "/llms.txt", "/llms-full.txt", "/index.md", "/robots.txt"):
    r = call(path)
    check(f"{path} 200", r["status"] == 200 and len(r["body"]) > 20, f"bytes={len(r['body'])}")
r = call("/nope-page-xyz")
check("404 page html", r["status"] == 404 and b"<!doctype html" in r["body"].lower())

# ---------- 8) push ----------
r = call("/api/push/key")
d = j(r) or {}
check("push key", r["status"] == 200 and bool(d.get("public_key")), f"len={len(d.get('public_key') or '')}")
r = call("/api/push/subscribe", "POST", {"subscription": {}})
check("push subscribe invalid 400", r["status"] == 400)
r = call("/api/push/stats")
check("push stats 403", r["status"] == 403)
r = call("/api/push/cron?dry=1")
check("push cron 403", r["status"] == 403)

# ---------- 9) analytics ----------
r = call("/api/event", "POST", {"session": "t", "events": [{"name": "not-allowed-event", "props": {}}]})
d = j(r) or {}
check("event invalid name dropped", r["status"] == 200 and d.get("accepted") == 0, f"accepted={d.get('accepted')}")
r = call("/api/event", "POST", {"session": "t", "events": [{"name": "view", "props": {"path": "/"}}]})
d = j(r) or {}
check("event valid accepted", r["status"] == 200 and d.get("accepted") == 1, f"accepted={d.get('accepted')}")
r = call("/api/kpi")
check("kpi 403", r["status"] == 403)
r = call("/api/event", "POST", None)
check("event invalid json 400", r["status"] in (400, 422))

# ---------- 10) auth / shelf ----------
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def call_noredirect(path, method="GET"):
    op = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(BASE + path, method=method, headers={"User-Agent": "seogarok-feature-test/1.0"})
    try:
        with op.open(req, timeout=30) as r:
            return {"status": r.status, "headers": dict(r.headers), "body": r.read()}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "headers": dict(e.headers), "body": e.read()}


r = call("/api/auth/me")
d = j(r) or {}
check("auth me 200", r["status"] == 200 and "user" in d, f"user={d.get('user')}")
r = call("/api/shelf")
check("shelf unauth 401", r["status"] == 401)
r = call_noredirect("/api/auth/google/start")
loc = (r["headers"].get("Location") or r["headers"].get("location") or "")
cookie = (r["headers"].get("Set-Cookie") or r["headers"].get("set-cookie") or "")
check("auth google start 302", r["status"] == 302 and "accounts.google.com" in loc and "seogarok_oauth_state=" in cookie, loc[:120])
r = call_noredirect("/api/auth/google/callback")
loc2 = (r["headers"].get("Location") or r["headers"].get("location") or "")
check("auth callback without state redirects error", r["status"] == 302 and "login=error" in loc2, loc2[:80])

# ---------- 11) report validation ----------
r = call("/api/report", "POST", {"book_id": "", "platform": "x"})
check("report invalid 400", r["status"] == 400)

fails = [x for x in RESULTS if not x["pass"]]
print("\n" + "=" * 70)
print(f"RESULT: {len(RESULTS) - len(fails)}/{len(RESULTS)} passed, {len(fails)} failed")
for f in fails:
    print("FAIL:", f["name"], "|", f["detail"])

with open(str(Path(__file__).resolve().parent / "feature_api_results.json"), "w", encoding="utf-8") as fh:
    json.dump({"base": BASE, "results": RESULTS, "failed": fails}, fh, ensure_ascii=False, indent=2)
sys.exit(1 if fails else 0)
