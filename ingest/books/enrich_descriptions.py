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
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

API_BASE = "https://apis.yes24.com"

# ---- API 응답 디스크 캐시 (원본 아카이브, gitignored) ----
_ENRICH_CACHE = Path(__file__).resolve().parents[2] / "data" / "enrich_cache"
_POS_TTL = 30 * 86400
_NEG_TTL = 3 * 86400
_REFRESH = False


def _cache_file(kind: str, key: str) -> Path:
    safe = re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", str(key))[:80]
    d = _ENRICH_CACHE / kind
    d.mkdir(parents=True, exist_ok=True)
    return d / (safe + ".json")


def _cache_get(kind: str, key: str):
    if _REFRESH:
        return None
    try:
        obj = json.loads(_cache_file(kind, key).read_text(encoding="utf-8"))
    except Exception:
        return None
    data = obj.get("data")
    ttl = _POS_TTL if data else _NEG_TTL
    if time.time() - float(obj.get("ts") or 0) > ttl:
        return None
    return data


def _cache_put(kind: str, key: str, data) -> None:
    try:
        _cache_file(kind, key).write_text(
            json.dumps({"ts": time.time(), "data": data}, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


# Google Books 무료 한도: 분당 100회 → 안전하게 80/min 으로 제한
_GOOGLE_LOCK = threading.Lock()
_GOOGLE_LAST = 0.0
_GOOGLE_INTERVAL = 0.75
_GOOGLE_429 = 0
_GOOGLE_ABORT = False


def _google_cached(kind: str, key: str, url: str) -> dict:
    hit = _cache_get(kind, key)
    if hit is not None:
        return hit
    data = _google_get(url)
    # 429/오류 응답은 캐시하지 않음(다음 실행에서 재시도)
    # 성공 응답(0건 포함)은 캐시, 429/네트워크 오류({} 또는 totalItems 없음)는 캐시 안 함
    if isinstance(data, dict) and "totalItems" in data:
        _cache_put(kind, key, data)
    return data


def _google_get(url: str, timeout: int = 15) -> dict:
    """레이트 리밋 + 429 재시도 + 쿼터 소진 서킷브레이커 포함 GET."""
    global _GOOGLE_LAST, _GOOGLE_429, _GOOGLE_ABORT
    if _GOOGLE_ABORT:
        return {}
    for attempt in range(3):
        with _GOOGLE_LOCK:
            wait = _GOOGLE_INTERVAL - (time.monotonic() - _GOOGLE_LAST)
            if wait > 0:
                time.sleep(wait)
            _GOOGLE_LAST = time.monotonic()
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers={"User-Agent": "seogarok-enrich/1"}), timeout=timeout
            ) as resp:
                _GOOGLE_429 = 0
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                _GOOGLE_429 += 1
                if _GOOGLE_429 >= 3:
                    _GOOGLE_ABORT = True
                    print("[enrich] Google 쿼터 소진(429 3회) — 남은 Google 호출 스킵", file=sys.stderr)
                    return {}
                if attempt < 2:
                    time.sleep(2.0 + attempt * 2.0)
                    continue
                return {}
            return {}
        except Exception:
            if attempt < 2:
                time.sleep(1.0)
                continue
            return {}
    return {}



def _load_dotenv() -> None:
    """로컬 실행 편의: 프로젝트 .env의 키를 환경변수로 로드(이미 있으면 유지)."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    try:
        text = env_path.read_text(encoding="utf-8-sig")
    except Exception:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


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


def _google_books(isbn: str) -> dict:
    """Google Books ISBN 조회 (GOOGLE_BOOKS_API_KEY 필요)."""
    api_key = (os.getenv("GOOGLE_BOOKS_API_KEY") or "").strip()
    if not api_key or not isbn:
        return {}
    url = "https://www.googleapis.com/books/v1/volumes?" + urllib.parse.urlencode(
        {"q": f"isbn:{isbn}", "key": api_key}
    )
    data = _google_cached("google_isbn", isbn, url)
    items = data.get("items") or []
    if not items:
        return {}
    vi = items[0].get("volumeInfo") or {}
    desc = _clean_text(vi.get("description"))[:2000]
    return {
        "description": desc or None,
        "pages": vi.get("pageCount"),
        "subtitle": (vi.get("subtitle") or "").strip() or None,
        "source": "google_books",
    }


def _naver_book(isbn: str, title: str = "") -> dict:
    """네이버 책 검색 API (NAVER_CLIENT_ID/SECRET 필요)."""
    cid = (os.getenv("NAVER_CLIENT_ID") or "").strip()
    secret = (os.getenv("NAVER_CLIENT_SECRET") or "").strip()
    q = (isbn or title or "").strip()
    if not cid or not secret or not q:
        return {}
    url = "https://openapi.naver.com/v1/search/book.json?" + urllib.parse.urlencode({"query": q, "display": 3})
    try:
        with urllib.request.urlopen(
            urllib.request.Request(
                url,
                headers={
                    "X-Naver-Client-Id": cid,
                    "X-Naver-Client-Secret": secret,
                    "User-Agent": "seogarok-enrich/1",
                },
            ),
            timeout=15,
        ) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return {}
    items = data.get("items") or []
    for it in items:
        desc = _clean_text(it.get("description"))[:2000]
        if desc:
            return {"description": desc, "source": "naver_book"}
    return {}


def _norm_title(text: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKC", str(text or "")).lower()
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)|<[^>]*>", "", t)
    t = re.sub(r"[\s\-_·:：,，.。/|'\"]+", "", t)
    t = re.sub(r"\d+$", "", t)
    t = re.sub(r"(세트|전집|특별판|한정판|개정판|증보판|양장|합본)$", "", t)
    return t


def _google_title(title: str, author: str = "") -> dict:
    """Google Books 제목 검색 기반 보강 (GOOGLE_BOOKS_API_KEY 필요).

    ISBN 색인이 없는 한국어 책 대응 — 일반 제목 쿼리 후 제목 정규화 매칭.
    """
    api_key = (os.getenv("GOOGLE_BOOKS_API_KEY") or "").strip()
    title = (title or "").strip()
    if not api_key or len(title) < 2:
        return {}
    url = "https://www.googleapis.com/books/v1/volumes?" + urllib.parse.urlencode(
        {"q": title, "key": api_key, "maxResults": 10}
    )
    data = _google_cached("google_title", title, url)
    want = _norm_title(title)
    for it in data.get("items") or []:
        vi = it.get("volumeInfo") or {}
        cand = _norm_title(vi.get("title") or "")
        if not want or not cand:
            continue
        if cand != want and want not in cand and cand not in want:
            continue
        desc = _clean_text(vi.get("description"))[:2000]
        if len(desc) < 40:
            continue
        return {
            "description": desc,
            "pages": vi.get("pageCount"),
            "subtitle": (vi.get("subtitle") or "").strip() or None,
            "source": "google_books_title",
        }
    return {}


def fetch_detail(key: str, row: dict) -> dict:
    isbn = (row.get("isbn13") or "").strip()
    item = (row.get("item_code") or "").strip()
    if isbn:
        params = {"searchType": "ISBN13", "query": isbn, "detail": "Y"}
    elif item:
        params = {"searchType": "ItemId", "query": item, "detail": "Y"}
    else:
        return {}
    _ck = isbn or f"item:{item}"
    _hit = _cache_get("yes24", _ck)
    if _hit is not None:
        return _hit

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
            out = {
                "intro": _clean_text(cd.get("bookIntroduction"))[:2000] or None,
                "summary": _clean_text(cd.get("bookSummary"))[:800] or None,
                "toc": _clean_text(cd.get("tableOfContents"))[:4000] or None,
                "pages": it.get("pages"),
                "star": it.get("starScore"),
                "subtitle": (it.get("subTitle") or "").strip() or None,
                "source": "yes24_itemdetail",
            }
            _cache_put("yes24", _ck, out)
            return out
        except Exception:
            if attempt == 0:
                time.sleep(0.4)
    _cache_put("yes24", _ck, {})
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
    _load_dotenv()
    ap = argparse.ArgumentParser(description="YES24/대체소스 설명 배치 보강")
    ap.add_argument("--catalog", default=str(Path(__file__).resolve().parents[2] / "data" / "catalog.jsonl"))
    ap.add_argument("--out", default="")
    ap.add_argument("--limit", type=int, default=0, help="누락분 중 최대 N권 (0=전체)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--timeout", type=int, default=0, help="초 (0=무제한)")
    ap.add_argument("--min-desc", type=int, default=20, help="이 길이 이하 설명은 누락으로 간주")
    ap.add_argument("--html", action="store_true", help="API로 안 되는 책은 HTML 상세페이지에서 보강")
    ap.add_argument("--skip-api", action="store_true", help="YES24 API 보강 단계 건너뛰기(HTML/대체소스만)")
    ap.add_argument("--google-only", action="store_true", help="YES24 없이 Google Books만으로 보강(일일 쿼터 주의)")
    ap.add_argument("--google-title", action="store_true", help="Google Books 제목 검색으로 보강(ISBN 미색인 대응)")
    ap.add_argument("--refresh", action="store_true", help="API 응답 디스크 캐시 무시하고 재조회")
    ap.add_argument("--html-workers", type=int, default=3)
    ap.add_argument("--html-interval", type=float, default=1.1, help="HTML 요청 간 최소 간격(초)")
    args = ap.parse_args(argv)
    global _REFRESH
    _REFRESH = bool(args.refresh)

    key = _key()
    if not key and not (args.google_only or args.google_title):
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
            d = {}
        if not (d.get("intro") or d.get("summary")):
            # YES24에 소개가 없으면 키 기반 대체 소스 시도 (없으면 조용히 스킵)
            alt = {}
            isbn = (row.get("isbn13") or "").strip()
            if isbn and os.getenv("GOOGLE_BOOKS_API_KEY"):
                alt = _google_books(isbn)
            if not alt.get("description") and os.getenv("NAVER_CLIENT_ID") and os.getenv("NAVER_CLIENT_SECRET"):
                alt = _naver_book(isbn, row.get("title") or "")
            if alt.get("description"):
                d = dict(d)
                d["intro"] = alt["description"]
                d["pages"] = d.get("pages") or alt.get("pages")
                d["subtitle"] = d.get("subtitle") or alt.get("subtitle")
                d["alt_source"] = alt.get("source")
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

    if args.google_title:
        if not os.getenv("GOOGLE_BOOKS_API_KEY"):
            print("[enrich] --google-title: GOOGLE_BOOKS_API_KEY 없음 — 스킵", file=sys.stderr)
            return 0
        print(f"[enrich] google-title targets={len(targets)} workers={args.workers}")
        tfilled = 0
        tmiss = 0

        def twork(row):
            nonlocal tfilled, tmiss
            if args.timeout and time.time() - t0 > args.timeout:
                return
            info = _google_title(row.get("title") or "", row.get("author") or "")
            desc = _clean_text(info.get("description"))
            if desc:
                row["description"] = desc[:2000]
                if info.get("pages"):
                    row["pages"] = info["pages"]
                if info.get("subtitle") and not row.get("subtitle"):
                    row["subtitle"] = info["subtitle"]
                row["enriched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                row["enrich_source"] = info.get("source") or "google_books_title"
                tfilled += 1
            else:
                tmiss += 1

        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
            list(ex.map(twork, targets))
        tmp = out.with_suffix(out.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.replace(out)
        with_desc = sum(1 for r in rows if len(_clean_text(r.get("description"))) > args.min_desc)
        print(
            f"[enrich] google-title done in {time.time() - t0:.1f}s · filled={tfilled} miss={tmiss} "
            f"· coverage {with_desc}/{len(rows)} ({with_desc * 100 // max(1, len(rows))}%)"
        )
        return 0

    if args.google_only:
        if not os.getenv("GOOGLE_BOOKS_API_KEY"):
            print("[enrich] --google-only: GOOGLE_BOOKS_API_KEY 없음 — 스킵", file=sys.stderr)
            return 0
        print(f"[enrich] google-only targets={len(targets)} workers={args.workers}")
        gfilled = 0
        gfailed = 0

        def gwork(row):
            nonlocal gfilled, gfailed
            if args.timeout and time.time() - t0 > args.timeout:
                return
            isbn = (row.get("isbn13") or "").strip()
            if not isbn:
                return
            info = _google_books(isbn)
            desc = _clean_text(info.get("description"))
            if desc:
                row["description"] = desc[:2000]
                if info.get("pages"):
                    row["pages"] = info["pages"]
                row["enriched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                row["enrich_source"] = "google_books"
                gfilled += 1
            else:
                gfailed += 1

        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
            list(ex.map(gwork, targets))
        tmp = out.with_suffix(out.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.replace(out)
        with_desc = sum(1 for r in rows if len(_clean_text(r.get("description"))) > args.min_desc)
        print(
            f"[enrich] google done in {time.time() - t0:.1f}s · filled={gfilled} miss={gfailed} "
            f"· coverage {with_desc}/{len(rows)} ({with_desc * 100 // max(1, len(rows))}%)"
        )
        return 0

    if args.skip_api:
        print("[enrich] --skip-api: YES24 API 단계 건너뜀")
    else:
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
