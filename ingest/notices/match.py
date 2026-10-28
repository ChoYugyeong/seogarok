"""제목/저자 정규화 및 카탈로그 퍼지 매칭 유틸.

플랫폼마다 제목 표기가 조금씩 다르다.
  - "소년이 온다 (개정판)"            -> 괄호/판본 제거
  - "구의 증명 - 개정판"               -> 부제 제거
  - "해리 포터와 마법사의 돌: 1권"     -> 부제 제거
  - "채식주의자(한강)"                 -> 괄호 제거
  - "김현학, iamfoodstylist 편집부"    -> 저자 역할어/공동저자 정리
그래서 notice 제목을 정규화한 뒤 카탈로그(data.js 38권)와
시퀀스 유사도 + 토큰 자카드 + 저자 일치 보너스로 퍼지 매칭한다.

이 모듈은 base.py 에 의존하지 않는다(단독 import 가능).
"""

from __future__ import annotations

import dataclasses
import difflib
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# 정규화
# ---------------------------------------------------------------------------

_BRACKET_PAIRS = [
    ("(", ")"),
    ("[", "]"),
    ("{", "}"),
    ("（", "）"),
    ("［", "］"),
    ("｛", "｝"),
    ("【", "】"),
    ("〔", "〕"),
    ("〈", "〉"),
    ("《", "》"),
    ("「", "」"),
    ("『", "』"),
    ("<", ">"),
    ("＜", "＞"),
]

_QUOTES = "“”‘’\"'`´"
_TITLE_SEPARATORS = re.compile(r"\s*(?:-{1,2}|–|—|:|：|\||｜|·{2})\s*")
_EDITION_WORDS = [
    "전면개정판",
    "개정판",
    "개정증보판",
    "증보판",
    "리커버판",
    "리커버",
    "특별판",
    "기념판",
    "합본판",
    "합본",
    "완역판",
    "완역",
    "무삭제판",
    "무삭제",
    "신판",
    "초판",
    "한정판",
    "보급판",
    "양장본",
    "반양장",
    "전자책",
    "오디오북",
    "단행본",
    "세트판",
    "전집",
    "개정",
]
_EDITION_RE = re.compile(
    "|".join(sorted((re.escape(w) for w in _EDITION_WORDS), key=len, reverse=True))
)
_SERIES_SUFFIX_RE = re.compile(r"\s*(?:제?\s*\d+\s*(?:권|화|부|편)|vol\.?\s*\d+)\s*$", re.I)
_AUTHOR_ROLE_RE = re.compile(
    r"\s*(?:지음|지은이|저자|글쓴이|글|그림|옮김|옮긴이|역자|역|편저|엮음|엮은이|편|감수|해설|기획|원작|사진|일러스트|저)\s*$"
)
_AUTHOR_SPLIT_RE = re.compile(r"\s*[,/·;、]\s*")
_ISBN_RE = re.compile(r"^(?:\d{9}[\dXx]|\d{13})$")


def normalize_title(value: str | None) -> str:
    """제목 정규화: NFKC -> 괄호/부제/판본/따옴표/공백 제거 -> 소문자."""
    if not value:
        return ""
    s = unicodedata.normalize("NFKC", str(value))
    s = _strip_brackets(s)
    # 부제 분리자 이후 제거 ("제목 - 부제", "제목: 부제")
    parts = _TITLE_SEPARATORS.split(s)
    if parts and parts[0].strip():
        s = parts[0]
    s = _EDITION_RE.sub(" ", s)
    s = _SERIES_SUFFIX_RE.sub(" ", s)
    s = s.strip().strip(_QUOTES + " .,;")
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def _strip_brackets(text: str) -> str:
    """가장 안쪽 괄호쌍부터 반복 제거. 짝이 없는 괄호는 문자만 제거."""
    result = text
    for open_ch, close_ch in _BRACKET_PAIRS:
        pattern = re.compile(re.escape(open_ch) + r"[^" + re.escape(open_ch + close_ch) + r"]*" + re.escape(close_ch))
        prev = None
        while prev != result:
            prev = result
            result = pattern.sub(" ", result)
        result = result.replace(open_ch, " ").replace(close_ch, " ")
    # 《》 는 제목 인용에 쓰이므로 내용은 유지하고 괄호만 제거
    for ch in "《》〈〉":
        result = result.replace(ch, " ")
    return result


def normalize_author(value: str | None) -> str:
    """저자 정규화: 괄호/역할어 제거, 공동저자는 첫 저자만."""
    if not value:
        return ""
    s = unicodedata.normalize("NFKC", str(value))
    s = _strip_brackets(s)
    candidates = [part.strip() for part in _AUTHOR_SPLIT_RE.split(s) if part.strip()]
    if not candidates:
        return ""
    first = candidates[0]
    prev = None
    while prev != first:
        prev = first
        first = _AUTHOR_ROLE_RE.sub("", first).strip()
    first = first.strip(_QUOTES + " .,;")
    return re.sub(r"\s+", " ", first).strip().lower()


def normalize_isbn(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"[^0-9Xx]", "", str(value))
    return digits.upper() if _ISBN_RE.match(digits.upper()) else None


def title_tokens(normalized_title: str) -> set[str]:
    return {token for token in normalized_title.split() if token}


def title_similarity(a: str | None, b: str | None) -> float:
    """0~1. 시퀀스 유사도와 토큰 자카드의 최댓값."""
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    seq = difflib.SequenceMatcher(None, na, nb).ratio()
    ta, tb = title_tokens(na), title_tokens(nb)
    jaccard = len(ta & tb) / len(ta | tb) if ta | tb else 0.0
    containment = 1.0 if (na in nb or nb in na) else 0.0
    return round(max(seq, jaccard, containment * 0.95), 4)


# ---------------------------------------------------------------------------
# 카탈로그 (data.js 38권, 읽기 전용)
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class CatalogBook:
    id: str
    title: str
    author: str
    publisher: str = ""
    year: int | None = None
    av: dict[str, dict[str, Any]] = dataclasses.field(default_factory=dict)

    @property
    def title_key(self) -> str:
        return normalize_title(self.title)

    @property
    def author_key(self) -> str:
        return normalize_author(self.author)


@dataclasses.dataclass
class CatalogMatch:
    book_id: str
    title: str
    score: float
    title_score: float
    author_score: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _scan_balanced(text: str, start: int, open_ch: str, close_ch: str) -> int:
    """text[start] == open_ch 일 때 짝이 맞는 close_ch 인덱스(포함)를 반환."""
    depth = 0
    quote: str | None = None
    i = start
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError(f"unbalanced {open_ch}{close_ch} from {start}")


def _split_top_level(text: str) -> list[str]:
    """`[...]` 안쪽 문자열을 최상위 콤마로 분리."""
    items: list[str] = []
    depth = 0
    quote: str | None = None
    start = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        else:
            if ch in "'\"":
                quote = ch
            elif ch in "[{(":
                depth += 1
            elif ch in "]})":
                depth -= 1
            elif ch == "," and depth == 0:
                items.append(text[start:i])
                start = i + 1
        i += 1
    tail = text[start:]
    if tail.strip():
        items.append(tail)
    return items


def _js_field(obj_src: str, name: str) -> str | None:
    match = re.search(rf"\b{name}\s*:\s*(['\"])(.*?)\1", obj_src, re.S)
    return match.group(2) if match else None


def _parse_av(obj_src: str) -> dict[str, dict[str, Any]]:
    match = re.search(r"\bav\s*:\s*\{", obj_src)
    if not match:
        return {}
    start = match.end() - 1
    end = _scan_balanced(obj_src, start, "{", "}")
    av_src = obj_src[start + 1 : end]
    result: dict[str, dict[str, Any]] = {}
    for chunk in _split_top_level(av_src):
        kv = re.match(r"\s*['\"]?([A-Za-z0-9_]+)['\"]?\s*:\s*\{(.*)\}\s*$", chunk, re.S)
        if not kv:
            continue
        platform, body = kv.group(1), kv.group(2)
        entry: dict[str, Any] = {}
        status = re.search(r"\bs\s*:\s*['\"](\w+)['\"]", body)
        if status:
            entry["s"] = status.group(1)
        days = re.search(r"\bd\s*:\s*(\d+)", body)
        if days:
            entry["d"] = int(days.group(1))
        for key in ("buy", "wait"):
            price = re.search(rf"\b{key}\s*:\s*(\d+)", body)
            if price:
                entry[key] = int(price.group(1))
        if entry:
            result[platform] = entry
    return result


def load_data_js_catalog(path: str | Path) -> list[CatalogBook]:
    """`data.js`(프론트 프로토타입, 읽기 전용)에서 BOOKS 배열을 파싱한다."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    match = re.search(r"const\s+BOOKS\s*=\s*\[", text)
    if not match:
        raise ValueError("data.js 에서 const BOOKS = [ 를 찾지 못했습니다")
    array_start = match.end() - 1
    array_end = _scan_balanced(text, array_start, "[", "]")
    body = text[array_start + 1 : array_end]
    books: list[CatalogBook] = []
    for chunk in _split_top_level(body):
        chunk = chunk.strip()
        if not chunk.startswith("{"):
            continue
        book_id = _js_field(chunk, "id")
        title = _js_field(chunk, "title")
        author = _js_field(chunk, "author")
        if not book_id or not title:
            continue
        year_raw = re.search(r"\byear\s*:\s*(\d+)", chunk)
        books.append(
            CatalogBook(
                id=book_id,
                title=title,
                author=author or "",
                publisher=_js_field(chunk, "publisher") or "",
                year=int(year_raw.group(1)) if year_raw else None,
                av=_parse_av(chunk),
            )
        )
    return books


# ---------------------------------------------------------------------------
# 매칭
# ---------------------------------------------------------------------------


def match_book(
    title: str,
    author: str | None,
    catalog: Iterable[CatalogBook],
    *,
    isbn13: str | None = None,
    threshold: float = 0.78,
) -> CatalogMatch | None:
    """공지 1건을 카탈로그에서 가장 유사한 책으로 매칭. 임계 미만이면 None."""
    norm_title = normalize_title(title)
    norm_author = normalize_author(author)
    if not norm_title:
        return None
    best: CatalogMatch | None = None
    for book in catalog:
        title_score = title_similarity(title, book.title)
        if isbn13 and normalize_isbn(isbn13):
            # 카탈로그에 isbn 필드가 없으므로 제목 매칭으로만 판단(향후 확장 지점)
            pass
        same_author = bool(norm_author and norm_author == book.author_key)
        if norm_author and book.author_key:
            author_score = 1.0 if same_author else 0.0
        else:
            author_score = 0.5  # 저자 미상: 중립
        bonus = 0.12 if same_author else 0.0
        score = round(min(1.0, title_score * 0.9 + bonus), 4)
        if best is None or score > best.score:
            reason = "제목+저자 일치" if same_author else "제목 유사"
            best = CatalogMatch(
                book_id=book.id,
                title=book.title,
                score=score,
                title_score=title_score,
                author_score=author_score,
                reason=reason,
            )
    if best is None or best.score < threshold:
        return None
    return best


def match_many(
    rows: Iterable[dict[str, Any]],
    catalog: Iterable[CatalogBook],
    *,
    threshold: float = 0.78,
) -> list[dict[str, Any]]:
    """[{title, author, ...}, ...] 각각에 대해 매칭 결과를 붙여 반환."""
    catalog = list(catalog)
    out: list[dict[str, Any]] = []
    for row in rows:
        match = match_book(row.get("title", ""), row.get("author"), catalog, threshold=threshold)
        enriched = dict(row)
        enriched["match"] = match.as_dict() if match else None
        out.append(enriched)
    return out


def match_stats(matched: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(matched)
    hit = sum(1 for row in matched if row.get("match"))
    return {
        "total": total,
        "matched": hit,
        "unmatched": total - hit,
        "match_rate": round(hit / total, 4) if total else 0.0,
    }
