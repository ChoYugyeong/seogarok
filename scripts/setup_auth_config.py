"""OAuth 클라이언트 설정 → GCS(auth/config.json) 업로드 + .env 저장.

사용:
  python scripts/setup_auth_config.py [client_secret.json 경로]
"""
from __future__ import annotations

import json
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
BUCKET = "gs://seogarok-reports/auth/config.json"
DEFAULT_JSON = Path.home() / "Downloads"
PROJECT = "seoga-prod"


def load_client(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    d = raw.get("web") or raw.get("installed") or {}
    cid = d.get("client_id")
    csec = d.get("client_secret")
    if not cid or not csec:
        raise SystemExit(f"client_id/client_secret 없음: {path}")
    return {"client_id": cid, "client_secret": csec}


def find_client(path_arg: str | None) -> Path:
    if path_arg:
        return Path(path_arg)
    candidates = sorted(DEFAULT_JSON.glob("client_secret_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise SystemExit("client_secret_*.json을 찾지 못했습니다. 경로를 인자로 주세요.")
    return candidates[0]


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


def gcloud() -> str:
    import shutil

    for cand in ("gcloud.cmd", "gcloud"):
        exe = shutil.which(cand)
        if exe:
            return exe
    raise SystemExit("gcloud 없음")


def main(argv=None) -> int:
    args = sys.argv[1:]
    path = find_client(args[0] if args else None)
    client = load_client(path)
    print(f"[auth] client: {path.name}")

    config = {
        **client,
        "redirect_uri": "https://seogarok.com/api/auth/google/callback",
        "session_secret": secrets.token_urlsafe(32),
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False)
        tmp = fh.name
    try:
        cmd = [gcloud(), "storage", "cp", tmp, BUCKET]
        r = subprocess.run(cmd, capture_output=True, text=True)
        print("[auth] GCS upload:", r.returncode, (r.stderr or "").strip()[:160])
        if r.returncode != 0:
            return 1
    finally:
        Path(tmp).unlink(missing_ok=True)

    save_env(
        {
            "GOOGLE_OAUTH_CLIENT_ID": client["client_id"],
            "GOOGLE_OAUTH_CLIENT_SECRET": client["client_secret"],
            "SESSION_SECRET": config["session_secret"],
            "GSC_CLIENT_ID": client["client_id"],
            "GSC_CLIENT_SECRET": client["client_secret"],
        }
    )
    print("[auth] .env 저장 완료 (클라이언트/세션 시크릿)")
    print("[auth] 완료 — 서버는 GCS auth/config.json 을 읽어 로그인 활성화")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
