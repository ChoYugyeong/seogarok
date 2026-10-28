# 홈 화면 오버라이드 — Seogarok

> `MASTER.md`(UI UX Pro Max 생성)의 규칙보다 이 파일이 우선합니다.
> 이유: MASTER의 Swiss Modernism 2.0 / parchment+amber 팔레트는 브랜드(서가록 = paper & ink)와
> `design-taste-frontend` 하우스 규칙(크림+테라코타 금지)과 충돌합니다. 제안은 토큰·체크리스트
> 참고용으로만 채택하고, 시각 방향은 아래를 따릅니다.

## 시각 방향 (확정)

| 항목 | 값 |
| --- | --- |
| 방향 | **paper & ink** — 도서관 색인카드/활자/종이 |
| 배경 | `#f7f2e8` (cream paper) |
| 표면 | `#efe8da` 계열 |
| 잉크 | `#17120e` (near-black ink) |
| 액센트 | `#b8371f` (vermilion) — 액션과 한두 곳에만 |
| 타입 | Noto Serif KR (display) + Pretendard (body) |
| 이미지 | 표지는 실제 예스24 표지, 아카이브 사진은 소개/보조 섹션에서만 |

## UX Pro Max에서 채택한 것

- 터치: `touch-action: manipulation`, coarse pointer에서 최소 44px 터치 타깃
- 포커스: 항상 보이는 포커스 링, `scroll-padding-top`으로 sticky nav가 포커스를 가리지 않게
- 모션: `prefers-reduced-motion` 존중, hover 150–300ms
- 체크리스트: 이모지 아이콘 금지( SVG만), 클릭 요소 `cursor:pointer`, 라이트 모드 대비 4.5:1
- 데이터: 종료/가용성은 확인된 것만 표시(추정 금지)

## 채택하지 않은 것

- Swiss Modernism 2.0 스타일·팔레트(크림+앰버) — 브랜드/하우스 규칙 충돌
- Testimonials 캐러셀 패턴 — 실제 후기 데이터 없음(허위 금지)
- Cormorant Garamond 단독 사용 — 한글 글리프 없음 → Noto Serif KR 유지

## 남은 UX 개선 후보

1. 뒤로가기/딥링크 (`?q=` 검색, `#book=` 상세)
2. 모바일 하단 내비게이션(≤5)
3. 드로어 로딩 스켈레톤
4. 검색 콤보박스 `aria-expanded`/`aria-activedescendant`
