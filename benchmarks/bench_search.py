"""검색 성능/품질 벤치마크.

1) 실제 카탈로그에서 모드별 지연시간(p50/p95)과 후보 수
2) 렉시컬(FTS5) vs 벡터(sqlite-vec) vs 하이브리드 결과 비교
3) 벡터 인덱스 확장성: 합성 벡터 1k/10k/50k 에서 KNN 지연
결과는 data/bench_report.json + 콘솔 요약.
"""
from __future__ import annotations

import json
import random
import sqlite3
import statistics
import time
from pathlib import Path

import numpy as np

from server import config
from server.db import VectorStore, connect
from server.embed import get_embedder
from server.search import fetch_books, search

QUERIES = [
    "채식주의자", "한강", "김초엽", "SF 소설", "우주 과학 소설",
    "따뜻한 힐링 소설", "인공지능과 미래", "죽음과 상실", "에세이", "역사 교양",
    "소년이 온다", "불편한 편의점", "쇼펜하우어", "사피엔스",
]
MODES = ["keyword", "vector", "hybrid"]
REPS = 5


def pct(vals, p):
    if not vals:
        return 0.0
    vals = sorted(vals)
    k = (len(vals) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(vals) - 1)
    return round(vals[lo] + (vals[hi] - vals[lo]) * (k - lo), 3)


def bench_queries():
    embedder = get_embedder()
    conn = connect()
    store = VectorStore(conn, embedder.dim)
    print(f"[bench] books={conn.execute('SELECT count(*) FROM books').fetchone()[0]} "
          f"vectors={store.count()} backend={store.backend} embed={embedder.name} dim={embedder.dim}")

    out = {m: {"lat": [], "counts": [], "server_ms": []} for m in MODES}
    per_query = {}

    for q in QUERIES:
        per_query[q] = {}
        for mode in MODES:
            for _ in range(REPS):
                t = time.perf_counter()
                ids, dbg = search(conn, store, embedder, q, mode=mode, limit=24)
                dt = (time.perf_counter() - t) * 1000
                out[mode]["lat"].append(dt)
                out[mode]["counts"].append(len(ids))
                out[mode]["server_ms"].append(dbg.keyword_ms + dbg.vector_ms + dbg.fuse_ms)
            ids, _ = search(conn, store, embedder, q, mode=mode, limit=6)
            rows = fetch_books(conn, ids)
            per_query[q][mode] = [r["title"] for r in rows]

    summary = {}
    for mode in MODES:
        lat = out[mode]["lat"]
        summary[mode] = {
            "p50_ms": pct(lat, 0.5),
            "p95_ms": pct(lat, 0.95),
            "max_ms": round(max(lat), 3),
            "avg_results": round(statistics.mean(out[mode]["counts"]), 1),
        }
    return summary, per_query


def bench_vector_scale(sizes=(1000, 10000, 50000), dim=256, k=10):
    """합성 벡터로 vec0 KNN 확장성 측정 (별도 DB)."""
    path = Path(config.DATA_DIR) / "bench_vectors.db"
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(str(path))
    try:
        import sqlite_vec

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        vec_ok = True
    except Exception as e:
        print("[bench] sqlite-vec 로드 실패:", e)
        vec_ok = False

    results = []
    rng = np.random.default_rng(42)
    for n in sizes:
        if not vec_ok:
            break
        conn.execute("DROP TABLE IF EXISTS v")
        conn.execute(f"CREATE VIRTUAL TABLE v USING vec0(id text primary key, embedding float[{dim}])")
        mat = rng.normal(size=(n, dim)).astype(np.float32)
        mat /= np.linalg.norm(mat, axis=1, keepdims=True)
        t0 = time.perf_counter()
        conn.executemany(
            "INSERT INTO v(id, embedding) VALUES (?, ?)",
            [(f"id{i}", mat[i].tobytes()) for i in range(n)],
        )
        conn.commit()
        insert_s = time.perf_counter() - t0

        q = rng.normal(size=dim).astype(np.float32)
        q /= np.linalg.norm(q)
        lat = []
        for _ in range(20):
            t0 = time.perf_counter()
            conn.execute(
                "SELECT id, distance FROM v WHERE embedding MATCH ? AND k = ? ORDER BY distance",
                (q.tobytes(), k),
            ).fetchall()
            lat.append((time.perf_counter() - t0) * 1000)
        results.append(
            {
                "n": n,
                "insert_rows_per_sec": round(n / insert_s),
                "knn_p50_ms": pct(lat, 0.5),
                "knn_p95_ms": pct(lat, 0.95),
            }
        )
        print(f"[bench] vec0 n={n:>6} insert={n/insert_s:>9.0f}/s knn_p50={pct(lat,0.5)}ms")
    conn.close()
    try:
        path.unlink()
    except OSError:
        pass
    return results


def main():
    summary, per_query = bench_queries()
    print("\n=== 모드별 지연 (실데이터) ===")
    for m, s in summary.items():
        print(f"  {m:8s} p50={s['p50_ms']:>7.3f}ms p95={s['p95_ms']:>7.3f}ms max={s['max_ms']:>7.3f}ms avg_results={s['avg_results']}")

    print("\n=== 질의별 결과 비교 (상위 4) ===")
    for q, m in list(per_query.items())[:6]:
        print(f"\n  Q: {q}")
        for mode in MODES:
            print(f"    {mode:8s} {' | '.join(m[mode][:4]) or '(없음)'}")

    scale = bench_vector_scale()
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "db": str(config.DB_PATH),
        "latency": summary,
        "per_query": per_query,
        "vector_scale": scale,
    }
    out = Path(config.DATA_DIR) / "bench_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[bench] wrote {out}")


if __name__ == "__main__":
    main()
