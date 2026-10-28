"""한국어 검색을 위한 텍스트 정규화 / n-gram 토크나이저.

SQLite FTS5 의 기본 unicode61 토크나이저는 공백 기준으로만 쪼개기 때문에
"채식주의자" 를 "채식" 으로 검색할 수 없다. 그래서 색인 시점에 한글 토큰을
문자 n-gram 으로 분해해 넣고, 질의도 같은 방식으로 변환한다.
(외부 형태소 분석기 의존성 없이 동작하는 실용적 방법)
"""
from __future__ import annotations

import re
import unicodedata

TOKEN_RE = re.compile(r"[가-힣]+|[a-zA-Z]+|\d+")
HANGUL_RE = re.compile(r"^[가-힣]+$")

# 검색에서 의미 없는 토큰
STOPWORDS = {"의", "을", "를", "이", "가", "은", "는", "와", "과", "도", "에", "로", "으로"}

CHOSUNG = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
_JAMO_ONLY = re.compile(r"^[ㄱ-ㅎ]+$")


def is_chosung_query(text: str) -> bool:
    """자음(초성)만으로 이루어진 질의인가. 예: 'ㅎㄱ', 'ㄱㅊㅇ'."""
    t = re.sub(r"\s+", "", text or "")
    return bool(t) and bool(_JAMO_ONLY.match(t))


def to_chosung(text: str) -> str:
    """'한강' -> 'ㅎㄱ'. 한글 음절은 초성으로, 영숫자는 그대로, 그 외는 버린다."""
    out: list[str] = []
    for ch in str(text or ""):
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            out.append(CHOSUNG[(code - 0xAC00) // 588])
        elif ch.isalnum():
            out.append(ch.lower())
    return "".join(out)


def normalize(text: str) -> str:
    """NFKC + 소문자 + 공백 정리."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", str(text)).lower()
    return re.sub(r"\s+", " ", t).strip()


def _ngrams(token: str) -> list[str]:
    """한글 토큰을 문자 unigram/bigram 으로 분해."""
    if HANGUL_RE.match(token):
        out: list[str] = []
        n = len(token)
        if n == 1:
            if token not in STOPWORDS:
                out.append(token)
            return out
        # bigram (2글자 질의 커버: '한강', '채식')
        for i in range(n - 1):
            out.append(token[i : i + 2])
        # 짧은 토큰은 원형도 함께 (정확도)
        if n <= 5:
            out.append(token)
        return out
    return [token]


def index_terms(text: str) -> list[str]:
    """색인용 term 목록."""
    out: list[str] = []
    for m in TOKEN_RE.finditer(normalize(text)):
        out.extend(_ngrams(m.group()))
    return out


def index_text(*parts: str | None) -> str:
    """FTS5에 넣을 색인 문자열 (공백 구분 term)."""
    terms: list[str] = []
    for p in parts:
        if not p:
            continue
        terms.extend(index_terms(str(p)))
    # 중복 제거하며 순서 유지
    seen = set()
    uniq = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return " ".join(uniq)


def _quote(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


def fts_query(query: str) -> str:
    """사용자 질의 -> FTS5 MATCH 식.

    각 원본 단어 안의 n-gram 은 OR, 단어끼리는 AND.
    예: "김초엽 SF" -> ("김초" OR "초엽" OR "김초엽") AND ("sf")
    """
    groups: list[list[str]] = []
    for m in TOKEN_RE.finditer(normalize(query)):
        toks = _ngrams(m.group())
        if not toks:
            continue
        groups.append(toks)
    if not groups:
        return ""
    parts = []
    for g in groups:
        parts.append("(" + " OR ".join(_quote(t) for t in g) + ")")
    return " AND ".join(parts)


def query_terms(query: str) -> list[str]:
    out: list[str] = []
    for m in TOKEN_RE.finditer(normalize(query)):
        out.extend(_ngrams(m.group()))
    return out


def light_stem(text: str) -> str:
    """매칭용 거친 정규화: 공백/구두점/괄호 제거."""
    t = normalize(text)
    t = re.sub(r"\(.*?\)|\[.*?\]|〈.*?〉|《.*?》", " ", t)
    t = re.sub(r"[^0-9a-z가-힣 ]", " ", t)
    return re.sub(r"\s+", "", t)
