"""API 응답 캐시를 GCS에 아카이브/복원 (머신 간 재사용).

사용:
  python scripts/enrich_cache_sync.py status
  python scripts/enrich_cache_sync.py pull   # GCS → 로컬
  python scripts/enrich_cache_sync.py push   # 로컬 → GCS
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "enrich_cache"
BUCKET = "gs://seogarok-reports/enrich-cache/enrich_cache.tar.gz"


def _tool() -> list[str] | None:
    # Windows: .cmd 래퍼 필요 (gsutil.cmd / gcloud.cmd)
    for cand in ("gcloud.cmd", "gcloud"):
        if shutil.which(cand):
            return [shutil.which(cand), "storage"]
    for cand in ("gsutil.cmd", "gsutil"):
        if shutil.which(cand):
            return [shutil.which(cand)]
    return None


def _run(cmd: list[str]) -> int:
    print("[cache-sync]", " ".join(cmd))
    return subprocess.call(cmd)


def status() -> int:
    files = list(CACHE_DIR.rglob("*.json")) if CACHE_DIR.exists() else []
    total = sum(f.stat().st_size for f in files)
    print(f"local cache: {len(files)} files, {total / 1024:.1f}KB")
    tool = _tool()
    if not tool:
        print("gsutil/gcloud 없음 — GCS 동기화 불가")
        return 0
    return _run(tool + ["ls", "-l", BUCKET])


def pull() -> int:
    tool = _tool()
    if not tool:
        print("gsutil/gcloud 없음")
        return 1
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tar_path = Path(tmp) / "enrich_cache.tar.gz"
        if _run(tool + ["cp", BUCKET, str(tar_path)]) != 0:
            print("[cache-sync] GCS 아카이브 없음 — 신규")
            return 0
        with tarfile.open(tar_path, "r:gz") as tf:
            tf.extractall(ROOT / "data")
    n = len(list(CACHE_DIR.rglob("*.json")))
    print(f"[cache-sync] pulled — {n} files")
    return 0


def push() -> int:
    tool = _tool()
    if not tool:
        print("gsutil/gcloud 없음")
        return 1
    files = list(CACHE_DIR.rglob("*.json")) if CACHE_DIR.exists() else []
    if not files:
        print("[cache-sync] 로컬 캐시 없음 — 생략")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        tar_path = Path(tmp) / "enrich_cache.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tf:
            tf.add(CACHE_DIR, arcname="enrich_cache")
        print(f"[cache-sync] tar: {len(files)} files, {tar_path.stat().st_size / 1024:.1f}KB")
        return _run(tool + ["cp", str(tar_path), BUCKET])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="enrich cache GCS 동기화")
    ap.add_argument("action", choices=["status", "pull", "push"])
    args = ap.parse_args(argv)
    return {"status": status, "pull": pull, "push": push}[args.action]()


if __name__ == "__main__":
    raise SystemExit(main())
