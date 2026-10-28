# -*- coding: utf-8 -*-
"""fetch_base.py — 공통 HTTP 계층: robots.txt 판정, 인코딩 판별, 1.2s 레이트리밋, 원본 HTML 캐시.

설계 원칙
- robots.txt를 먼저 받아 우리 UA 그룹을 계산하고, Disallow 경로면 요청 자체를 하지 않는다.
- 응답은 bytes로 받아 utf-8 → cp949 → euc-kr 순으로 디코드하고 한글 마커로 판별한다.
- 원본 bytes는 `_cache/<sha1>.html`에, 메타는 `<sha1>.html.meta.json`에 저장한다. 캐시가 있으면 네트워크 요청 금지.
- 네트워크 요청 사이 간격은 최소 `min_interval`초(기본 1.2s). 캐시 히트는 간격에 영향 없음.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import time
from typing import Optional
from urllib.parse import urlparse

import requests

DEFAULT_UA = "seoga-research-bot/0.1 (+demo; contact: local)"
DEFAULT_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cache")
KOREAN_MARKERS = ("베스트", "소설", "도서", "저자", "출판")


class RobotsDisallowed(RuntimeError):
    """robots.txt가 해당 경로를 금지할 때."""


# --------------------------------------------------------------------------- #
# 인코딩
# --------------------------------------------------------------------------- #
def decode_html(content: bytes, content_type: Optional[str] = None) -> tuple[str, str]:
    """bytes → (text, encoding). utf-8 우선, 한글 마커 없으면 cp949/euc-kr 시도."""
    candidates = []
    if content_type:
        m = re.search(r"charset=([\w\-]+)", content_type, re.I)
        if m:
            candidates.append(m.group(1).lower())
    # meta charset 스니핑 (ascii 범위만 검사)
    head = content[:4096].decode("ascii", "ignore")
    m = re.search(r"charset\s*=\s*[\"']?([\w\-]+)", head, re.I)
    if m:
        candidates.append(m.group(1).lower())
    candidates += ["utf-8", "cp949", "euc-kr"]

    seen = set()
    fallback = None
    for enc in candidates:
        if enc in seen:
            continue
        seen.add(enc)
        try:
            text = content.decode(enc, errors="strict")
        except (UnicodeDecodeError, LookupError):
            continue
        if fallback is None:
            fallback = (text, enc)
        if any(mk in text for mk in KOREAN_MARKERS):
            return text, enc
    if fallback is not None:
        return fallback
    return content.decode("utf-8", errors="replace"), "utf-8/replace"


# --------------------------------------------------------------------------- #
# robots.txt (RFC 9309)
# --------------------------------------------------------------------------- #
def parse_robots(text: str) -> list[dict]:
    """robots.txt → [{'agents': [...], 'rules': [(key, value)], 'start': line_no}]."""
    groups: list[dict] = []
    cur: Optional[dict] = None
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        key, _, val = line.partition(":")
        key = key.strip().lower()
        val = val.strip()
        if key == "user-agent":
            if cur is None or cur["rules"]:
                cur = {"agents": [], "rules": []}
                groups.append(cur)
            cur["agents"].append(val)
        elif key in ("allow", "disallow", "crawl-delay") and cur is not None:
            cur["rules"].append((key, val))
    return groups


class RobotsPolicy:
    """특정 UA에 적용되는 robots.txt 규칙. 명명 그룹은 UA 문자열 매칭으로 선택, 없으면 `*`."""

    def __init__(self, text: str, ua: str, robots_url: str = ""):
        self.text = text
        self.ua = ua
        self.robots_url = robots_url
        self.groups = parse_robots(text)
        self.group = self._select_group()
        self.crawl_delay = 0.0
        for k, v in (self.group or {}).get("rules", []):
            if k == "crawl-delay":
                try:
                    self.crawl_delay = float(v)
                except ValueError:
                    pass

    def _select_group(self) -> Optional[dict]:
        ua_l = self.ua.lower()
        best = None
        best_len = -1
        for g in self.groups:
            for a in g["agents"]:
                if a == "*":
                    if best is None and best_len < 0:
                        best = g
                        best_len = 0
                else:
                    tok = a.lower()
                    if tok and tok in ua_l and len(tok) > best_len:
                        best = g
                        best_len = len(tok)
        return best

    def _match_len(self, pattern: str, path: str) -> int:
        if not pattern:
            return -1
        pat = pattern
        if pat.startswith("http://") or pat.startswith("https://"):
            # 절대 URL 규칙은 path+query 로 축약해 비교
            p = urlparse(pat)
            pat = p.path + (("?" + p.query) if p.query else "")
        anchored_end = pat.endswith("$")
        if anchored_end:
            pat = pat[:-1]
        regex = re.escape(pat).replace(r"\*", ".*")
        if anchored_end:
            regex = regex + "$"
        return len(pattern) if re.match(regex, path) else -1

    def can_fetch(self, url: str) -> bool:
        if self.group is None:
            return True
        p = urlparse(url)
        path = p.path or "/"
        if p.query:
            path += "?" + p.query
        best_len = -1
        best_allow = True
        for k, v in self.group["rules"]:
            if k == "crawl-delay" or v == "":
                continue
            ln = self._match_len(v, path)
            if ln < 0:
                continue
            allow = k == "allow"
            if ln > best_len or (ln == best_len and allow):
                best_len = ln
                best_allow = allow
        return best_allow

    def summary(self) -> dict:
        return {
            "robots_url": self.robots_url,
            "ua": self.ua,
            "matched_agents": (self.group or {}).get("agents"),
            "crawl_delay": self.crawl_delay,
            "rules": (self.group or {}).get("rules"),
        }


# --------------------------------------------------------------------------- #
# 캐시 + 페처
# --------------------------------------------------------------------------- #
class FetchResult:
    __slots__ = ("url", "text", "encoding", "status", "from_cache", "fetched_at", "meta")

    def __init__(self, url, text, encoding, status, from_cache, fetched_at, meta):
        self.url = url
        self.text = text
        self.encoding = encoding
        self.status = status
        self.from_cache = from_cache
        self.fetched_at = fetched_at
        self.meta = meta

    def __repr__(self):
        return "<FetchResult %s status=%s cache=%s enc=%s>" % (
            self.url, self.status, self.from_cache, self.encoding)


class Fetcher:
    def __init__(self, cache_dir: str = DEFAULT_CACHE_DIR, ua: str = DEFAULT_UA,
                 min_interval: float = 1.2, timeout: float = 40.0, logger=None):
        self.cache_dir = cache_dir
        self.ua = ua
        self.min_interval = max(0.0, float(min_interval))
        self.timeout = timeout
        self.log = logger or (lambda *a: None)
        self._last_request_at = 0.0
        self.request_count = 0
        self.cache_hits = 0
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
        })
        os.makedirs(self.cache_dir, exist_ok=True)

    # -- cache helpers ---------------------------------------------------- #
    def cache_paths(self, url: str) -> tuple[str, str]:
        key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        base = os.path.join(self.cache_dir, key)
        return base + ".html", base + ".html.meta.json"

    def _load_cache(self, url: str) -> Optional[FetchResult]:
        html_path, meta_path = self.cache_paths(url)
        if not (os.path.exists(html_path) and os.path.exists(meta_path)):
            return None
        try:
            with io.open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            with io.open(html_path, "rb") as f:
                raw = f.read()
        except Exception as e:
            self.log("cache read failed for %s: %s" % (url, e))
            return None
        text, enc = decode_html(raw, meta.get("content_type"))
        self.cache_hits += 1
        return FetchResult(url, text, enc, meta.get("status"), True, meta.get("fetched_at"), meta)

    def _save_cache(self, url: str, raw: bytes, status: int, content_type: str,
                    enc: str, extra: Optional[dict] = None) -> dict:
        html_path, meta_path = self.cache_paths(url)
        meta = {
            "url": url,
            "status": status,
            "content_type": content_type,
            "encoding": enc,
            "bytes": len(raw),
            "fetched_at": _now_iso(),
            "ua": self.ua,
        }
        if extra:
            meta.update(extra)
        with io.open(html_path, "wb") as f:
            f.write(raw)
        with io.open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
        return meta

    # -- network ---------------------------------------------------------- #
    def _throttle(self):
        elapsed = time.monotonic() - self._last_request_at
        wait = self.min_interval - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    def get(self, url: str, force: bool = False, allow_disallowed: bool = False,
            policy: Optional[RobotsPolicy] = None, is_binary: bool = False) -> FetchResult:
        """캐시 우선 GET. robots 정책이 주어지면 Disallow 시 RobotsDisallowed."""
        if not force and not allow_disallowed:
            cached = self._load_cache(url)
            if cached is not None:
                return cached
        if policy is not None and not policy.can_fetch(url):
            raise RobotsDisallowed(
                "robots.txt disallows %s for UA %r (matched agents: %s)"
                % (url, self.ua, (policy.group or {}).get("agents")))
        self._throttle()
        resp = self.session.get(url, timeout=self.timeout)
        self.request_count += 1
        ctype = resp.headers.get("content-type", "")
        if is_binary:
            meta = self._save_cache(url, resp.content, resp.status_code, ctype, "binary")
            return FetchResult(url, "", "binary", resp.status_code, False, meta["fetched_at"], meta)
        text, enc = decode_html(resp.content, ctype)
        meta = self._save_cache(url, resp.content, resp.status_code, ctype, enc)
        self.log("GET %s -> %s %d bytes enc=%s" % (url, resp.status_code, len(resp.content), enc))
        return FetchResult(url, text, enc, resp.status_code, False, meta["fetched_at"], meta)

    def close(self):
        try:
            self.session.close()
        except Exception:
            pass


def _now_iso() -> str:
    """+09:00 고정 오프셋의 ISO8601 시각."""
    from datetime import datetime, timedelta, timezone
    return datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds")
