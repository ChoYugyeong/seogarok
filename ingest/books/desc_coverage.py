"""카탈로그 설명 커버리지 출력 (CI 로그용): d/n 형식."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "data" / "catalog.jsonl"
    n = 0
    d = 0
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            n += 1
            try:
                r = json.loads(line)
            except Exception:
                continue
            if len((r.get("description") or "").strip()) > 20:
                d += 1
    print(f"{d}/{n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
