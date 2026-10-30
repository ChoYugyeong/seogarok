"""GSC 연결 후 refresh token 회수 → .env 저장 (GitHub Secret 등록은 set_gsc_secrets.ps1)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
URI = "gs://seogarok-reports/auth/gsc_token.json"


def gcloud() -> str:
    for cand in ("gcloud.cmd", "gcloud"):
        exe = shutil.which(cand)
        if exe:
            return exe
    raise SystemExit("gcloud 없음")


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


def main() -> int:
    exe = gcloud()
    r = subprocess.run([exe, "storage", "cat", URI], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        print("GSC 토큰 없음 — 먼저 연결 링크를 승인하세요.")
        return 1
    data = json.loads(r.stdout)
    refresh = data.get("refresh_token")
    if not refresh:
        print("refresh_token 없음")
        return 1

    env = {}
    for line in (ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []):
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    updates = {"GSC_REFRESH_TOKEN": refresh}
    for k in ("GSC_CLIENT_ID", "GSC_CLIENT_SECRET"):
        if env.get(k):
            updates[k] = env[k]
    save_env(updates)
    print("GSC refresh token 저장 완료 (.env)")
    print("다음: pwsh -NoProfile -File scripts/set_gsc_secrets.ps1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
