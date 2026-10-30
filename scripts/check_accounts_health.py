"""로그인/서재/푸시 연결 상태 점검 (개인정보 미출력, 개수만)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def gcloud() -> str:
    for cand in ("gcloud.cmd", "gcloud"):
        exe = shutil.which(cand)
        if exe:
            return exe
    raise SystemExit("gcloud 없음")


def ls(prefix: str) -> list[str]:
    r = subprocess.run([gcloud(), "storage", "ls", f"gs://seogarok-reports/{prefix}"], capture_output=True, text=True)
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip().endswith(".json")]


def cat(uri: str) -> dict:
    r = subprocess.run([gcloud(), "storage", "cat", uri], capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        return {}


def main() -> int:
    users = ls("auth/users/")
    shelves = ls("auth/shelves/")
    sessions = ls("auth/sessions/")
    push_subs = ls("push/subs/")
    push_users = ls("push/users/")
    linked = 0
    for uri in push_subs:
        rec = cat(uri)
        if rec.get("user_sub"):
            linked += 1
    print(f"로그인 사용자: {len(users)}")
    print(f"동기화 서재: {len(shelves)}")
    print(f"활성 세션 객체: {len(sessions)}")
    print(f"푸시 구독: {len(push_subs)} (계정 연결됨: {linked})")
    print(f"푸시 연결 계정 인덱스: {len(push_users)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
