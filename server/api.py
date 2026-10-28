"""서가 HTTP API + 정적 파일 서버 + 관측성 엔드포인트.

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

import json
import mimetypes
import os
import random
import threading
import time
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

VERSION = "0.3.0"
CHAOS_ENABLED = os.getenv("SEOG_CHAOS", "0") == "1"

# 런타임 장애 주입 상태 (게임데이/알림 검증용)
CHAOS = {"latency_ms": 0, "error_rate": 0.0}

# 라벨 카디널리티를 낮추기 위한 경로 정규화
_ROUTES = ("/api/search", "/api/book", "/api/notices", "/api/stats", "/api/suggest",
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
    server_version = "seoga/0.3"
    protocol_version = "HTTP/1.1"
    _status = 200

    # ---------------- utils ----------------
    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8", cache: str = "no-store"):
        self._status = code
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
        METRICS.set_gauge("seoga_index_documents", docs)
        METRICS.set_gauge("seoga_index_vectors", store.count())
        METRICS.set_gauge("seoga_notices_total", notices)
        ok, _ = app.readiness()
        METRICS.set_gauge("seoga_ready", 1 if ok else 0)
        # 인덱스 신선도: 마지막 sync 이후 경과 시간
        raw = app.meta.get("synced_at")
        if raw:
            try:
                import datetime as _dt

                ts = _dt.datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S%z")
                METRICS.set_gauge("seoga_index_age_seconds", max(0.0, (time.time() - ts.timestamp())))
            except ValueError:
                pass
        try:
            METRICS.set_gauge("seoga_db_size_bytes", Path(config.DB_PATH).stat().st_size)
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
                "strategy": dbg.extra.get("strategy"),
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
            conn, _ = app.ctx()
            rows = fetch_books(conn, [bid])
            if not rows:
                return self._json({"error": "not_found", "id": bid}, 404)
            row = rows[0]
            avs = fetch_availability(conn, [bid])
            nts = fetch_notices(conn, [bid])
            av, origins = build_availability(row, avs.get(bid, []), nts.get(bid, []))
            return self._json(serialize_book(row, av, origins, nts.get(bid, [])))

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

        if path == "/api/suggest":
            q = (qs.get("q") or [""])[0].strip()
            conn, _ = app.ctx()
            if not q:
                return self._json({"q": q, "suggestions": []})
            from .kotext import fts_query

            fq = fts_query(q)
            out = []
            if fq:
                try:
                    rows = conn.execute(
                        "SELECT b.title FROM books_fts f JOIN books b ON b.id = f.book_id "
                        "WHERE books_fts MATCH ? ORDER BY bm25(books_fts) LIMIT 8",
                        (fq,),
                    ).fetchall()
                    out = [r["title"] for r in rows]
                except Exception:
                    out = []
            return self._json({"q": q, "suggestions": out})

        return self._json({"error": "unknown_endpoint", "path": path}, 404)

    # ---------------- static ----------------
    def serve_static(self, path: str):
        if path in ("/", ""):
            path = "/index.html"
        root = config.STATIC_DIR.resolve()
        target = (root / path.lstrip("/")).resolve()
        if not str(target).startswith(str(root)) or not target.is_file():
            return self._send(404, b"not found", "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        data = target.read_bytes()
        cache = "no-store" if target.suffix in (".html", ".js", ".css") else "public, max-age=300"
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
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[seoga] bye")
    finally:
        httpd.server_close()
