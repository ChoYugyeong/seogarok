"""커밋용 fallback 스냅샷 재생성 (설명 최대 800자 유지).

사용:
  python scripts/rebuild_fallback.py [--catalog data/catalog.jsonl] [--out data/catalog_fallback.jsonl.gz]
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="fallback 카탈로그 재생성")
    ap.add_argument("--catalog", default=str(ROOT / "data" / "catalog.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "data" / "catalog_fallback.jsonl.gz"))
    ap.add_argument("--max-desc", type=int, default=800)
    args = ap.parse_args(argv)

    src = Path(args.catalog)
    dst = Path(args.out)
    if not src.exists():
        print(f"[fallback] catalog 없음: {src}")
        return 1

    lines = [ln for ln in src.open(encoding="utf-8") if ln.strip()]
    out = io.BytesIO()
    rows = 0
    with gzip.GzipFile(fileobj=out, mode="wb", compresslevel=9, mtime=0) as gz:
        for line in lines:
            obj = json.loads(line)
            desc = " ".join((obj.get("description") or "").split())
            obj["description"] = desc[: args.max_desc] or None
            gz.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
            rows += 1
    dst.write_bytes(out.getvalue())

    with_desc = 0
    with gzip.open(dst, "rt", encoding="utf-8") as f:
        for line in f:
            if (json.loads(line).get("description") or ""):
                with_desc += 1
    size_mb = os.path.getsize(dst) / 1024 / 1024
    print(f"[fallback] rows={rows} with_desc={with_desc} size={size_mb:.2f}MB -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
