# 홈 화면 오버라이드 — Seogarok

> `MASTER.md`(UI UX Pro Max 생성)의 규칙보다 이 파일이 우선합니다.
> 이유: MASTER의 Swiss Modernism 2.0 / parchment+amber 팔레트는 브랜드(서가록 = paper & ink)와
> `design-taste-frontend` 하우스 규칙(크림+테라코타 금지)과 충돌합니다. 제안은 토큰·체크리스트
> 참고용으로만 채택하고, 시각 방향은 아래를 따릅니다.

## 시각 방향 (2026-10-29 확정 — 3개 레퍼런스 합성)

**따뜻한 종이&잉크(비주얼) × 밀리의서재(책 서비스 구조) × 토스(레이아웃·타이포)**

| 레퍼런스 | 차용한 것 |
| --- | --- |
| paper & ink | 크림 `#f7f2e8` 배경, 잉크 `#17120e` 텍스트, 버미리언 `#b8371f` 포인트, 종이 질감의 카드 |
| 밀리의서재 | 상단 카테고리 필, 랭킹 리스트(번호+표지+제목), 오늘의 책, 책 중심 정보 구조 |
| 토스 | Pretendard 굵은 제목, 화이트→종이 카드의 명확한 계층, 큰 숫자(tabular), 둥근 카드·여백 리듬, 간결한 문구 |

### 이전 방향 (폐기)
- 에디토리얼 세리프 + 크림: 한국 사용자 체감 낯섦(사용자 피드백)
- 화이트+블루 순수 서비스형: 책 서비스 정체성 약함

## 시각 토큰 (확정)

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

## 적용 결과 (2026-10-29)

| 항목 | 상태 |
| --- | --- |
| 딥링크/뒤로가기 (`?q=`, `?col=`, `?tab=`, `#book=`) | ✅ 적용 — popstate 복원, 드로어 닫기 시 history.back |
| 모바일 하단 내비게이션(4개, safe-area) | ✅ 적용 — ≤860px에서 상단 탭 숨김 |
| 드로어 로딩 스켈레톤 + 포커스 트랩 + Esc + 포커스 복귀 | ✅ 적용 |
| 검색 콤보박스 `aria-expanded`/`aria-activedescendant` + 행 id | ✅ 적용 |
| `inputmode`/`enterkeyhint` 검색 인풋 | ✅ 적용 |
| 스킵 링크(본문으로) | ✅ 적용 |
| sticky nav focus 비가림 (`scroll-padding`) | ✅ 적용 |
| 섹션 리빌 300ms/y8 + reduced-motion | ✅ 적용 |
| 눌림 피드백(active translate) + hover 150–300ms | ✅ 적용 |
| 카테고리(장르)를 히어로 다음 1번 섹션으로 (Marketplace/Directory 패턴) | ✅ 적용 |
| 첫 로딩 스켈레톤(데모 데이터 깜빡임 제거) | ✅ 적용 |
| 다크 모드 | ⏸ 보류 (라이트 단일 테마 유지) |
| 차트/데이터 접근성 | ✅ 라벨 텍스트 병기 (색 단독 의존 없음) |

## Pre-Delivery 체크리스트 결과

- [x] 이모지 아이콘 없음 (SVG만)
- [x] 클릭 요소 `cursor:pointer`
- [x] hover 150–300ms 전환
- [x] 라이트 모드 텍스트 대비 4.5:1 이상
- [x] 키보드 포커스 가시
- [x] `prefers-reduced-motion` 존중
- [x] 반응형 375 / 768 / 1024 / 1440 확인

## 2026-10-29 추가 (사용자 요청 4건)

| 항목 | 처리 |
| --- | --- |
| 서가 랭킹 2단 리스트 | 1~3위 큰 카드(표지 84×118, 순위·가격) + 4~10위 컴팩트 리스트 |
| 랭킹 데이터 정직성 | **예스24 실시간 베스트셀러 API** 연동 (/api/rank?cat=, 10분 캐시). 출처·기준일 표기, 실패 시 503 + 서가 추천 폴백 |
| 카테고리 필 고정 | .cat-bar sticky(상단 내비 아래), 검색/컬렉션 화면(ody.is-wide)에서는 숨김 |
| 오늘의 책 히어로화 | 큰 배너 카드(좌: 문구·CTA / 우: 176px 표지) |

## 2026-10-29 추가 2 (랭킹 고도화 3건)

| 항목 | 처리 |
| --- | --- |
| 베스트/스테디/일간/월간 4축 | /api/rank?cat=&kind=best|steady|daily|monthly, 예스24 공식 엔드포인트 사용. UI에 종류 탭 |
| 어제 대비 순위 변동 | server/rank_store.py — 일별 스냅샷 
ank/{YYYY-MM-DD}/{kind}-{cat}.json를 GCS(gs://seogarok-reports)에 저장, 다음날 조회해 delta 계산(▲빨강/▼파랑/NEW). Cloud Run read-only FS 대응(/tmp 폴백) |
| 카테고리 필 → 랭킹 연동 | 상단 카테고리 필 클릭 시 검색 + 랭킹 카테고리 동시 전환, 필 활성 상태 동기화 |
| 평점 표시 | 예스24 detail=Y의 starScore를 랭킹 카드에 ★ 표시 |

