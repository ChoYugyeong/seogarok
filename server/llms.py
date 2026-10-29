"""에이전트/AI 검색용 발견 파일: llms.txt · llms-full.txt · Markdown 버전.

구조는 llmstxt.org 권장(H1 → 인용 요약 → H2 섹션의 [링크](URL) 목록)을 따른다.
"""
from __future__ import annotations

import html
import time

BASE = "https://seogarok.com"
SUB_LABEL = {"millie": "밀리", "ridiselect": "리디셀렉트", "sam": "교보 sam", "willa": "윌라"}


def esc(v) -> str:
    return html.escape(str(v if v is not None else ""), quote=True)


def llms_txt(books: int = 0, notices: int = 0) -> str:
    today = time.strftime("%Y-%m-%d")
    count_line = f"- 색인 {books:,}권 · 종료 공지 {notices:,}건 ({today} 기준)" if books else f"- {today} 기준"
    return f"""# 서가록 (SEOGAROK)

> 밀리·리디셀렉트·교보 sam·윌라 구독 가용성과 종료 예정일을 한 번에 확인하는 한국어 책 검색 서비스. 예스24 실시간 랭킹(베스트·스테디·일간·월간)과 공개 추천 목록을 함께 제공한다.

서가록은 "이 책, 지금 어디서 읽을 수 있고 언제 사라지는가"를 한 화면에서 답한다.
확인되지 않은 가용성은 추정하지 않고 “미확인”으로 표시한다.

## 주요 페이지

- [홈]({BASE}/): 검색·오늘의 책·서가 랭킹·종료 타임라인
- [책 목록]({BASE}/books?page=1): 색인된 책 전체를 페이지 단위로 탐색
- [서비스 소개]({BASE}/about.html): 작동 방식·데이터 출처·FAQ
- [이용약관·개인정보]({BASE}/legal.html)

## 추천 목록

- [서울대 권장도서 100선]({BASE}/?col=snu-100)
- [하버드 클래식]({BASE}/?col=harvard-classics)
- [세종도서 2025 교양 부문]({BASE}/?col=sejong-2025-culture)
- [세종도서 2025 학술 부문]({BASE}/?col=sejong-2025-academic)

## 실시간 랭킹

- [예스24 베스트셀러와 서가 가용성 교차]({BASE}/): 종합·소설·에세이·인문·과학별 10분 갱신
- [랭킹 API]({BASE}/api/rank?cat=종합&kind=best): JSON, 인증 불필요

## API (읽기 전용, 인증 불필요)

- [검색]({BASE}/api/search?q=한강): 제목·저자·초성 검색, 하이브리드
- [책 상세]({BASE}/api/book?id=yes24:197068949): 가용성·공지·비슷한 책
- [오늘의 책]({BASE}/api/pick): 큐레이션 컬렉션에서 데일리 선택
- [서가 현황]({BASE}/api/overview): 장르·플랫폼·종료 통계

## 데이터·정책

{count_line}
- 구매 가격은 예스24 판매가 기준, 랭킹은 예스24 공개 순위 기준(출처·기준일 표기)
- 종료 공지는 확인된 원문만 반영하며, 미확인 정보는 추정하지 않음
- 자세한 수집·표시 정책: [{BASE}/about.html]({BASE}/about.html)

## Optional

- [소스 코드 (GitHub)](https://github.com/ChoYugyeong/seogarok)
- [사이트맵 인덱스]({BASE}/sitemap-index.xml)
- [LLM용 전체 문서]({BASE}/llms-full.txt)
"""


def llms_full_txt(books: int = 0, notices: int = 0) -> str:
    today = time.strftime("%Y-%m-%d")
    return f"""# 서가록 전체 문서 (llms-full)

> {today} 기준 · 색인 {books:,}권 · 종료 공지 {notices:,}건

## 서비스 정의

서가록은 한국어 도서의 **구독 서비스 가용성**과 **종료 예정일**을 한 화면에서 확인하는 검색 서비스다.
대상 플랫폼: 밀리(millie), 리디셀렉트(ridiselect), 교보 sam(sam), 윌라(willa).
책 구매 가격은 예스24 판매가를 사용하며, 랭킹은 예스24 공개 카테고리 랭킹을 따른다.

## 페이지 구조

- `/` — 홈: 검색, 오늘의 책, 서가 랭킹(4축·카테고리), 종료 예정 타임라인, 추천 목록, 장르 레일
- `/book/{{id}}` — 책별 랜딩(서버 렌더, Book JSON-LD, 가용성·종료일·가격·관련 책)
- `/books?page={{n}}` — 색인 책 목록(60권/쪽)
- `/about.html`, `/legal.html` — 소개/약관·개인정보

## 가용성 표기 원칙

- `available`: 확인된 구독 제공
- `ending`: 종료 공지 확인(종료일·D-day 표시)
- 그 외: **미확인** — 추정값을 표시하지 않는다.

## API 요약

| 엔드포인트 | 설명 | 인증 |
| --- | --- | --- |
| `GET /api/search?q=…&mode=hybrid` | 하이브리드/키워드/벡터 검색 | 없음 |
| `GET /api/book?id=…` | 책 상세(가용성·공지·유사도서) | 없음 |
| `GET /api/rank?cat=…&kind=best\\|steady\\|daily\\|monthly` | 예스24 랭킹+등락 | 없음 |
| `GET /api/pick` | 오늘의 책 | 없음 |
| `GET /api/overview` | 장르·플랫폼·종료 통계 | 없음 |
| `GET /api/suggest?q=…` | 자동완성 | 없음 |
| `POST /api/report` | 가용성 제보 | 없음(레이트리밋) |

## 인용 시 권장 표기

- 출처: “서가록(seogarok.com)”
- 기준일: 각 페이지의 데이터 기준일 또는 응답의 `fetched_at`
- 랭킹: “예스24 {today} 기준 {{kind}}”

## 연락

- 운영: 서가록 (개인 프로젝트)
- GitHub: https://github.com/ChoYugyeong/seogarok
"""


def index_markdown(books: int = 0, notices: int = 0) -> str:
    return f"""# 서가록 홈 (Markdown)

> 구독 4사 가용성 + 종료 예정일 + 예스24 실시간 랭킹을 교차하는 책 검색 서비스.

색인 {books:,}권 · 종료 공지 {notices:,}건.

## 링크

- [홈]({BASE}/)
- [책 목록]({BASE}/books?page=1)
- [소개]({BASE}/about.html)
- [약관]({BASE}/legal.html)
- [llms.txt]({BASE}/llms.txt)
"""


def book_markdown(book: dict, av: dict, notices: list[dict]) -> str:
    bid = str(book.get("id") or "")
    facts = [
        book.get("publisher"),
        (book.get("pubdate") or "")[:10],
        f"{book['pages']}쪽" if book.get("pages") else None,
        f"ISBN {book['isbn13']}" if book.get("isbn13") else None,
    ]
    fact_line = " · ".join(str(f) for f in facts if f)
    price = book.get("price")
    avail = []
    for key, label in SUB_LABEL.items():
        state = ((av or {}).get(key) or {}).get("s")
        if state == "available":
            avail.append(f"- {label}: 구독으로 읽기 가능")
        elif state == "ending":
            d = ((av or {}).get(key) or {}).get("d")
            avail.append(f"- {label}: {'D-' + str(d) + ' 종료 예정' if isinstance(d, int) and d >= 0 else '종료 예정'}")
    if not avail:
        avail.append("- 구독 가용성: 확인된 정보 없음 (제보로 확인 중)")
    notice_lines = "\n".join(
        f"- {SUB_LABEL.get(n.get('platform'), n.get('platform'))}: {(n.get('ends_at') or '')[:10]} 종료"
        for n in (notices or [])[:3]
    )
    desc = " ".join((book.get("description") or "").split())[:1200]
    return f"""# {book.get('title') or ''}

> {book.get('author') or '저자 미상'} · {fact_line}{f' · {int(price):,}원' if price else ''}

{desc or '설명이 아직 없습니다.'}

## 구독 가용성

{chr(10).join(avail)}

## 종료 공지

{notice_lines or '- 확인된 종료 공지 없음'}

## 링크

- [책 페이지]({BASE}/book/{bid})
- [서가록에서 보기]({BASE}/#book={bid})
- [llms.txt]({BASE}/llms.txt)
"""
