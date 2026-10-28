"""빌드 시점 데이터 준비: 운영 데이터(API 수집분)가 없으면 seed(38권)로 폴백.

- data/catalog.jsonl  : `python -m ingest.books.yes24_api` 로 생성 (공식 API, .gitignore)
- data/notices.jsonl  : `python -m ingest.notices.run` 으로 생성 (밀리 공개 목록, .gitignore)
둘 다 없으면 data/seed_catalog.jsonl(직접 작성한 38권) 로 데모 인덱스를 만든다.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def main() -> int:
    catalog = DATA / "catalog.jsonl"
    seed = DATA / "seed_catalog.jsonl"
    notices = DATA / "notices.jsonl"

    if not catalog.exists():
        if not seed.exists():
            print("[prepare] catalog.jsonl 과 seed_catalog.jsonl 이 모두 없습니다", file=sys.stderr)
            return 2
        shutil.copyfile(seed, catalog)
        print(f"[prepare] 운영 카탈로그 없음 → seed 폴백 ({seed.name} → catalog.jsonl)")

    if not notices.exists():
        notices.write_text("", encoding="utf-8")
        print("[prepare] notices.jsonl 없음 → 빈 파일 생성 (종료 공지 없이 기동)")

    n_cat = sum(1 for _ in catalog.open(encoding="utf-8"))
    n_not = sum(1 for _ in notices.open(encoding="utf-8"))
    print(f"[prepare] catalog={n_cat} notices={n_not}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
