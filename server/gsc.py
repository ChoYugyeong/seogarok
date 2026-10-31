# -*- coding: utf-8 -*-
"""GSC 자동화: 사이트맵 제출 + 색인/검색 성과 모니터링.

GCS의 auth/gsc_token.json(refresh token)으로 access token을 갱신한다.
쓰기 scope(webmasters)로 재연결된 경우에만 사이트맵 제출이 성공한다.
"""
from __future__ import annotations

import json
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from . import store
from .auth import GSC_SCOPE, GSC_TOKEN_PATH, config

SITE = "sc-domain:seogarok.com"
SITE_ENC = urllib.parse.quote(SITE, safe="")
TOKEN_URL = "https://oauth2.googleapis.com/token"
WEBMASTERS = "https://www.googleapis.com/webmasters/v3/sites/" + SITE_ENC
INSPECT_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"


class GscAuthError(RuntimeError):
    """재연결(refresh token) 또는 scope 부족."""


def _refresh_token() -> str:
    tok = store.read_json(GSC_TOKEN_PATH) or {}
    refresh = str(tok.get("refresh_token") or "").strip()
    cfg = config() or {}
    if not refresh or not cfg.get("client_id") or not cfg.get("client_secret"):
        raise GscAuthError("gsc_token_missing")
    data = urllib.parse.urlencode({
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "refresh_token": refresh,
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(
        TOKEN_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise GscAuthError("refresh_failed:" + str(e.code)) from e
    except Exception as e:  # noqa: BLE001
        raise GscAuthError("refresh_failed") from e
    token = body.get("access_token")
    if not token:
        raise GscAuthError("refresh_failed:no_access_token")
    return token


def _call(token: str, method: str, url: str, body: dict | None = None):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "ignore")
        if e.code == 403 and ("insufficient" in raw.lower() or "scope" in raw.lower()):
            raise GscAuthError("insufficient_scope") from e
        return e.code, {"error": raw[:300]}


def _sitemap_urls(limit: int = 8) -> list[str]:
    try:
        req = urllib.request.Request(
            "https://seogarok.com/sitemap-books.xml", headers={"User-Agent": "seogarok-gsc/1"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            xml = r.read().decode("utf-8", "ignore")
        locs = re.findall(r"<loc>(.*?)</loc>", xml)
    except Exception:
        locs = []
    random.seed(int(time.time()) // 86400)
    random.shuffle(locs)
    return locs[:limit]


def run(days: int = 7, sample: int = 5) -> dict:
    token = _refresh_token()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    submitted = []
    for feed in (
        "https://seogarok.com/sitemap-books.xml",
        "https://seogarok.com/sitemap.xml",
        "https://seogarok.com/sitemap-index.xml",
    ):
        path = "/sitemaps/" + urllib.parse.quote(feed, safe="")
        status, body = _call(token, "PUT", WEBMASTERS + path)
        submitted.append({"feed": feed, "status": status, "ok": status in (200, 204), "body": body})

    sitemap_status, sitemaps = _call(token, "GET", WEBMASTERS + "/sitemaps")

    end = time.strftime("%Y-%m-%d", time.gmtime())
    start = time.strftime("%Y-%m-%d", time.gmtime(time.time() - max(1, days) * 86400))
    analytics = {}
    for dims_name, dims in (("by_date", ["date"]), ("by_page", ["page"]), ("by_query", ["query"])):
        st, data = _call(token, "POST", WEBMASTERS + "/searchAnalytics/query", {
            "startDate": start, "endDate": end, "dimensions": dims, "rowLimit": 20,
        })
        analytics[dims_name] = (data.get("rows") or []) if st == 200 else []

    inspected = []
    urls = ["https://seogarok.com/"] + _sitemap_urls(sample)
    for url in urls:
        st, data = _call(token, "POST", INSPECT_URL, {"inspectionUrl": url, "siteUrl": SITE})
        res = (data.get("inspectionResult") or {}).get("indexStatusResult") or {}
        inspected.append({
            "url": url,
            "status": st,
            "verdict": res.get("verdict") or "UNKNOWN",
            "coverage": res.get("coverageState") or "",
            "last_crawl": (res.get("lastCrawlTime") or "")[:10],
        })

    report = {
        "at": now,
        "site": SITE,
        "scope": GSC_SCOPE,
        "sitemaps_submitted": submitted,
        "sitemaps_status": sitemap_status,
        "sitemaps": (sitemaps.get("sitemap") or []) if isinstance(sitemaps, dict) else [],
        "analytics": analytics,
        "inspected": inspected,
        "index_verdicts": {
            v: sum(1 for x in inspected if x["verdict"] == v)
            for v in sorted({x["verdict"] for x in inspected})
        },
    }
    try:
        store.write_json("reports/gsc/" + end + ".json", report)
    except Exception:
        pass
    return report
