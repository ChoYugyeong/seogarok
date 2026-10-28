"""공개 추천 목록(큐레이션 컬렉션).

- 서울대학교 중앙도서관 '서울대 학생을 위한 권장도서 100선' (공식 공개 목록, 제목·저자만 사용)
- The Harvard Classics (1909, 퍼블릭 도메인) 대표작

목록 자체(제목·저자)는 사실 정보이며, 해설·평가 문구는 사용하지 않는다.
카탈로그에 수록된 책과 제목/저자 기반으로 매칭해 보여준다.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from . import config

PATH = Path(getattr(config, "DATA_DIR", Path("data"))) / "collections.jsonl"


def load_collections() -> list[dict]:
    if not PATH.exists():
        return []
    out: list[dict] = []
    for line in PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _norm(s) -> str:
    s = unicodedata.normalize("NFKC", str(s or "")).lower()
    return re.sub(r"[\s\-_:,·()\[\]{}<>\"'’“”/]", "", s)


_SUFFIX = ["개정판", "개정신판", "신판", "전집", "선집", "완역판", "합본", "세트", "특별판", "양장", "ebook"]


def _norm_title(t) -> str:
    t = _norm(t)
    for suf in _SUFFIX:
        t = t.replace(_norm(suf), "")
    t = re.sub(r"(vol\.?\d+|\d+권|\d+)$", "", t)
    return t


def _author_key(a) -> str:
    a = _norm(a)
    return re.sub(r"(저자|지음|옮김|감수|원저|저|역|글|그림|편)$", "", a)


def match_items(conn, items: list[dict]) -> list[dict]:
    """컬렉션 항목 → 카탈로그 책 매칭 (제목 우선, 저자 보정)."""
    books = conn.execute("SELECT id, title, author FROM books").fetchall()
    if not books:
        return []
    prepared = [(_norm_title(b["title"]), _author_key(b["author"] or ""), b["id"], b["title"]) for b in books]
    out: list[dict] = []
    for item in items:
        t = _norm_title(item.get("title"))
        a = _author_key(item.get("author") or "")
        if not t:
            continue
        best = None
        best_score = 0.0
        for bt, ba, bid, btitle in prepared:
            if not bt:
                continue
            author_ok = bool(a and ba and (a == ba or ba.startswith(a) or a in ba))
            score = 0.0
            if bt == t:
                score = 100.0            # 제목 완전 일치 (부제 유무와 무관)
            elif bt.startswith(t):
                score = 90.0 - min(len(bt) - len(t), 20) * 0.25
            elif t.startswith(bt):
                score = 86.0 - min(len(t) - len(bt), 20) * 0.25
            elif len(t) >= 5 and t in bt:
                # '고전시가'처럼 짧은 토큰이 다른 제목에 우연히 포함되는 오탐 방지
                score = 78.0 - min(len(bt) - len(t), 20) * 0.3
            elif len(t) >= 2 and author_ok and t in bt:
                # '국가' → '플라톤 국가'처럼 짧은 제목이지만 저자가 일치하면 허용
                score = 74.0
            if score <= 0:
                continue
            if a and ba:
                if author_ok:
                    score += 8.0
                elif len(t) <= 4 and score < 100:
                    # 짧은 제목은 저자 확인 필수 (단, 제목 완전 일치는 예외)
                    continue
                else:
                    score -= 6.0
            if score > best_score:
                best_score, best = score, bid
        if best and best_score >= 70:
            out.append({
                "book_id": best,
                "item_title": item.get("title"),
                "item_author": item.get("author"),
                "category": item.get("category"),
                "score": round(best_score, 1),
            })
    # 중복 책 제거 (한 책이 두 항목에 매칭되는 경우 첫 항목만)
    seen: set[str] = set()
    uniq: list[dict] = []
    for m in out:
        if m["book_id"] in seen:
            continue
        seen.add(m["book_id"])
        uniq.append(m)
    return uniq


def sync_collections(conn) -> dict:
    """컬렉션 테이블 재생성 + 매칭 저장. sync_catalog 끝에서 호출."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS collections (
          slug TEXT PRIMARY KEY,
          title TEXT, subtitle TEXT, source TEXT, source_url TEXT,
          license_note TEXT, kind TEXT, ord INTEGER, total INTEGER
        );
        CREATE TABLE IF NOT EXISTS collection_items (
          slug TEXT NOT NULL, book_id TEXT, item_title TEXT, item_author TEXT,
          category TEXT, score REAL, ord INTEGER
        );
        DELETE FROM collections;
        DELETE FROM collection_items;
        """
    )
    # 구버전 스키마 마이그레이션
    cols = {r[1] for r in conn.execute("PRAGMA table_info(collections)").fetchall()}
    if "total" not in cols:
        conn.execute("ALTER TABLE collections ADD COLUMN total INTEGER")
    total_matched = 0
    for ord_, c in enumerate(load_collections()):
        conn.execute(
            "INSERT OR REPLACE INTO collections(slug,title,subtitle,source,source_url,license_note,kind,ord,total) VALUES (?,?,?,?,?,?,?,?,?)",
            (c.get("slug"), c.get("title"), c.get("subtitle"), c.get("source"),
             c.get("source_url"), c.get("license_note"), c.get("kind"), ord_, len(c.get("items") or [])),
        )
        matched = match_items(conn, c.get("items") or [])
        conn.executemany(
            "INSERT INTO collection_items(slug,book_id,item_title,item_author,category,score,ord) VALUES (?,?,?,?,?,?,?)",
            [(c["slug"], m["book_id"], m["item_title"], m["item_author"], m["category"], m["score"], i)
             for i, m in enumerate(matched)],
        )
        total_matched += len(matched)
    conn.commit()
    return {"collections": len(load_collections()), "matched": total_matched}
