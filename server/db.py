"""SQLite 스키마 + 벡터 스토어 + 동기화.

구성
  books          : 카탈로그 (알라딘 수집분 + 데모 큐레이션)
  books_fts      : FTS5 (한글 n-gram term 색인) — BM25 렉시컬 검색
  vec_books      : sqlite-vec vec0 가상 테이블 — 벡터 ANN 검색 (없으면 numpy 폴백)
  notices        : 플랫폼 종료 예정 공지 (정규화)
  availability   : 책 × 플랫폼 제공 상태 (실수집 + 시뮬레이션 구분)
  meta           : 인덱스 메타데이터
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from . import config
from .kotext import index_text, light_stem, to_chosung

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS books (
  id           TEXT PRIMARY KEY,
  source       TEXT NOT NULL,
  title        TEXT NOT NULL,
  subtitle     TEXT,
  author       TEXT,
  publisher    TEXT,
  pubdate      TEXT,
  isbn13       TEXT,
  item_code    TEXT,
  price        INTEGER,
  price_list   INTEGER,
  rating       REAL,
  cover_url    TEXT,
  link         TEXT,
  category     TEXT,
  description  TEXT,
  search_terms TEXT,
  chosung      TEXT,
  chosung_author TEXT,
  collected_at TEXT
);

CREATE TABLE IF NOT EXISTS notices (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  platform     TEXT NOT NULL,
  title        TEXT NOT NULL,
  author       TEXT,
  book_id      TEXT,
  ends_at      TEXT,
  status       TEXT,
  source_url   TEXT,
  source_kind  TEXT,
  collected_at TEXT,
  raw_note     TEXT,
  UNIQUE(platform, title, ends_at)
);
CREATE INDEX IF NOT EXISTS idx_notices_book ON notices(book_id);

CREATE TABLE IF NOT EXISTS availability (
  book_id     TEXT NOT NULL,
  platform    TEXT NOT NULL,
  status      TEXT NOT NULL,          -- on | ending | none
  ends_at     TEXT,
  origin      TEXT NOT NULL,          -- notice | simulated
  confidence  TEXT,
  updated_at  TEXT,
  PRIMARY KEY (book_id, platform)
);

CREATE TABLE IF NOT EXISTS reports (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id    TEXT NOT NULL,
  platform   TEXT NOT NULL,
  note       TEXT,
  ua         TEXT,
  ip_hash    TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_book ON reports(book_id, platform);

CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);

CREATE VIRTUAL TABLE IF NOT EXISTS books_fts USING fts5(
  book_id UNINDEXED,
  terms,
  tokenize='unicode61 remove_diacritics 2'
);
"""

SUB_PLATFORMS = ["millie", "ridiselect", "sam", "willa"]


class SeogaConnection(sqlite3.Connection):
    """sqlite3.Connection 은 임의 속성을 못 붙이므로 서브클래스로 플래그를 보관한다."""

    vec_loaded: bool = False


def connect(path: Path | str | None = None, readonly: bool = False) -> sqlite3.Connection:
    p = Path(path or config.DB_PATH)
    if readonly:
        conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True, check_same_thread=False, factory=SeogaConnection)
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(p), check_same_thread=False, factory=SeogaConnection)
    conn.row_factory = sqlite3.Row
    if not readonly:
        conn.executescript(SCHEMA)
    try:
        import sqlite_vec

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        conn.vec_loaded = True
    except Exception:
        conn.vec_loaded = False
    return conn


# --------------------------------------------------------------------------
# 벡터 스토어
# --------------------------------------------------------------------------
class VectorStore:
    """sqlite-vec vec0 가 있으면 사용하고, 없으면 numpy brute-force 로 폴백."""

    def __init__(self, conn: sqlite3.Connection, dim: int):
        self.conn = conn
        self.dim = dim
        self.backend = "sqlite-vec" if getattr(conn, "vec_loaded", False) else "numpy"
        self._ids: list[str] | None = None
        self._mat: np.ndarray | None = None
        if self.backend == "sqlite-vec":
            conn.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_books USING vec0(book_id text primary key, embedding float[{dim}])"
            )
        else:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS book_vectors (book_id TEXT PRIMARY KEY, dim INTEGER, vec BLOB)"
            )
        conn.commit()

    # -- write -------------------------------------------------------------
    def reset(self) -> None:
        if self.backend == "sqlite-vec":
            self.conn.execute("DELETE FROM vec_books")
        else:
            self.conn.execute("DELETE FROM book_vectors")
        self.conn.commit()
        self._ids, self._mat = None, None

    def upsert(self, ids: Sequence[str], mat: np.ndarray) -> None:
        mat = np.asarray(mat, dtype=np.float32)
        if self.backend == "sqlite-vec":
            self.conn.executemany(
                "INSERT OR REPLACE INTO vec_books(book_id, embedding) VALUES (?, ?)",
                [(i, mat[n].tobytes()) for n, i in enumerate(ids)],
            )
        else:
            self.conn.executemany(
                "INSERT OR REPLACE INTO book_vectors(book_id, dim, vec) VALUES (?, ?, ?)",
                [(i, self.dim, mat[n].tobytes()) for n, i in enumerate(ids)],
            )
        self.conn.commit()
        self._ids, self._mat = None, None

    # -- read --------------------------------------------------------------
    def _load_numpy(self) -> tuple[list[str], np.ndarray]:
        if self._ids is None or self._mat is None:
            rows = self.conn.execute("SELECT book_id, vec FROM book_vectors").fetchall()
            self._ids = [r["book_id"] for r in rows]
            if rows:
                self._mat = np.vstack([np.frombuffer(r["vec"], dtype=np.float32) for r in rows])
            else:
                self._mat = np.zeros((0, self.dim), dtype=np.float32)
        return self._ids, self._mat

    def get(self, book_id: str) -> np.ndarray | None:
        """책 하나의 임베딩 벡터를 반환 (없으면 None)."""
        if self.backend == "sqlite-vec":
            row = self.conn.execute(
                "SELECT embedding FROM vec_books WHERE book_id = ?", (book_id,)
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT vec FROM book_vectors WHERE book_id = ?", (book_id,)
            ).fetchone()
        if not row:
            return None
        try:
            return np.frombuffer(row[0], dtype=np.float32).copy()
        except Exception:
            return None

    def search(self, qvec: np.ndarray, k: int = 50) -> list[tuple[str, float]]:
        """(book_id, cosine similarity) 내림차순."""
        q = np.asarray(qvec, dtype=np.float32).reshape(-1)
        if self.backend == "sqlite-vec":
            try:
                rows = self.conn.execute(
                    "SELECT book_id, distance FROM vec_books WHERE embedding MATCH ? AND k = ? ORDER BY distance",
                    (q.tobytes(), k),
                ).fetchall()
                # vec0 기본 거리 = L2. 정규화 벡터이므로 ||u-v||^2 = 2(1-cos)
                #   => cos = 1 - d^2 / 2
                return [(r["book_id"], 1.0 - (float(r["distance"]) ** 2) / 2.0) for r in rows]
            except sqlite3.Error:
                self.backend = "numpy"
        ids, mat = self._load_numpy()
        if not ids:
            return []
        sims = mat @ q
        idx = np.argpartition(-sims, min(k, len(sims) - 1))[:k]
        idx = idx[np.argsort(-sims[idx])]
        return [(ids[i], float(sims[i])) for i in idx]

    def count(self) -> int:
        if self.backend == "sqlite-vec":
            try:
                return int(self.conn.execute("SELECT count(*) FROM vec_books").fetchone()[0])
            except sqlite3.Error:
                pass
        return int(self.conn.execute("SELECT count(*) FROM book_vectors").fetchone()[0])


# --------------------------------------------------------------------------
# 카탈로그 동기화
# --------------------------------------------------------------------------
def load_catalog_rows(path: Path | None = None) -> list[dict]:
    p = Path(path or config.CATALOG_PATH)
    if not p.exists():
        return []
    rows = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _author_core(author) -> str:
    """'한강 저/홍은주 역' -> '한강' (역할어 제거, 첫 저자)."""
    first = str(author or "").split("/")[0]
    for w in ("저자", "지음", "엮음", "옮김", "그림", "감수", "편저", "원저", "저", "역", "글", "편"):
        first = first.replace(w, " ")
    return " ".join(first.split())
def _clean(v):
    if v in ("", "null", "None"):
        return None
    return v


def sync_catalog(conn: sqlite3.Connection, embedder, rows: Iterable[dict], batch: int = 128) -> dict:
    """카탈로그 JSONL -> books + FTS + 벡터."""
    store = VectorStore(conn, embedder.dim)
    store.reset()
    # 구버전 DB 대비 chosung 컬럼/인덱스 보장
    cols = {r[1] for r in conn.execute("PRAGMA table_info(books)").fetchall()}
    if "chosung" not in cols:
        conn.execute("ALTER TABLE books ADD COLUMN chosung TEXT")
    if "chosung_author" not in cols:
        conn.execute("ALTER TABLE books ADD COLUMN chosung_author TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_books_chosung ON books(chosung)")
    conn.execute("DELETE FROM books")
    conn.execute("DELETE FROM books_fts")
    conn.commit()

    t0 = time.time()
    n = 0
    buf_books: list[dict] = []
    buf_texts: list[str] = []
    buf_ids: list[str] = []
    vec_total = 0

    def flush():
        nonlocal vec_total
        if not buf_ids:
            return
        conn.executemany(
            """INSERT OR REPLACE INTO books
               (id, source, title, subtitle, author, publisher, pubdate, isbn13, item_code,
                price, price_list, rating, cover_url, link, category, description, search_terms, chosung, chosung_author, collected_at)
               VALUES (:id,:source,:title,:subtitle,:author,:publisher,:pubdate,:isbn13,:item_code,
                       :price,:price_list,:rating,:cover_url,:link,:category,:description,:search_terms,:chosung,:chosung_author,:collected_at)""",
            buf_books,
        )
        conn.executemany(
            "INSERT INTO books_fts(book_id, terms) VALUES (?, ?)",
            [(b["id"], b["search_terms"]) for b in buf_books],
        )
        mat = embedder.encode(buf_texts)
        store.upsert(buf_ids, mat)
        vec_total += len(buf_ids)
        buf_books.clear()
        buf_texts.clear()
        buf_ids.clear()

    for row in rows:
        bid = _clean(row.get("id"))
        title = _clean(row.get("title"))
        if not bid or not title:
            continue
        # FTS(렉시컬) 색인은 제목/저자/출판사/카테고리만.
        # 설명문까지 bigram 색인하면 '주의', '의자' 같은 흔한 bigram 이
        # 무관한 책을 끌어와 정확도를 망친다. 설명은 벡터 쪽이 담당한다.
        terms = index_text(title, row.get("subtitle"), row.get("author"), row.get("category"))
        buf_books.append(
            {
                "id": bid,
                "source": _clean(row.get("source")) or "unknown",
                "title": title,
                "subtitle": _clean(row.get("subtitle")),
                "author": _clean(row.get("author")),
                "publisher": _clean(row.get("publisher")),
                "pubdate": _clean(row.get("pubdate")),
                "isbn13": _clean(row.get("isbn13")),
                "item_code": _clean(row.get("item_code")),
                "price": row.get("price"),
                "price_list": row.get("price_list"),
                "rating": row.get("rating"),
                "cover_url": _clean(row.get("cover_url")),
                "link": _clean(row.get("link")),
                "category": _clean(row.get("category")),
                "description": _clean(row.get("description")),
                "search_terms": terms,
                "chosung": to_chosung(row.get("title") or ""),
                "chosung_author": to_chosung(_author_core(row.get("author"))),
                "collected_at": _clean(row.get("collected_at")),
            }
        )
        buf_texts.append(
            " ".join(
                x
                for x in [
                    title,
                    row.get("subtitle") or "",
                    row.get("author") or "",
                    row.get("publisher") or "",
                    (row.get("category") or "").replace(">", " "),
                    (row.get("description") or "")[:600],
                ]
                if x
            )
        )
        buf_ids.append(bid)
        n += 1
        if n % batch == 0:
            flush()
    flush()

    conn.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('book_count',?)", (str(n),))
    conn.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('embed_backend',?)", (embedder.name,))
    conn.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('embed_dim',?)", (str(embedder.dim),))
    conn.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('vec_backend',?)", (store.backend,))
    conn.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('synced_at',?)", (time.strftime("%Y-%m-%dT%H:%M:%S%z"),))
    conn.commit()
    try:
        from .collections import sync_collections

        cstats = sync_collections(conn)
        print(f"[sync] collections={cstats['collections']} matched={cstats['matched']}")
    except Exception as exc:
        print(f"[sync] collections skip: {exc}")
    return {
        "books": n,
        "vectors": vec_total,
        "vector_backend": store.backend,
        "embed_backend": embedder.name,
        "embed_dim": embedder.dim,
        "seconds": round(time.time() - t0, 2),
    }


# --------------------------------------------------------------------------
# 공지 동기화 (수집 파이프라인 산출물 -> notices + availability)
# --------------------------------------------------------------------------
def load_notice_rows(path: Path | None = None) -> list[dict]:
    p = Path(path or config.NOTICES_PATH)
    if not p.exists():
        return []
    out = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def sync_notices(conn: sqlite3.Connection, rows: Sequence[dict]) -> dict:
    """공지를 DB에 넣고, 제목 기준으로 카탈로그 책과 매칭한다."""
    books = conn.execute("SELECT id, title, author FROM books").fetchall()
    by_title: dict[str, str] = {}
    for b in books:
        key = light_stem(b["title"])
        if key:
            by_title.setdefault(key, b["id"])

    matched = 0
    inserted = 0
    # 공지는 파이프라인 산출물의 "스냅샷"이므로 통째로 교체한다.
    # (ends_at 이 NULL 인 행은 SQLite UNIQUE 제약이 중복으로 보지 않아 누적되기 때문)
    conn.execute("DELETE FROM notices")
    for r in rows:
        platform = str(r.get("platform") or "").strip()
        title = str(r.get("title") or "").strip()
        if not platform or not title:
            continue
        book_id = by_title.get(light_stem(title))
        if book_id:
            matched += 1
        conn.execute(
            """INSERT OR REPLACE INTO notices
               (platform,title,author,book_id,ends_at,status,source_url,source_kind,collected_at,raw_note)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                platform,
                title,
                r.get("author"),
                book_id,
                r.get("ends_at"),
                r.get("status") or "ending",
                r.get("source_url"),
                r.get("source_kind"),
                r.get("collected_at"),
                r.get("raw_note"),
            ),
        )
        inserted += 1

    # 실제 공지 -> availability 반영 (notice origin)
    conn.execute("DELETE FROM availability WHERE origin='notice'")
    rows2 = conn.execute(
        "SELECT book_id, platform, ends_at FROM notices "
        "WHERE book_id IS NOT NULL AND status='ending' "
        "AND (source_kind IS NULL OR source_kind != 'fixture')"
    ).fetchall()
    for r in rows2:
        conn.execute(
            """INSERT OR REPLACE INTO availability(book_id,platform,status,ends_at,origin,confidence,updated_at)
               VALUES (?,?,?,?, 'notice', 'high', ?)""",
            (r["book_id"], r["platform"], "ending", r["ends_at"], time.strftime("%Y-%m-%d")),
        )
    conn.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('notice_count',?)", (str(inserted),))
    conn.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('notice_matched',?)", (str(matched),))
    conn.commit()
    return {"notices": inserted, "matched_to_catalog": matched}


def meta(conn: sqlite3.Connection) -> dict:
    try:
        return {r["k"]: r["v"] for r in conn.execute("SELECT k,v FROM meta")}
    except sqlite3.Error:
        return {}
