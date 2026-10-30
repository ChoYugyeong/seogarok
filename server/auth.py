"""Google OAuth 로그인 + 기기 간 '내 서재' 동기화.

- 세션/사용자/서재는 GCS JSON(auth/...)에 저장 (런타임 DB는 읽기 전용)
- 비밀번호 없음(구글 OAuth), 세션 쿠키는 HttpOnly·Secure·SameSite=Lax
- 라우트:
    GET  /api/auth/google/start        → 구글 로그인 시작
    GET  /api/auth/google/callback     → 콜백(코드 교환·세션 발급)
    GET  /api/auth/me                  → 현재 사용자
    POST /api/auth/logout              → 로그아웃
    DELETE /api/auth/account           → 계정/서재 삭제
    GET|PUT /api/shelf                 → 서재 조회/저장(로그인 필요)
    POST /api/auth/merge               → 로컬 서재 병합
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.parse
import urllib.request

from . import store

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
SCOPE = "openid email profile"
GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
GSC_SETUP_PATH = "auth/gsc_setup.json"
GSC_TOKEN_PATH = "auth/gsc_token.json"
SESSION_COOKIE = "__Host-seogarok_session"
STATE_COOKIE = "__Host-seogarok_oauth_state"
SESSION_TTL = 30 * 86400
STATE_TTL = 600
SHELF_MAX = 500
_CONFIG_CACHE: dict | None = None


# ---------------- config ----------------
def _env_config() -> dict | None:
    cid = (os.getenv("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    csec = (os.getenv("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    if cid and csec:
        return {
            "client_id": cid,
            "client_secret": csec,
            "session_secret": (os.getenv("SESSION_SECRET") or "").strip() or cid,
            "redirect_uri": os.getenv("GOOGLE_OAUTH_REDIRECT_URI")
            or "https://seogarok.com/api/auth/google/callback",
        }
    return None


def config() -> dict | None:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    cfg = _env_config()
    if cfg is None:
        try:
            cfg = store.read_json("auth/config.json")
        except Exception:
            cfg = None
    if isinstance(cfg, dict) and cfg.get("client_id") and cfg.get("client_secret"):
        cfg.setdefault("redirect_uri", "https://seogarok.com/api/auth/google/callback")
        cfg.setdefault("session_secret", cfg["client_id"])
        _CONFIG_CACHE = cfg
        return cfg
    return None


# ---------------- cookies / state ----------------
_RATE: dict = {}
_RATE_WINDOW = 60
_RATE_MAX = 30


def _client_ip(handler) -> str:
    ip = (handler.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    if not ip:
        ip = (handler.client_address[0] if getattr(handler, "client_address", None) else "") or "unknown"
    return ip


def _rate_ok(handler) -> bool:
    ip = _client_ip(handler)
    now = time.time()
    arr = [t for t in (_RATE.get(ip) or []) if now - t < _RATE_WINDOW]
    if len(arr) >= _RATE_MAX:
        _RATE[ip] = arr
        return False
    arr.append(now)
    _RATE[ip] = arr[-60:]
    return True


def _origin_ok(handler) -> bool:
    """상태 변경 요청의 출처 검증(CSRF 방어)."""
    origin = (handler.headers.get("Origin") or "").strip()
    if not origin:
        # Origin 없는 요청(서버 간/테스트)은 SameSite=Lax 쿠키로 보호되므로 허용
        return handler.headers.get("Sec-Fetch-Site") != "cross-site"
    allowed = {"https://seogarok.com", "http://127.0.0.1:8104", "http://localhost:8104"}
    if origin in allowed:
        return True
    # 로컬 개발 포트 변형 허용
    if origin.startswith("http://127.0.0.1:") or origin.startswith("http://localhost:"):
        return True
    return False


def parse_cookies(header: str | None) -> dict:
    out: dict[str, str] = {}
    for part in (header or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _sign(value: str) -> str:
    cfg = config() or {}
    secret = str(cfg.get("session_secret") or "fallback")
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()[:32]


def make_state() -> str:
    state = secrets.token_urlsafe(24)
    return f"{state}.{_sign(state)}"


def check_state(cookie_value: str | None, state: str | None) -> bool:
    """state 쿼리와 서명 쿠키가 동일한지 검증.

    make_state()는 `랜덤.서명` 전체를 만들고 쿠키에도 전체를 저장하므로
    쿼리 state와 쿠키 값 전체를 비교한 뒤 서명을 검증한다.
    """
    if not cookie_value or not state:
        return False
    if not hmac.compare_digest(cookie_value, state):
        return False
    try:
        raw, sig = state.rsplit(".", 1)
    except ValueError:
        return False
    return hmac.compare_digest(sig, _sign(raw))


def _cookie(name: str, value: str, max_age: int, secure: bool = True) -> str:
    parts = [f"{name}={value}", "Path=/", "HttpOnly", "SameSite=Lax", f"Max-Age={max_age}"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


# ---------------- users / sessions / shelf ----------------
def _hash_session(sid: str) -> str:
    return hashlib.sha256(sid.encode()).hexdigest()


def _user_path(sub: str) -> str:
    return f"auth/users/{sub}.json"


def upsert_user(info: dict) -> dict:
    sub = str(info.get("sub") or "").strip()
    now = int(time.time())
    prev = store.read_json(_user_path(sub)) or {}
    user = {
        "sub": sub,
        "email": (info.get("email") or "").strip(),
        "name": (info.get("name") or "").strip(),
        "picture": (info.get("picture") or "").strip(),
        "email_verified": bool(info.get("email_verified")),
        "created_at": prev.get("created_at") or now,
        "last_login": now,
        "sessions": prev.get("sessions") or [],
    }
    store.write_json(_user_path(sub), user)
    return user


def new_session(user: dict) -> str:
    sid = secrets.token_urlsafe(32)
    h = _hash_session(sid)
    store.write_json(
        f"auth/sessions/{h}.json",
        {"sub": user["sub"], "exp": int(time.time()) + SESSION_TTL, "created_at": int(time.time())},
    )
    sessions = list(user.get("sessions") or [])
    sessions = (sessions + [h])[-20:]
    user["sessions"] = sessions
    store.write_json(_user_path(user["sub"]), user)
    return sid


def current_user(cookie_header: str | None) -> dict | None:
    sid = parse_cookies(cookie_header).get(SESSION_COOKIE)
    if not sid:
        return None
    h = _hash_session(sid)
    sess = store.read_json(f"auth/sessions/{h}.json")
    if not sess or int(sess.get("exp") or 0) < int(time.time()):
        return None
    user = store.read_json(_user_path(str(sess.get("sub") or "")))
    if not user:
        return None
    return {"sub": user["sub"], "email": user.get("email", ""), "name": user.get("name", ""), "picture": user.get("picture", "")}


def logout(cookie_header: str | None) -> None:
    sid = parse_cookies(cookie_header).get(SESSION_COOKIE)
    if sid:
        store.delete(f"auth/sessions/{_hash_session(sid)}.json")


def delete_account(user: dict) -> None:
    for h in user.get("sessions") or []:
        store.delete(f"auth/sessions/{h}.json")
    store.delete(_user_path(user["sub"]))
    store.delete(f"auth/shelves/{user['sub']}.json")
    try:
        from . import push

        push.delete_user_subscriptions(user["sub"])
    except Exception:
        pass


def get_shelf(sub: str) -> dict:
    data = store.read_json(f"auth/shelves/{sub}.json") or {}
    return {
        "want": [str(x) for x in (data.get("want") or [])][:SHELF_MAX],
        "reading": [str(x) for x in (data.get("reading") or [])][:SHELF_MAX],
        "done": [str(x) for x in (data.get("done") or [])][:SHELF_MAX],
        "alerts": data.get("alerts") if isinstance(data.get("alerts"), dict) else {},
        "pushLeads": [int(x) for x in (data.get("pushLeads") or []) if isinstance(x, int)][:6],
        "updated_at": data.get("updated_at") or 0,
    }


def _clean_ids(items) -> list[str]:
    out: list[str] = []
    for x in items or []:
        s = str(x).strip()
        if s and s not in out and len(s) <= 80:
            out.append(s)
        if len(out) >= SHELF_MAX:
            break
    return out


def put_shelf(sub: str, shelf: dict) -> dict:
    alerts = shelf.get("alerts") if isinstance(shelf.get("alerts"), dict) else {}
    leads = [int(x) for x in (shelf.get("pushLeads") or []) if isinstance(x, (int, float)) and 0 <= int(x) <= 30][:6]
    data = {
        "want": _clean_ids(shelf.get("want")),
        "reading": _clean_ids(shelf.get("reading")),
        "done": _clean_ids(shelf.get("done")),
        "alerts": {str(k)[:80]: v for k, v in list(alerts.items())[:SHELF_MAX]},
        "pushLeads": sorted(set(leads), reverse=True) or [7, 3, 1, 0],
        "updated_at": int(time.time()),
    }
    store.write_json(f"auth/shelves/{sub}.json", data)
    return data


def merge_shelf(sub: str, incoming: dict) -> dict:
    cur = get_shelf(sub)
    for key in ("want", "reading", "done"):
        ids = cur.get(key) or []
        for x in _clean_ids(incoming.get(key)):
            if x not in ids:
                ids.append(x)
        cur[key] = ids[:SHELF_MAX]
    alerts = dict(cur.get("alerts") or {})
    for k, v in (incoming.get("alerts") or {}).items():
        alerts[str(k)[:80]] = v
    cur["alerts"] = alerts
    if incoming.get("pushLeads"):
        cur["pushLeads"] = incoming["pushLeads"]
    cur.pop("updated_at", None)
    return put_shelf(sub, cur)


# ---------------- handlers ----------------
def _redirect(handler, location: str, cookies: list[str] | None = None):
    handler._send(302, b"", "text/plain; charset=utf-8", extra_headers=[("Location", location)] + [(("Set-Cookie"), c) for c in (cookies or [])])


def _json_headers(handler, obj, code=200, cookies: list[str] | None = None):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler._send(code, body, "application/json; charset=utf-8", extra_headers=[("Set-Cookie", c) for c in (cookies or [])])


def handle_auth(handler, method: str, parsed, qs: dict):
    path = parsed.path
    cfg = config()

    if not _rate_ok(handler):
        return _json_headers(handler, {"error": "rate_limited"}, 429)
    if method in ("POST", "PUT", "DELETE") and not _origin_ok(handler):
        return _json_headers(handler, {"error": "cross_origin_blocked"}, 403)

    if path == "/api/auth/gsc/start":
        if method != "GET" or not cfg:
            return _json_headers(handler, {"error": "auth_unavailable"}, 503)
        import hashlib

        token = (qs.get("t") or [""])[0].strip()
        setup = store.read_json(GSC_SETUP_PATH) or {}
        exp = int(setup.get("exp") or 0)
        if not token or int(time.time()) > exp or hashlib.sha256(token.encode()).hexdigest() != setup.get("token_hash"):
            return _redirect(handler, "/?gsc=invalid")
        state = make_state()
        params = {
            "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"],
            "response_type": "code",
            "scope": GSC_SCOPE,
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return _redirect(
            handler,
            AUTH + "?" + urllib.parse.urlencode(params),
            cookies=[_cookie(STATE_COOKIE, state, STATE_TTL)],
        )

    if path == "/api/auth/google/start":
        if method != "GET" or not cfg:
            return _json_headers(handler, {"error": "auth_unavailable"}, 503)
        state = make_state()
        params = {
            "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"],
            "response_type": "code",
            "scope": SCOPE,
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
        return _redirect(
            handler,
            AUTH + "?" + urllib.parse.urlencode(params),
            cookies=[_cookie(STATE_COOKIE, state, STATE_TTL)],
        )

    if path == "/api/auth/google/callback":
        if not cfg:
            return _json_headers(handler, {"error": "auth_unavailable"}, 503)
        code = (qs.get("code") or [""])[0]
        state = (qs.get("state") or [""])[0]
        cookies = parse_cookies(handler.headers.get("Cookie"))
        if (qs.get("error") or [""])[0] or not code or not check_state(cookies.get(STATE_COOKIE), state):
            return _redirect(handler, "/?login=error", cookies=[_cookie(STATE_COOKIE, "", 0)])
        data = urllib.parse.urlencode(
            {
                "code": code,
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "redirect_uri": cfg["redirect_uri"],
                "grant_type": "authorization_code",
            }
        ).encode()
        if state.startswith("gsc."):
            try:
                req = urllib.request.Request(
                    TOKEN, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                with urllib.request.urlopen(req, timeout=15) as r:
                    tok = json.loads(r.read().decode())
                refresh = tok.get("refresh_token")
                if refresh:
                    store.write_json(
                        GSC_TOKEN_PATH,
                        {
                            "refresh_token": refresh,
                            "scope": tok.get("scope") or GSC_SCOPE,
                            "created_at": int(time.time()),
                        },
                    )
                    return _redirect(handler, "/?gsc=ok", cookies=[_cookie(STATE_COOKIE, "", 0)])
            except Exception:
                pass
            return _redirect(handler, "/?gsc=error", cookies=[_cookie(STATE_COOKIE, "", 0)])
        try:
            req = urllib.request.Request(
                TOKEN, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                tok = json.loads(r.read().decode())
            access = tok.get("access_token") or ""
            req2 = urllib.request.Request(USERINFO, headers={"Authorization": f"Bearer {access}"})
            with urllib.request.urlopen(req2, timeout=15) as r2:
                info = json.loads(r2.read().decode())
        except Exception as exc:
            try:
                from .api import log_event

                log_event(level="warn", msg="oauth_callback_failed", error=str(exc)[:200])
            except Exception:
                pass
            return _redirect(handler, "/?login=error", cookies=[_cookie(STATE_COOKIE, "", 0)])
        if info.get("email_verified") is False:
            return _redirect(handler, "/?login=error", cookies=[_cookie(STATE_COOKIE, "", 0)])
        user = upsert_user(info)
        sid = new_session(user)
        return _redirect(
            handler,
            "/?login=1",
            cookies=[
                _cookie(STATE_COOKIE, "", 0),
                _cookie(SESSION_COOKIE, sid, SESSION_TTL),
            ],
        )

    user = current_user(handler.headers.get("Cookie"))

    if path == "/api/auth/me":
        if not user:
            return _json_headers(handler, {"user": None})
        return _json_headers(handler, {"user": user})

    if path == "/api/auth/logout":
        if method != "POST":
            return _json_headers(handler, {"error": "method_not_allowed"}, 405)
        logout(handler.headers.get("Cookie"))
        return _json_headers(handler, {"ok": True}, cookies=[_cookie(SESSION_COOKIE, "", 0)])

    if path == "/api/auth/account":
        if not user:
            return _json_headers(handler, {"error": "unauthorized"}, 401)
        if method != "DELETE":
            return _json_headers(handler, {"error": "method_not_allowed"}, 405)
        delete_account(store.read_json(_user_path(user["sub"])) or user)
        return _json_headers(handler, {"ok": True}, cookies=[_cookie(SESSION_COOKIE, "", 0)])

    if path == "/api/shelf":
        if not user:
            return _json_headers(handler, {"error": "unauthorized"}, 401)
        if method == "GET":
            return _json_headers(handler, {"shelf": get_shelf(user["sub"])})
        if method == "PUT":
            body = handler._read_json_body() or {}
            shelf = put_shelf(user["sub"], body)
            return _json_headers(handler, {"shelf": shelf})
        return _json_headers(handler, {"error": "method_not_allowed"}, 405)

    if path == "/api/auth/merge":
        if not user:
            return _json_headers(handler, {"error": "unauthorized"}, 401)
        if method != "POST":
            return _json_headers(handler, {"error": "method_not_allowed"}, 405)
        body = handler._read_json_body() or {}
        shelf = merge_shelf(user["sub"], body)
        return _json_headers(handler, {"shelf": shelf})

    return _json_headers(handler, {"error": "not_found"}, 404)
