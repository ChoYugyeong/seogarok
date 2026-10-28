"""카탈로그·공지 -> SQLite 인덱스 동기화 CLI.

사용:
  python -m server.sync                      # data/catalog.jsonl (+ notices.jsonl) 적재
  python -m server.sync --catalog data/seed_catalog.jsonl
  python -m server.sync --embed hashing      # 모델 없이 빠르게
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config
from .db import connect, load_catalog_rows, load_notice_rows, meta, sync_catalog, sync_notices
from .embed import get_embedder

SEED = Path(config.DATA_DIR) / "seed_catalog.jsonl"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="서가 인덱스 동기화")
    ap.add_argument("--catalog", default=str(config.CATALOG_PATH), help="도서 카탈로그 JSONL")
    ap.add_argument("--notices", default=str(config.NOTICES_PATH), help="종료 공지 JSONL")
    ap.add_argument("--db", default=str(config.DB_PATH), help="SQLite 파일 경로")
    ap.add_argument("--embed", default=config.EMBED_BACKEND, help="auto|model2vec|hashing")
    ap.add_argument("--no-seed", action="store_true", help="카탈로그 없을 때 seed 사용 안 함")
    args = ap.parse_args(argv)

    rows = load_catalog_rows(Path(args.catalog))
    src = args.catalog
    if not rows and not args.no_seed and SEED.exists():
        print(f"[sync] {args.catalog} 없음 -> seed 사용: {SEED}")
        rows = load_catalog_rows(SEED)
        src = str(SEED)
    if not rows:
        print(f"[sync] 카탈로그가 비어 있습니다: {args.catalog}")
        return 2

    print(f"[sync] catalog={src} rows={len(rows)}")
    embedder = get_embedder(args.embed)
    print(f"[sync] embedder={embedder.name} dim={embedder.dim}")

    conn = connect(Path(args.db))
    result = sync_catalog(conn, embedder, rows)
    print(f"[sync] books={result['books']} vectors={result['vectors']} "
          f"vec_backend={result['vector_backend']} {result['seconds']}s")

    nrows = load_notice_rows(Path(args.notices))
    if nrows:
        nres = sync_notices(conn, nrows)
        print(f"[sync] notices={nres['notices']} matched_to_catalog={nres['matched_to_catalog']}")
    else:
        print(f"[sync] notices 없음 ({args.notices})")

    m = meta(conn)
    print("[sync] meta:", {k: m[k] for k in sorted(m)})
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
