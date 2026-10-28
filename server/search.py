"""하이브리드 검색: BM25(FTS5) + 벡터(sqlite-vec) + RRF 융합."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .kotext import fts_query

RRF_K = 60


@dataclass
class SearchDebug:
    keyword_ms: float = 0.0
    vector_ms: float = 0.0
    fuse_ms: float = 0.0
    keyword_candidates: int = 0
    vector_candidates: int = 0
    keyword_query: str = ""
    mode: str = "hybrid"
    extra: dict = field(default_factory=dict)


def keyword_search(conn, query: str, limit: int = 80) -> list[str]:
    fq = fts_query(query)
    if not fq:
        return []
    try:
        rows = conn.execute(
            "SELECT book_id FROM books_fts WHERE books_fts MATCH ? ORDER BY bm25(books_fts) LIMIT ?",
            (fq, limit),
        ).fetchall()
    except Exception:
        return []
    return [r["book_id"] for r in rows]


def vector_search(store, embedder, query: str, limit: int = 80) -> list[tuple[str, float]]:
    qv = embedder.encode_one(query)
    hits = store.search(qv, k=limit)
    if not hits:
        return []
    # 관련도 컷: 정적 임베딩은 코사인 값이 압축돼 있어 절대 임계값만으로는 부족하다.
    # 최고 유사도 대비 상대 컷오프를 함께 적용해 무관한 꼬리를 잘라낸다.
    best = hits[0][1]
    floor = max(0.18, best * 0.72)
    return [h for h in hits if h[1] >= floor]


def rrf(*ranked_lists: list, k: int = RRF_K) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion. 입력은 순위가 매겨진 id 리스트(또는 (id,score) 리스트)."""
    scores: dict[str, float] = {}
    for lst in ranked_lists:
        for rank, item in enumerate(lst):
            bid = item[0] if isinstance(item, (tuple, list)) else item
            scores[bid] = scores.get(bid, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: -kv[1])


def field_boost(conn, candidates: list[tuple[str, float]], query: str) -> list[tuple[str, float]]:
    """제목/저자 정확 일치 부스트.

    RRF 는 순위만 보기 때문에 "한강" 같은 저자 질의에서 벡터 노이즈가
    정확 일치를 이길 수 있다. 실서비스 검색엔진의 field boost 를 흉내내
    제목/저자 일치에 가중치를 준다.
    """
    from .kotext import light_stem, normalize

    if not candidates:
        return []
    ids = [c[0] for c in candidates]
    qs = ",".join("?" * len(ids))
    rows = conn.execute(f"SELECT id, title, author FROM books WHERE id IN ({qs})", ids).fetchall()
    fields = {r["id"]: (r["title"] or "", r["author"] or "") for r in rows}

    q = normalize(query)
    q_stem = light_stem(query)
    out = []
    for bid, score in candidates:
        title, author = fields.get(bid, ("", ""))
        t_stem = light_stem(title)
        boost = 0.0
        if q_stem and t_stem:
            if t_stem == q_stem:
                boost += 1.0
            elif q_stem in t_stem:
                boost += 0.45
            elif t_stem in q_stem:
                boost += 0.2
        a = normalize(author)
        if q and a:
            if q == a or (q in a and len(q) >= 2):
                boost += 0.9
        out.append((bid, score + boost * 0.09))
    return sorted(out, key=lambda kv: -kv[1])


def exact_match_first(conn, kw_ids: list[str], query: str, top: int = 5) -> bool:
    """질의가 제목/저자와 정확히 일치하는 책이 있는지.

    있으면 벡터 노이즈를 섞지 않고 렉시컬 결과를 그대로 쓰는 게 정확도에 좋다.
    (사용자가 정확한 제목을 쳤을 때 무관한 의미유사 책이 끼어드는 것을 방지)
    """
    from .kotext import light_stem, normalize

    if not kw_ids:
        return False
    ids = kw_ids[:top]
    qs = ",".join("?" * len(ids))
    rows = conn.execute(f"SELECT title, author FROM books WHERE id IN ({qs})", ids).fetchall()
    q = normalize(query)
    q_stem = light_stem(query)
    for r in rows:
        if q_stem and light_stem(r["title"] or "") == q_stem:
            return True
        a = normalize(r["author"] or "")
        if q and a and (q == a or q in a.split("^")[0]):
            return True
    return False


def chosung_search(conn, query: str, limit: int = 24) -> list[str]:
    """자음 질의('ㅎㄱ') → 초성 LIKE 매칭.

    랭킹: 제목 접두 > 제목 포함 > 저자 접두 > 저자 포함, 같은 순위면 제목이 짧은 순.
    (예: 'ㅎㄱ' → '한강' 작가 책, '한강'으로 시작하는 책이 먼저)
    """
    from .kotext import to_chosung

    q = to_chosung(query)
    if not q:
        return []
    rows = conn.execute(
        "SELECT id, title, chosung, chosung_author FROM books "
        "WHERE chosung LIKE ? OR chosung_author LIKE ?",
        (f"%{q}%", f"%{q}%"),
    ).fetchall()

    def rank(r) -> tuple:
        title_c = r["chosung"] or ""
        author_c = r["chosung_author"] or ""
        if author_c == q:
            tier = -2          # 초성이 정확히 일치하는 작가 (한강)
        elif title_c == q:
            tier = -1          # 초성이 정확히 일치하는 책 (채식주의자)
        elif title_c.startswith(q):
            tier = 0
        elif q in title_c:
            tier = 1
        elif author_c.startswith(q):
            tier = 2
        elif q in author_c:
            tier = 3
        else:
            tier = 4
        return (tier, len(r["title"] or ""), r["title"] or "")

    rows.sort(key=rank)
    return [r["id"] for r in rows[:limit]]


def search(conn, store, embedder, query: str, mode: str = "hybrid", limit: int = 24) -> tuple[list[str], SearchDebug]:
    dbg = SearchDebug(mode=mode)
    query = (query or "").strip()
    if not query:
        return [], dbg

    # ① 초성 검색 (ㅎㄱ → 한강): 자음만 입력한 경우
    from .kotext import is_chosung_query

    if is_chosung_query(query):
        ids = chosung_search(conn, query, limit=limit)
        dbg.extra["strategy"] = "chosung"
        dbg.keyword_candidates = len(ids)
        dbg.keyword_ms = 0.0
        return ids, dbg

    kw_ids: list[str] = []
    vec_hits: list[tuple[str, float]] = []

    if mode in ("hybrid", "keyword"):
        t = time.perf_counter()
        kw_ids = keyword_search(conn, query, limit=limit * 4)
        dbg.keyword_ms = round((time.perf_counter() - t) * 1000, 2)
        dbg.keyword_candidates = len(kw_ids)
        dbg.keyword_query = fts_query(query)

    # 정확 일치가 있으면 하이브리드에서도 벡터를 섞지 않는다.
    exact = mode == "hybrid" and exact_match_first(conn, kw_ids, query)
    dbg.extra["strategy"] = "exact-first" if exact else ("vector-only" if not kw_ids else "rrf")

    if mode == "vector" or (mode == "hybrid" and not exact):
        t = time.perf_counter()
        vec_hits = vector_search(store, embedder, query, limit=limit * 4)
        dbg.vector_ms = round((time.perf_counter() - t) * 1000, 2)
        dbg.vector_candidates = len(vec_hits)

    t = time.perf_counter()
    if mode == "keyword" or exact:
        fused = [(i, 1.0 / (rank + 1)) for rank, i in enumerate(kw_ids)]
    elif mode == "vector":
        fused = vec_hits
    else:
        fused = rrf(kw_ids, vec_hits)
    dbg.fuse_ms = round((time.perf_counter() - t) * 1000, 2)

    t = time.perf_counter()
    fused = field_boost(conn, fused, query)
    dbg.extra["boost_ms"] = round((time.perf_counter() - t) * 1000, 2)

    ids = [i for i, _ in fused[:limit]]
    dbg.extra["scores"] = {i: round(s, 5) for i, s in fused[:limit]}
    dbg.extra["keyword_ids"] = kw_ids[:limit]
    dbg.extra["vector_ids"] = [i for i, _ in vec_hits[:limit]]
    dbg.extra["vector_sims"] = {i: round(s, 4) for i, s in vec_hits[:limit]}
    return ids, dbg


def rrf_k_rank(rank: int) -> int:
    return rank + 1


def fetch_books(conn, ids: list[str]) -> list[dict]:
    if not ids:
        return []
    qs = ",".join("?" * len(ids))
    rows = conn.execute(f"SELECT * FROM books WHERE id IN ({qs})", ids).fetchall()
    by_id = {r["id"]: dict(r) for r in rows}
    return [by_id[i] for i in ids if i in by_id]


def fetch_availability(conn, book_ids: list[str]) -> dict[str, list[dict]]:
    if not book_ids:
        return {}
    qs = ",".join("?" * len(book_ids))
    rows = conn.execute(
        f"SELECT * FROM availability WHERE book_id IN ({qs})", book_ids
    ).fetchall()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["book_id"], []).append(dict(r))
    return out


def fetch_notices(conn, book_ids: list[str]) -> dict[str, list[dict]]:
    if not book_ids:
        return {}
    qs = ",".join("?" * len(book_ids))
    rows = conn.execute(
        f"SELECT * FROM notices WHERE book_id IN ({qs}) ORDER BY ends_at", book_ids
    ).fetchall()
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["book_id"], []).append(dict(r))
    return out
