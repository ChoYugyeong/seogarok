"""GSC OAuth 연결 링크 생성 (1회, 콘솔 리디렉션 수정 불필요).

사용:
  python scripts/gsc_connect_link.py
출력된 URL을 브라우저에서 열어 구글 계정으로 승인하면,
서버가 refresh token을 GCS(auth/gsc_token.json)에 저장한다.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUCKET = "gs://seogarok-reports/auth/gsc_setup.json"


def gcloud() -> str:
    for cand in ("gcloud.cmd", "gcloud"):
        exe = shutil.which(cand)
        if exe:
            return exe
    raise SystemExit("gcloud 없음")


def main() -> int:
    token = secrets.token_urlsafe(32)
    payload = {
        "token_hash": hashlib.sha256(token.encode()).hexdigest(),
        "exp": int(time.time()) + 1800,
        "created_at": int(time.time()),
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump(payload, fh)
        tmp = fh.name
    try:
        r = subprocess.run([gcloud(), "storage", "cp", tmp, BUCKET], capture_output=True, text=True)
        if r.returncode != 0:
            print("업로드 실패:", r.stderr[:300])
            return 1
    finally:
        Path(tmp).unlink(missing_ok=True)
    print("연결 링크 (30분 내 1회):")
    print(f"https://seogarok.com/api/auth/gsc/start?t={token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
