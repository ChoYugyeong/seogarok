"""개인정보 요청(GCS) → GitHub Issue 생성 (중복 방지). GitHub Actions에서 실행."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

PREFIX = "gs://seogarok-reports/privacy/requests/"


def tool(names: list[str]) -> str:
    for n in names:
        exe = shutil.which(n)
        if exe:
            return exe
    raise SystemExit(f"필요한 명령 없음: {names}")


GCLOUD = tool(["gcloud.cmd", "gcloud"])
GH = tool(["gh", "gh.cmd"])


def run(cmd: list[str], check: bool = True) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        print("[privacy] cmd 실패:", " ".join(cmd), r.stderr[:300], file=sys.stderr)
    return r.stdout


def main() -> int:
    # 라벨 준비(없으면 생성)
    run([GH, "label", "create", "privacy-request", "--description", "개인정보 열람/삭제 요청", "--color", "b42318"], check=False)

    listing = run([GCLOUD, "storage", "ls", PREFIX], check=False)
    uris = [ln.strip() for ln in listing.splitlines() if ln.strip().endswith(".json")]
    print(f"[privacy] requests: {len(uris)}")
    created = 0
    for uri in uris:
        ref = uri.rsplit("/", 1)[-1].removesuffix(".json")
        title = f"[개인정보 요청] {ref}"
        existing = run(
            [GH, "issue", "list", "--search", f'"{title}" in:title', "--state", "all", "--json", "number"],
            check=False,
        )
        try:
            if json.loads(existing or "[]"):
                continue
        except Exception:
            pass
        raw = run([GCLOUD, "storage", "cat", uri], check=False)
        try:
            rec = json.loads(raw)
        except Exception:
            continue
        # 공개 저장소 이슈에는 개인정보를 넣지 않는다 (ref만).
        # 내용 확인: gcloud storage cat gs://seogarok-reports/privacy/requests/{ref}.json
        body = "\n".join(
            [
                f"**접수번호**: `{ref}`",
                f"**유형**: {rec.get('type_label')} (`{rec.get('type')}`)",
                f"**접수 시각**: {rec.get('created_at')}",
                "",
                "> 개인정보 보호를 위해 이메일·요청 내용은 이슈에 표시하지 않습니다.",
                f"> 확인: `gcloud storage cat gs://seogarok-reports/privacy/requests/{ref}.json`",
                "",
                "처리 후 7일 이내 회신하고 이 이슈를 닫으세요. 상세 내용은 비공개 GCS 객체를 참조하세요.",
            ]
        )
        out = run([GH, "issue", "create", "--title", title, "--body", body, "--label", "privacy-request"], check=False)
        if out.strip():
            created += 1
            print(f"[privacy] created: {ref} -> {out.strip()}")
    print(f"[privacy] done. created={created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
