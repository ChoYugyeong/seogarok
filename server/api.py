"""서가록(SEOGAROK) HTTP API + 정적 파일 서버 + 관측성 엔드포인트.

외부 의존성 없이 표준 라이브러리만 사용한다.
  GET  /healthz , /livez            liveness (프로세스 생존)  ※ Cloud Run 전면(GFE)은 /healthz 를 예약 → /livez 사용
  GET  /readyz                      readiness (DB/벡터 인덱스 준비)
  GET  /metrics                     Prometheus 텍스트 포맷
  POST /api/_chaos                  장애 주입 (SEOG_CHAOS=1 일 때만)
  GET  /api/health
  GET  /api/search?q=&mode=hybrid|keyword|vector&limit=&debug=1
  GET  /api/book?id=
  GET  /api/notices?limit=
  GET  /api/stats
  GET  /api/suggest?q=
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import random
import threading
import time
from datetime import datetime, timedelta
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import config
from .availability import build_availability
from .db import VectorStore, connect, meta
from .embed import get_embedder
from .metrics import METRICS
from .search import fetch_availability, fetch_books, fetch_notices, search

_lock_encode = threading.Lock()
_rank_cache: dict = {}  # /api/rank 카테고리별 (ts, payload)
_rank_saved: set = set()  # 이번 인스턴스에서 저장한 일별 스냅샷 키

VERSION = "0.4.0"
CHAOS_ENABLED = os.getenv("SEOG_CHAOS", "0") == "1"

# 런타임 장애 주입 상태 (게임데이/알림 검증용)
CHAOS = {"latency_ms": 0, "error_rate": 0.0}

# 라벨 카디널리티를 낮추기 위한 경로 정규화
_ROUTES = ("/api/search", "/api/book", "/api/notices", "/api/stats", "/api/suggest", "/api/report", "/api/rank", "/api/collections", "/api/collection", "/api/overview", "/api/pick",
           "/api/health", "/api/_chaos", "/healthz", "/livez", "/readyz", "/metrics")


def route_of(path: str) -> str:
    for r in _ROUTES:
        if path == r or path.startswith(r + "/"):
            return r
    if path.startswith("/api/"):
        return "/api/other"
    return "/static" if path not in ("/", "") else "/"


def log_event(**fields) -> None:
    """stdout JSON 로그 (컨테이너 로그 수집기와 호환)."""
    fields.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    print(json.dumps(fields, ensure_ascii=False), flush=True)



class _ChaosInjected(Exception):
    """카오스 주입으로 요청을 중단했음을 표시."""


class AppState:
    def __init__(self):
        self.started = time.time()
        self.db_path = config.DB_PATH
        boot = connect(readonly=False)
        self.meta = meta(boot)
        boot.close()
        self.embedder = get_embedder()
        self.dim = int(self.meta.get("embed_dim") or self.embedder.dim)
        self.vec_backend = self.meta.get("vec_backend", "?")
        self.book_count = int(self.meta.get("book_count") or 0)
        self.notice_count = int(self.meta.get("notice_count") or 0)
        self.lock = threading.Lock()
        METRICS.build_info = {
            "version": VERSION,
            "embed": str(self.meta.get("embed_backend") or "?"),
            "vector": str(self.vec_backend),
        }

    def readiness(self) -> tuple[bool, dict]:
        """readiness: DB에서 실제 문서 수와 벡터 수를 읽어 판정한다.

        (메타 캐시만 믿으면 재색인 후에도 옛 값을 서빙하는 사고가 난다)
        """
        try:
            conn, store = self.ctx()
            docs = int(conn.execute("SELECT count(*) FROM books").fetchone()[0])
            vectors = int(store.count())
            ok = docs > 0 and vectors > 0 and docs == vectors
            return ok, {
                "documents": docs,
                "vectors": vectors,
                "embed": self.meta.get("embed_backend"),
                "index_backend": self.vec_backend,
            }
        except Exception as exc:  # DB 잠김/파일 없음 등
            return False, {"error": str(exc)[:200]}

    # 스레드별 DB 연결/벡터 스토어
    def ctx(self):
        tls = getattr(self, "_tls", None)
        if tls is None:
            tls = threading.local()
            self._tls = tls
        conn = getattr(tls, "conn", None)
        if conn is None:
            conn = connect(readonly=False)
            store = VectorStore(conn, self.dim)
            tls.conn, tls.store = conn, store
        return tls.conn, tls.store

    def encode_one(self, text: str):
        with _lock_encode:
            return self.embedder.encode_one(text)


APP: AppState | None = None


def get_app() -> AppState:
    global APP
    if APP is None:
        APP = AppState()
    return APP


def serialize_book(row: dict, av: dict, origins: dict, notices: list[dict], score: float | None = None) -> dict:
    out = {
        "id": row["id"],
        "title": row["title"],
        "subtitle": row.get("subtitle"),
        "author": row.get("author"),
        "publisher": row.get("publisher"),
        "pubdate": row.get("pubdate"),
        "isbn13": row.get("isbn13"),
        "price": row.get("price"),
        "price_list": row.get("price_list"),
        "rating": row.get("rating"),
        "cover_url": row.get("cover_url"),
        "link": row.get("link"),
        "category": row.get("category"),
        "description": row.get("description"),
        "source": row.get("source"),
        "av": av,
        "av_origin": origins,
        "notices": [
            {
                "platform": n.get("platform"),
                "ends_at": n.get("ends_at"),
                "status": n.get("status"),
                "source_url": n.get("source_url"),
                "source_kind": n.get("source_kind"),
            }
            for n in (notices or [])
        ],
    }
    if score is not None:
        out["score"] = round(score, 5)
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "seogarok/0.4"
    protocol_version = "HTTP/1.1"
    _status = 200

    # ---------------- utils ----------------
    _COMPRESSIBLE = ("application/json", "text/", "application/manifest+json", "image/svg")

    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8", cache: str = "no-store"):
        self._status = code
        # gzip (JSON/텍스트가 512B 이상일 때) — 공지 126KB → ~15KB
        accept = (self.headers.get("Accept-Encoding") or "")
        if (
            len(body) >= 512
            and "gzip" in accept.lower()
            and any(ctype.startswith(t) for t in self._COMPRESSIBLE)
            and not ctype.startswith("image/")
        ):
            try:
                import gzip as _gzip

                body = _gzip.compress(body, compresslevel=6)
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Vary", "Accept-Encoding")
            except Exception:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
        else:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("Access-Control-Allow-Origin", "*")
        if getattr(self, "req_id", None):
            self.send_header("X-Request-Id", self.req_id)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def log_message(self, fmt, *args):  # 기본 액세스 로그는 끄고 _handle 에서 JSON 으로 남긴다
        return

    # ---------------- routing ----------------
    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def _handle(self, method: str):
        self.req_id = uuid.uuid4().hex[:12]
        parsed = urlparse(self.path)
        route = route_of(parsed.path)
        t0 = time.perf_counter()
        METRICS.inc_in_flight()
        try:
            self._dispatch(method, parsed)
        except BrokenPipeError:
            self._status = 499
        except _ChaosInjected:
            pass  # 이미 503 응답을 보냈다
        except Exception:
            traceback.print_exc()
            self._status = 500
            try:
                self._json({"error": "internal", "request_id": self.req_id}, 500)
            except Exception:
                pass
        finally:
            dur = time.perf_counter() - t0
            METRICS.dec_in_flight()
            METRICS.observe_request(method, route, self._status, dur)
            log_event(level="error" if self._status >= 500 else "info", req_id=self.req_id,
                      method=method, path=parsed.path, route=route, status=self._status,
                      dur_ms=round(dur * 1000, 2), ua=self.headers.get("User-Agent", "")[:80])

    def _chaos_apply(self, path: str) -> None:
        """앱 엔드포인트에만 장애를 주입한다(관측 엔드포인트는 제외)."""
        if not CHAOS_ENABLED:
            return
        if path in ("/metrics", "/healthz", "/livez", "/readyz", "/api/_chaos"):
            return
        if CHAOS["latency_ms"]:
            time.sleep(CHAOS["latency_ms"] / 1000.0)
        if CHAOS["error_rate"] > 0 and random.random() < CHAOS["error_rate"]:
            self._json({"error": "chaos_injected", "request_id": self.req_id}, 503)
            raise _ChaosInjected()

    def _dispatch(self, method: str, parsed):
        self._chaos_apply(parsed.path)
        if parsed.path.startswith("/api/_chaos"):
            return self.handle_chaos(method, parsed)
        if parsed.path == "/api/report":
            return self.handle_report(method, parsed)
        if parsed.path.startswith("/api/"):
            return self.route_api(parsed.path, parse_qs(parsed.query))
        if parsed.path in ("/healthz", "/livez", "/readyz", "/metrics"):
            return self.route_ops(parsed.path)
        return self.serve_static(parsed.path)

    def route_ops(self, path: str):
        app = get_app()
        if path in ("/healthz", "/livez"):
            return self._json({"ok": True, "version": VERSION, "uptime_s": round(time.time() - app.started, 1)})
        if path == "/readyz":
            ok, detail = app.readiness()
            return self._json({"ready": ok, **detail}, 200 if ok else 503)
        if path == "/metrics":
            try:
                self._refresh_gauges()
            except Exception as exc:  # 메트릭 스크레이프는 절대 실패하면 안 된다
                log_event(level="warn", msg="metrics_gauge_refresh_failed", error=str(exc))
            body = METRICS.render().encode("utf-8")
            return self._send(200, body, "text/plain; version=0.0.4; charset=utf-8")

    def handle_report(self, method: str, parsed):
        """가용성 제보: POST /api/report {book_id, platform, note?}

        컨테이너가 read_only 이므로 DB 쓰기가 실패하면 /tmp JSONL 로 폴백한다.
        (제보 원본은 Cloud Logging 에도 남겨 나중에 배치로 반영할 수 있게 한다)
        """
        if method != "POST":
            return self._json({"error": "method_not_allowed"}, 405)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "invalid_json"}, 400)
        if not isinstance(body, dict):
            return self._json({"error": "invalid_body"}, 400)
        book_id = str(body.get("book_id") or "").strip()[:120]
        platform = str(body.get("platform") or "").strip()
        note = str(body.get("note") or "").strip()[:200]
        from .availability import SUB_PLATFORMS

        if not book_id or platform not in SUB_PLATFORMS:
            return self._json({"error": "invalid_params", "allowed": SUB_PLATFORMS}, 400)

        app = get_app()
        ip = (self.headers.get("X-Forwarded-For") or self.client_address[0] or "").split(",")[0].strip()
        ip_hash = hashlib.sha256((ip or "unknown").encode("utf-8")).hexdigest()[:16]
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        record = {
            "book_id": book_id,
            "platform": platform,
            "note": note or None,
            "ua": self.headers.get("User-Agent", "")[:120],
            "ip_hash": ip_hash,
            "created_at": now,
        }
        count = 0
        dup = False
        stored = "db"
        # ① 제보 원본을 GCS 에 영속화 (컨테이너 재시작에도 유지)
        try:
            from .reports_store import persist_report

            persist_report(record)
            stored = "gcs"
        except Exception:
            pass
        try:
            conn, _ = app.ctx()
            exists = conn.execute("SELECT 1 FROM books WHERE id = ?", (book_id,)).fetchone()
            if not exists:
                return self._json({"error": "book_not_found", "book_id": book_id}, 404)
            dup = bool(
                conn.execute(
                    "SELECT 1 FROM reports WHERE book_id=? AND platform=? AND ip_hash=? AND created_at >= ?",
                    (book_id, platform, ip_hash,
                     (datetime.now().astimezone() - timedelta(hours=12)).isoformat(timespec="seconds")),
                ).fetchone()
            )
            if not dup:
                conn.execute(
                    "INSERT INTO reports(book_id, platform, note, ua, ip_hash, created_at) VALUES (?,?,?,?,?,?)",
                    (book_id, platform, record["note"], record["ua"], ip_hash, now),
                )
                conn.commit()
            count = conn.execute(
                "SELECT count(*) FROM reports WHERE book_id=? AND platform = ?", (book_id, platform)
            ).fetchone()[0]
        except Exception:
            # read_only 파일시스템 등 — /tmp 에 적재하고 로그로도 남긴다
            stored = "tmp"
            try:
                with open("/tmp/seogarok_reports.jsonl", "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count = 1
            except Exception:
                stored = "log"
                count = 0
        log_event(level="info", msg="availability_report", book_id=book_id, platform=platform,
                  count=count, dup=dup, stored=stored)
        return self._json({"ok": True, "book_id": book_id, "platform": platform, "count": count,
                           "duplicate": dup, "stored": stored})

    def handle_chaos(self, method: str, parsed):
        if not CHAOS_ENABLED:
            return self._json({"error": "chaos_disabled", "hint": "SEOG_CHAOS=1 로 기동해야 합니다"}, 404)
        if method == "GET":
            return self._json({"enabled": True, **CHAOS})
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "invalid_json"}, 400)
        CHAOS["latency_ms"] = int(body.get("latency_ms", 0) or 0)
        CHAOS["error_rate"] = float(body.get("error_rate", 0) or 0)
        log_event(level="warn", msg="chaos_set", **CHAOS)
        return self._json({"ok": True, **CHAOS})

    def _refresh_gauges(self):
        app = get_app()
        conn, store = app.ctx()
        docs = int(conn.execute("SELECT count(*) FROM books").fetchone()[0])
        notices = int(conn.execute("SELECT count(*) FROM notices").fetchone()[0])
        METRICS.set_gauge("seogarok_index_documents", docs)
        METRICS.set_gauge("seogarok_index_vectors", store.count())
        METRICS.set_gauge("seogarok_notices_total", notices)
        ok, _ = app.readiness()
        METRICS.set_gauge("seogarok_ready", 1 if ok else 0)
        # 인덱스 신선도: 마지막 sync 이후 경과 시간
        raw = app.meta.get("synced_at")
        if raw:
            try:
                import datetime as _dt

                ts = _dt.datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S%z")
                METRICS.set_gauge("seogarok_index_age_seconds", max(0.0, (time.time() - ts.timestamp())))
            except ValueError:
                pass
        try:
            METRICS.set_gauge("seogarok_db_size_bytes", Path(config.DB_PATH).stat().st_size)
        except OSError:
            pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def route_api(self, path: str, qs: dict):
        app = get_app()
        t0 = time.perf_counter()

        if path == "/api/health":
            return self._json(
                {
                    "ok": True,
                    "books": app.book_count,
                    "notices": app.notice_count,
                    "embed_backend": app.meta.get("embed_backend"),
                    "embed_dim": app.dim,
                    "vector_backend": app.vec_backend,
                    "synced_at": app.meta.get("synced_at"),
                    "mode": config.MODE,
                }
            )

        if path == "/api/overview":
            conn, store = app.ctx()
            from datetime import date as _date
            from datetime import timedelta as _td

            today = _date.today()
            week_ago = today - _td(days=7)
            week_later = today + _td(days=7)
            today_s = today.isoformat()
            wa_s = week_ago.isoformat()
            wl_s = week_later.isoformat()

            # 장르: category(예: 국내도서>소설>한국소설)의 2차 세그먼트로 집계
            cat_rows = conn.execute("SELECT category, count(*) AS c FROM books GROUP BY category").fetchall()
            agg: dict[str, int] = {}
            for r in cat_rows:
                parts = [x.strip() for x in (r["category"] or "").split(">") if x.strip()]
                g = parts[1] if len(parts) > 1 else (parts[0] if parts else "기타")
                agg[g] = agg.get(g, 0) + int(r["c"])
            genres = [{"name": k, "count": v} for k, v in sorted(agg.items(), key=lambda kv: -kv[1])[:8]]
            platforms = conn.execute(
                "SELECT platform, count(*) AS total, "
                "sum(CASE WHEN ends_at IS NOT NULL AND substr(ends_at,1,10) BETWEEN ? AND ? THEN 1 ELSE 0 END) AS soon "
                "FROM notices GROUP BY platform ORDER BY total DESC",
                (today_s, wl_s),
            ).fetchall()
            authors = conn.execute(
                "SELECT author, count(*) AS c FROM books WHERE author IS NOT NULL AND trim(author) != '' "
                "AND author NOT LIKE '%편집부%' AND author NOT LIKE '%저자 미상%' AND length(author) <= 24 "
                "GROUP BY author ORDER BY c DESC LIMIT 6"
            ).fetchall()
            ending_today = conn.execute(
                "SELECT count(*) FROM notices WHERE substr(ends_at,1,10) = ?", (today_s,)
            ).fetchone()[0]
            ending_3d = conn.execute(
                "SELECT count(*) FROM notices WHERE substr(ends_at,1,10) BETWEEN ? AND ?",
                (today_s, (today + _td(days=3)).isoformat()),
            ).fetchone()[0]
            ending_7d = conn.execute(
                "SELECT count(*) FROM notices WHERE substr(ends_at,1,10) BETWEEN ? AND ?", (today_s, wl_s)
            ).fetchone()[0]
            ninety = (today - _td(days=90)).isoformat()
            recent_books = conn.execute(
                "SELECT count(*) FROM books WHERE substr(pubdate,1,10) >= ?", (ninety,)
            ).fetchone()[0]
            try:
                collections = conn.execute("SELECT count(*) FROM collections").fetchone()[0]
                matched = conn.execute("SELECT count(*) FROM collection_items").fetchone()[0]
            except Exception:
                collections, matched = 0, 0
            return self._json({
                "books": app.book_count,
                "notices": app.notice_count,
                "vectors": store.count(),
                "synced_at": app.meta.get("synced_at"),
                "ending_today": int(ending_today),
                "ending_3d": int(ending_3d),
                "ending_7d": int(ending_7d),
                "new_releases_90d": int(recent_books),
                "collections": int(collections),
                "collection_books": int(matched),
                "genres": genres,
                "platforms": [
                    {"name": r["platform"], "total": int(r["total"]), "ending_7d": int(r["soon"] or 0)}
                    for r in platforms
                ],
                "authors": [{"name": r["author"], "count": int(r["c"])} for r in authors],
            })

        if path == "/api/pick":
            conn, store = app.ctx()
            # 가능하면 큐레이션(서울대/하버드/세종도서) 수록 책에서 고른다
            try:
                pool = conn.execute(
                    "SELECT count(*) FROM collection_items ci JOIN books b ON b.id = ci.book_id "
                    "WHERE b.cover_url IS NOT NULL AND ci.slug IN ('snu-100','harvard-classics','sejong-2025-culture')"
                ).fetchone()[0]
            except Exception:
                pool = 0
            curated = pool > 0
            if not curated:
                pool = conn.execute("SELECT count(*) FROM books WHERE cover_url IS NOT NULL").fetchone()[0]
            total = pool
            if not total:
                return self._json({"error": "empty"}, 404)
            from datetime import date as _date

            day = _date.today()
            seed = day.year * 372 + day.month * 31 + day.day
            if curated:
                row_raw = conn.execute(
                    "SELECT b.* FROM collection_items ci JOIN books b ON b.id = ci.book_id "
                    "WHERE b.cover_url IS NOT NULL AND ci.slug NOT LIKE 'sejong-2025-academic' ORDER BY b.id LIMIT 1 OFFSET ?",
                    (seed * 137 % total,),
                ).fetchone()
            else:
                row_raw = conn.execute(
                    "SELECT * FROM books WHERE cover_url IS NOT NULL ORDER BY id LIMIT 1 OFFSET ?",
                    (seed * 137 % total,),
                ).fetchone()
            if not row_raw:
                return self._json({"error": "empty"}, 404)
            row = dict(row_raw)
            bid = row["id"]
            avs = fetch_availability(conn, [bid])
            nts = fetch_notices(conn, [bid])
            av, origins = build_availability(row, avs.get(bid, []), nts.get(bid, []))
            payload = serialize_book(row, av, origins, nts.get(bid, []))
            try:
                vec = store.get(bid)
                if vec is not None:
                    hits = store.search(vec, k=7)
                    sim_ids = [h[0] for h in hits if h[0] != bid][:4]
                    by_id = {r["id"]: r for r in fetch_books(conn, sim_ids)}
                    payload["similar"] = [
                        {"id": i, "title": by_id[i]["title"], "author": by_id[i]["author"],
                         "cover_url": by_id[i]["cover_url"]}
                        for i in sim_ids if i in by_id
                    ]
            except Exception:
                payload["similar"] = []
            return self._json({"date": day.isoformat(), "book": payload})

        if path == "/api/stats":
            conn, store = app.ctx()
            return self._json(
                {
                    "books": app.book_count,
                    "notices": app.notice_count,
                    "meta": app.meta,
                    "vector_count": store.count(),
                    "db": str(config.DB_PATH),
                    "db_bytes": Path(config.DB_PATH).stat().st_size if Path(config.DB_PATH).exists() else 0,
                }
            )

        if path == "/api/search":
            q = (qs.get("q") or [""])[0]
            mode = (qs.get("mode") or ["hybrid"])[0]
            limit = int((qs.get("limit") or ["24"])[0])
            limit = max(1, min(limit, 60))
            debug = (qs.get("debug") or ["0"])[0] == "1"
            conn, store = app.ctx()
            ids, dbg = search(conn, store, app.embedder, q, mode=mode, limit=limit)
            METRICS.observe_search(
                mode,
                dbg.extra.get("strategy") or "unknown",
                {
                    "keyword": dbg.keyword_ms / 1000.0,
                    "vector": dbg.vector_ms / 1000.0,
                    "fuse": dbg.fuse_ms / 1000.0,
                },
            )
            rows = fetch_books(conn, ids)
            avs = fetch_availability(conn, ids)
            nts = fetch_notices(conn, ids)
            scores = dbg.extra.get("scores", {})
            results = []
            for row in rows:
                av, origins = build_availability(row, avs.get(row["id"], []), nts.get(row["id"], []))
                results.append(serialize_book(row, av, origins, nts.get(row["id"], []), scores.get(row["id"])))
            # ③ 카탈로그에 없으면 실시간 조회 (YES24 Open API)
            #    - 로컬 결과 0건이면 온디맨드 단독
            #    - FTS 후보 0건(벡터만 걸린 경우)이면 온디맨드 결과를 앞에 병합
            strategy = dbg.extra.get("strategy")
            if dbg.keyword_candidates == 0 and q.strip() and results:
                try:
                    from .on_demand import search as od_search

                    live_merge = od_search(q, limit=min(limit, 8))
                except Exception as exc:
                    log_event(level="warn", msg="on_demand_merge_failed", error=str(exc)[:200])
                    live_merge = []
                if live_merge:
                    seen_titles = {x["title"] for x in live_merge}
                    results = live_merge + [x for x in results if x["title"] not in seen_titles][: max(0, limit - len(live_merge))]
                    strategy = "hybrid-live"
            if not results and q.strip():
                try:
                    from .on_demand import search as od_search

                    live = od_search(q, limit=min(limit, 12))
                except Exception:
                    live = []
                if live:
                    return self._json({
                        "q": q,
                        "mode": mode,
                        "count": len(live),
                        "took_ms": round((time.perf_counter() - t0) * 1000, 2),
                        "stage_ms": {"keyword": 0, "vector": 0, "fuse": 0},
                        "candidates": {"keyword": 0, "vector": 0},
                        "strategy": "on-demand",
                        "live": True,
                        "results": live,
                    })
            payload = {
                "q": q,
                "mode": mode,
                "count": len(results),
                "took_ms": round((time.perf_counter() - t0) * 1000, 2),
                "stage_ms": {
                    "keyword": dbg.keyword_ms,
                    "vector": dbg.vector_ms,
                    "fuse": dbg.fuse_ms,
                },
                "candidates": {"keyword": dbg.keyword_candidates, "vector": dbg.vector_candidates},
                "strategy": strategy,
                "results": results,
            }
            if debug:
                payload["debug"] = {
                    "fts_query": dbg.keyword_query,
                    "keyword_ids": dbg.extra.get("keyword_ids", [])[:10],
                    "vector_ids": dbg.extra.get("vector_ids", [])[:10],
                    "vector_sims": dbg.extra.get("vector_sims", {}),
                }
            return self._json(payload)

        if path == "/api/book":
            bid = unquote((qs.get("id") or [""])[0])
            conn, store = app.ctx()
            rows = fetch_books(conn, [bid])
            if not rows:
                # ③ 온디맨드 상세 + 임베딩 유사 책
                try:
                    from .on_demand import fetch_book as od_book

                    payload = od_book(bid)
                except Exception:
                    payload = None
                if not payload:
                    return self._json({"error": "not_found", "id": bid}, 404)
                try:
                    vec = app.embedder.encode_one(f"{payload['title']} {payload.get('author') or ''}")
                    hits = store.search(vec, k=7)
                    sim_ids = [h[0] for h in hits][:6]
                    by_id = {r["id"]: r for r in fetch_books(conn, sim_ids)}
                    payload["similar"] = [
                        {"id": i, "title": by_id[i]["title"], "author": by_id[i]["author"],
                         "cover_url": by_id[i]["cover_url"]}
                        for i in sim_ids if i in by_id
                    ]
                except Exception:
                    payload["similar"] = []
                payload["reports"] = []
                return self._json(payload)
            row = rows[0]
            avs = fetch_availability(conn, [bid])
            nts = fetch_notices(conn, [bid])
            av, origins = build_availability(row, avs.get(bid, []), nts.get(bid, []))
            payload = serialize_book(row, av, origins, nts.get(bid, []))
            # ① 이 책과 비슷한 책: 같은 임베딩 공간에서 최근접 6권 (자기 제외)
            try:
                vec = store.get(bid)
                if vec is not None:
                    hits = store.search(vec, k=7)
                    sim_ids = [h[0] for h in hits if h[0] != bid][:6]
                    if sim_ids:
                        order = {rid: n for n, rid in enumerate(sim_ids)}
                        rows2 = sorted(fetch_books(conn, sim_ids), key=lambda r: order.get(r["id"], 99))
                        payload["similar"] = [
                            {
                                "id": r["id"],
                                "title": r["title"],
                                "author": r["author"],
                                "cover_url": r["cover_url"],
                            }
                            for r in rows2
                        ]
            except Exception:
                payload["similar"] = []
            # ② 가용성 제보 집계 (확인 중)
            try:
                rep = conn.execute(
                    "SELECT platform, count(*) AS c, max(created_at) AS last_at FROM reports WHERE book_id=? GROUP BY platform",
                    (bid,),
                ).fetchall()
                payload["reports"] = [
                    {"platform": r["platform"], "count": int(r["c"]), "last_at": r["last_at"]} for r in rep
                ]
            except Exception:
                payload["reports"] = []
            return self._json(payload)

        if path == "/api/notices":
            limit = int((qs.get("limit") or ["50"])[0])
            conn, _ = app.ctx()
            rows = conn.execute(
                "SELECT * FROM notices ORDER BY ends_at IS NULL, ends_at LIMIT ?", (limit,)
            ).fetchall()
            total = int(conn.execute("SELECT count(*) FROM notices").fetchone()[0])
            real = int(
                conn.execute("SELECT count(*) FROM notices WHERE source_kind IS NOT NULL AND source_kind != 'fixture'").fetchone()[0]
            )
            return self._json({"count": len(rows), "total": total, "real": real, "notices": [dict(r) for r in rows]})

        if path == "/api/rank":
            # 예스24 실시간 랭킹 (베스트/스테디/일간/월간 × 카테고리), 10분 캐시 + 일별 스냅샷
            RANK_CATS = {
                "종합": "001", "소설": "001001046", "에세이": "001001047",
                "인문": "001001019", "과학": "001001002", "역사": "001001010",
                "자기계발": "001001026", "경제": "001001025",
                "여행": "001001009", "어린이": "001001016",
            }
            RANK_KINDS = {
                "best": ("베스트셀러", "/v1/category/bestseller"),
                "steady": ("스테디셀러", "/v1/category/bestsellerSteady"),
                "daily": ("일간 베스트", "/v1/category/bestsellerDaily"),
                "monthly": ("월간 베스트", "/v1/category/bestsellerMonthly"),
            }
            cat = (qs.get("cat") or ["종합"])[0].strip() or "종합"
            if cat not in RANK_CATS:
                cat = "종합"
            kind = (qs.get("kind") or ["best"])[0].strip() or "best"
            if kind not in RANK_KINDS:
                kind = "best"
            limit = int((qs.get("limit") or ["10"])[0])
            limit = max(3, min(limit, 20))
            key = f"{cat}:{kind}"
            now = time.time()
            hit = _rank_cache.get(key)
            if hit and now - hit[0] < 600:
                return self._json(hit[1])
            label, endpoint = RANK_KINDS[kind]
            try:
                from .on_demand import _get as _od_get

                data = _od_get(endpoint, {
                    "categoryId": RANK_CATS[cat], "page": 1, "pageSize": limit, "detail": "Y",
                })
            except Exception as exc:
                return self._json({
                    "error": "rank_unavailable",
                    "message": str(exc)[:160],
                    "category": cat,
                    "kind": kind,
                }, 503)
            items = []
            for it in (data.get("items") or []):
                goods = str(it.get("itemId") or "").strip()
                title = str(it.get("title") or "").strip()
                if not goods or not title:
                    continue

                def _num(v):
                    try:
                        return int(float(v))
                    except (TypeError, ValueError):
                        return None

                items.append({
                    "rank": len(items) + 1,
                    "id": f"yes24:{goods}",
                    "title": title,
                    "author": (it.get("author") or "").strip() or "저자 미상",
                    "cover_url": it.get("cover") or f"https://image.yes24.com/goods/{goods}/L",
                    "price": _num(it.get("salePrice")),
                    "star": float(it["starScore"]) if it.get("starScore") is not None else None,
                    "sale_point": _num(it.get("salePoint")),
                    "category": it.get("goodsSortNm") or "",
                })

            try:
                from .rank_store import attach_deltas, save_snapshot

                attach_deltas(items, kind, cat)
                day_key = time.strftime("%Y-%m-%d", time.gmtime())
                saved_key = f"{day_key}:{kind}:{cat}"
                if saved_key not in _rank_saved:
                    _rank_saved.add(saved_key)
                    try:
                        save_snapshot(kind, cat, items)
                    except Exception:
                        pass
            except Exception:
                pass

            payload = {
                "category": cat,
                "category_id": RANK_CATS[cat],
                "kind": kind,
                "kind_label": label,
                "source": f"예스24 {label}",
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "items": items,
            }
            _rank_cache[key] = (now, payload)
            return self._json(payload)

        if path == "/api/collections":
            conn, _ = app.ctx()
            rows = conn.execute("SELECT * FROM collections ORDER BY ord").fetchall()
            out = []
            for r in rows:
                matched = int(
                    conn.execute("SELECT count(*) FROM collection_items WHERE slug = ?", (r["slug"],)).fetchone()[0]
                )
                samples = conn.execute(
                    "SELECT b.id, b.title, b.author, b.cover_url FROM collection_items ci "
                    "JOIN books b ON b.id = ci.book_id WHERE ci.slug = ? ORDER BY ci.ord LIMIT 4",
                    (r["slug"],),
                ).fetchall()
                item = dict(r)
                item["matched"] = matched
                item["samples"] = [dict(x) for x in samples]
                out.append(item)
            return self._json({"count": len(out), "collections": out})

        if path == "/api/collection":
            slug = (qs.get("slug") or [""])[0].strip()
            conn, _ = app.ctx()
            row = conn.execute("SELECT * FROM collections WHERE slug = ?", (slug,)).fetchone()
            if not row:
                return self._json({"error": "not_found", "slug": slug}, 404)
            items = conn.execute(
                "SELECT ci.book_id, ci.item_title, ci.item_author, ci.category, "
                "b.title AS book_title, b.author AS book_author, b.cover_url, b.price "
                "FROM collection_items ci JOIN books b ON b.id = ci.book_id "
                "WHERE ci.slug = ? ORDER BY ci.ord",
                (slug,),
            ).fetchall()
            meta = dict(row)
            meta["matched"] = len(items)
            # 미수록 항목 (프론트에서 '실시간 조회' 칩으로 노출) — DB 저장본 사용
            try:
                urows = conn.execute(
                    "SELECT item_title, item_author, category FROM collection_unmatched "
                    "WHERE slug = ? ORDER BY ord LIMIT 60",
                    (slug,),
                ).fetchall()
                unmatched = [
                    {"title": r["item_title"], "author": r["item_author"], "category": r["category"]}
                    for r in urows
                ]
            except Exception:
                unmatched = []
            return self._json({"collection": meta, "books": [dict(x) for x in items], "unmatched": unmatched})

        if path == "/api/suggest":
            q = (qs.get("q") or [""])[0].strip()
            conn, _ = app.ctx()
            if not q:
                return self._json({"q": q, "suggestions": [], "items": []})
            from .kotext import fts_query, is_chosung_query

            if is_chosung_query(q):
                from .search import chosung_search

                ids = chosung_search(conn, q, limit=7)
                rows = fetch_books(conn, ids) if ids else []
                by_id = {r["id"]: r for r in rows}
                items = [
                    {
                        "id": r["id"],
                        "title": r["title"],
                        "author": (r["author"] or "").strip() or "저자 미상",
                        "cover_url": r["cover_url"],
                    }
                    for r in (by_id[i] for i in ids if i in by_id)
                ]
            else:
                items = []
                fq = fts_query(q)
                if fq:
                    try:
                        rows = conn.execute(
                            "SELECT b.id, b.title, b.author, b.cover_url "
                            "FROM books_fts f JOIN books b ON b.id = f.book_id "
                            "WHERE books_fts MATCH ? ORDER BY bm25(books_fts) LIMIT 10",
                            (fq,),
                        ).fetchall()
                        seen: set[str] = set()
                        for r in rows:
                            t = (r["title"] or "").strip()
                            if not t or t in seen:
                                continue
                            seen.add(t)
                            items.append(
                                {
                                    "id": r["id"],
                                    "title": t,
                                    "author": (r["author"] or "").strip() or "저자 미상",
                                    "cover_url": r["cover_url"],
                                }
                            )
                            if len(items) >= 7:
                                break
                    except Exception:
                        items = []

            # ③ 카탈로그에 없으면 온디맨드 제안
            if not items and q:
                try:
                    from .on_demand import search as od_search

                    live = od_search(q, limit=6)
                    items = [
                        {"id": x["id"], "title": x["title"], "author": x["author"], "cover_url": x["cover_url"]}
                        for x in live
                    ]
                except Exception:
                    items = []
            return self._json({"q": q, "suggestions": [x["title"] for x in items], "items": items})

        return self._json({"error": "unknown_endpoint", "path": path}, 404)

    # ---------------- static ----------------
    def serve_static(self, path: str):
        if path in ("/", ""):
            path = "/index.html"
        root = config.STATIC_DIR.resolve()
        target = (root / path.lstrip("/")).resolve()
        if not str(target).startswith(str(root)) or not target.is_file():
            not_found = root / "404.html"
            if not_found.is_file():
                return self._send(404, not_found.read_bytes(), "text/html; charset=utf-8")
            return self._send(404, b"not found", "text/plain; charset=utf-8")
        ext = target.suffix.lower()
        extra_types = {
            ".webmanifest": "application/manifest+json",
            ".png": "image/png",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
        }
        ctype = extra_types.get(ext) or mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        data = target.read_bytes()
        no_store = ext in (".html", ".js", ".css", ".webmanifest")
        cache = "no-store" if no_store else "public, max-age=300"
        return self._send(200, data, ctype, cache)


def serve(host: str | None = None, port: int | None = None):
    host = host or config.HOST
    port = int(port or config.PORT)
    app = get_app()
    if not app.book_count:
        print("[seoga] ⚠ books=0 — `python -m server.sync` 로 카탈로그를 먼저 적재하세요.")
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    print(f"[seoga] http://{host}:{port}  books={app.book_count} notices={app.notice_count}")
    print(f"[seoga] embed={app.meta.get('embed_backend')} dim={app.dim} vec={app.vec_backend}")
    try:
        from .on_demand import enabled as _od_enabled

        _od = _od_enabled()
    except Exception:
        _od = False
    print(f"[seoga] on_demand={_od} reports_bucket={bool(__import__('os').getenv('REPORTS_BUCKET'))}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[seoga] bye")
    finally:
        httpd.server_close()
