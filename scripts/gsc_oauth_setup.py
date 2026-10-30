"""GSC OAuth 초기 설정 (1회 실행) — refresh token 발급.

준비:
1. GCP Console → API 및 서비스 → 사용자 인증 정보 → OAuth 클라이언트 ID 만들기
   → 애플리케이션 유형: **데스크톱 앱**
2. 클라이언트 ID/Secret을 아래 env 또는 인자로 전달

실행:
  set GSC_CLIENT_ID=...  (PowerShell: $env:GSC_CLIENT_ID="...")
  set GSC_CLIENT_SECRET=...
  python scripts/gsc_oauth_setup.py

동작:
- 127.0.0.1:8765 로컬 콜백 서버를 띄우고 인증 URL을 출력
- 브라우저에서 승인하면 refresh token을 받아 .env에 저장
- 이후 scripts/set_gsc_secrets.ps1 로 GitHub Secret 등록
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import socket
import threading
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
REDIRECT = "http://127.0.0.1:8765/"
AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"


def load_env() -> dict:
    out = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def save_env(updates: dict) -> None:
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    keys = set()
    for i, line in enumerate(lines):
        if "=" in line and not line.strip().startswith("#"):
            k = line.split("=", 1)[0].strip()
            if k in updates:
                lines[i] = f"{k}={updates[k]}"
                keys.add(k)
    for k, v in updates.items():
        if k not in keys:
            lines.append(f"{k}={v}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="GSC OAuth refresh token 발급")
    ap.add_argument("--client-id", default=os.getenv("GSC_CLIENT_ID", ""))
    ap.add_argument("--client-secret", default=os.getenv("GSC_CLIENT_SECRET", ""))
    args = ap.parse_args(argv)
    client_id = args.client_id.strip()
    client_secret = args.client_secret.strip()
    if not client_id or not client_secret:
        print("[oauth] GSC_CLIENT_ID / GSC_CLIENT_SECRET 필요")
        print("  GCP Console → 사용자 인증 정보 → OAuth 클라이언트(데스크톱 앱) 생성")
        return 1

    result: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            code = (qs.get("code") or [""])[0]
            error = (qs.get("error") or [""])[0]
            if error:
                result["error"] = error
            elif code:
                result["code"] = code
            body = "<h1>서가록 GSC 연동 완료</h1><p>이 창을 닫아도 됩니다.</p>".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 8765), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    url = AUTH + "?" + urllib.parse.urlencode(params)
    print("\n[oauth] 아래 URL을 브라우저에서 열어 승인하세요:\n")
    print(url + "\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass

    for _ in range(300):
        if "code" in result or "error" in result:
            break
        threading.Event().wait(0.2)
    server.shutdown()

    if result.get("error"):
        print("[oauth] 인증 실패:", result["error"])
        return 1
    code = result.get("code")
    if not code:
        print("[oauth] 시간 초과 — 다시 실행하세요")
        return 1

    data = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT,
            "grant_type": "authorization_code",
        }
    ).encode()
    req = urllib.request.Request(TOKEN, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        tok = json.loads(r.read().decode())
    refresh = tok.get("refresh_token")
    if not refresh:
        print("[oauth] refresh_token 없음 — prompt=consent 로 다시 시도")
        return 1

    save_env(
        {
            "GSC_CLIENT_ID": client_id,
            "GSC_CLIENT_SECRET": client_secret,
            "GSC_REFRESH_TOKEN": refresh,
        }
    )
    print("[oauth] refresh token 저장 완료: .env (GSC_REFRESH_TOKEN)")
    print("[oauth] GitHub Secret 등록: pwsh -NoProfile -File scripts/set_gsc_secrets.ps1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
