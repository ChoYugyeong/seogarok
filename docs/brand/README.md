# 서가록 브랜드 아이덴티티 — A · 책등의 결

`fatihaydost/brand-identity-skill` 워크플로 산출물. **A · 책등의 결** 선택.

- 보드: [board.png](board.png) · 카드 리뷰: [review.png](review.png) · 로고 시트: [logo-sheet.png](logo-sheet.png)
- **가이드라인 키트**: [kit-A/brand-guidelines.pdf](kit-A/brand-guidelines.pdf) (8페이지)
- 사이트 적용 프리뷰: [site-a-desktop.png](site-a-desktop.png) · [site-a-mobile.png](site-a-mobile.png)
- 디자인 토큰: [kit-A/tokens/tokens.css](kit-A/tokens/tokens.css) · [tokens.scss](kit-A/tokens/tokens.scss) · [tailwind.palette.js](kit-A/tokens/tailwind.palette.js) · [tokens.dtcg.json](kit-A/tokens/tokens.dtcg.json)
- 로고 파일: [kit-A/logo/](kit-A/logo/) (SVG/PNG 16종: full color, one color, reversed, favicon, app icon, symbol)
- 폰트 정보: [kit-A/fonts.md](kit-A/fonts.md)

## 핵심

| 항목 | 값 |
|---|---|
| 심볼 | 네 권의 책등 + 선반 기준선, 한 권만 주홍 |
| 디스플레이 | Hahmlet 500 |
| 본문 | IBM Plex Sans KR 400·600 |
| 주 색 | #B8371F (주홍) · 먹 #231911 · 종이 #F7F2E8 |

## 게이트/경고

- 전 항목 게이트 통과(대비·라이선스·글리프·16/32px 렌더)
- 경고: 링크/본문 2.96:1 → 링크 밑줄 병행으로 보완, 16px 세부 손실·detail-creep(휴리스틱)
- AI 기본값 3개(cream/terracotta/literal)는 기존 자산 계승 사유로 기록

## 다음

1. 사이트(seogarok.com)에 A 토큰 적용: CSS 변수 교체 → 헤더/파비콘 → 카드/랜딩
2. 적용 후 라이트/다크·모바일·접근성 대비 검증
## 사이트 적용 완료 (2026-10-30)

- 헤더: `assets/brand/logo-lockup.svg` (심볼+워드마크), 푸터 심볼
- 타이포: Hahmlet 600 (디스플레이) / IBM Plex Sans KR 400·500·600 (본문) · tnum
- 색: 먹 `#231911` · 보조 텍스트 `#5e534a` · 경계 `#d8d1c2` (기존 종이/주홍 유지)
- 파비콘·PWA 아이콘: 브랜드 앱 아이콘으로 교체 (`assets/brand`, `icons`)
- 링크 밑줄 보완 (A의 link-on-text 대비 경고 완화)
- 검증: 라이브 폰트 로드·로고·모바일 오버플로 없음, QA 스위트 PASS, API 68/68, axe 사이트 위반 0(브라우저 확장 주입 노드 제외)
