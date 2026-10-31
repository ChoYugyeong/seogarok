# unslop polish — 서가록 (2026-10-31)

이 패스는 [unslop](https://github.com/heydamir/unslop) by Damir Sokolovsky ([@heydamir](https://x.com/heydamir)) 을 적용해 진행했다. unslop은 CC BY 4.0이며, 이 문서는 그 크레딧과 함께 남긴다.

## 방향 (direction)

- **Product.** 밀리·리디셀렉트·교보 sam·윌라의 가용성과 종료 예정을 한 화면에서 확인하는 한국 독자용 책 색인.
- **Character.** 차분한, 정확한, 종이 냄새.
- **World.** 서가와 책등, 도서관의 종이 카드, 먹과 주홍.
- **Moments.** 실제 책 표지가 늘어선 "내 서재" 레일, 색인 카드의 숫자(권수·종료 공지·기준일), 오늘의 책 한 권.
- **Signature.** 네 권의 책등과 선반 기준선(로고). 색은 크롬이 아니라 실제 표지와 한 번의 검색 CTA에 둔다.

## 감사 (audit → fix)

| Slop sign | Where | Fix |
|---|---|---|
| 헤더에 채워진 버튼 2개 (로그아웃 + 내 구독) | nav | 로그아웃은 조용한 텍스트, 내 구독은 아웃라인. 검색 CTA 하나만 액센트 |
| 모든 것이 풀 필(pill) — 55개 | 카테고리·빠른 검색·최근 검색·필터 | 칩은 8px 라운드, 최근 검색은 밑줄 텍스트, 상태는 점+텍스트 |
| accent-soft 표면이 콘텐츠 카드·타임라인에 | pick 카드, 타임라인 날짜 | 카드/날짜는 중성 표면으로. 색은 실제 표지·D-day 의미에만 |
| 700~800 웨이트 남발 | 카드·숫자·버튼·섹션 | 500/600으로. 히어로는 Hahmlet 500 |
| 작은 히어로(40px)·촘촘한 자간 | hero | 46px 데스크톱/32px 모바일, -0.02em, line-height 1.18 |
| 그라디언트 폴백 표지 | cover fallback | 저채도 종이 톤 + 타이포 표지(제목/저자)로 교체 |
| 최근 검색/빠른 검색 중복 필 | hero | 최근 검색은 작은 밑줄 링크, 빠른 검색은 조용한 칩 |
| 한국어 단어 중간 줄바꿈 | hero lede, 카드 제목 | `word-break: keep-all` |
| hover scale, `transition: all` 느낌 | 카드·칩 | scale 제거, 명명된 색/보더 transition, 스크롤 reveal 정적화 |
| 긴 placeholder·느낌표 | 검색·제보 토스트 | "책 제목, 저자, ISBN", 느낌표 제거 |

## 패스 (passes)

1. **Spacing** — 4px 리듬(32/48), 그리드 24/16, 카드 간격 8, 히어로 갭 48.
2. **Color** — 크롬은 중성, 액센트는 검색 CTA·로고·D-day. pick/타임라인 accent-soft 제거.
3. **Icons** — 이모지 없음(★은 평점 데이터), 상태 점 하나로 통일.
4. **Copy** — 느낌표 제거, 짧은 라벨, "책 제목, 저자, ISBN".
5. **Type** — Hahmlet 500 디스플레이 / IBM Plex Sans KR 400·500, 800 제거.
6. **Layout** — 헤더 조용히, 히어로 비대칭 split 유지, CTA 하나.
7. **Details** — 라운드 8/12/16, 중첩, 수치 tabular, 그림자 제거.
8. **Visuals** — 실제 표지가 색을 담당, 폴백은 종이 표지.
9. **Motion** — 색/보더 140ms 한 커브, 스크롤 등장 제거, hover scale 제거.

## 파일

- 이전/이후: [before.png](unslop/before.png) · [after-live.png](unslop/after-live.png) · [after-full-live.png](unslop/after-full-live.png)
- 모바일: [after-mobile.png](unslop/after-mobile.png) · [after-mobile-live.png](unslop/after-mobile-live.png)
- 변경: `styles.css` (unslop 레이어), `app.js` (표지 폴백·카피), `index.html` (히어로 카드·placeholder), `ads.js` (동의 배너 카피)

## Story video

- [unslop-story.mp4](unslop/unslop-story.mp4) — 10초 · 1080×1080 · 30fps · H.264
- 구성: redline이 표시된 before(2.4s) → morph/crossfade(1s) → after + caption 4단계(5s) → 브랜드 엔드카드(1.6s)
- 크레딧: 영상 전체에 unslop by @heydamir · CC BY 4.0
- 포스터: [unslop/story-poster.png](unslop/story-poster.png)

## 검색 결과·책 상세 패스

- 검색: 결과 제목 26px/500, 결과 수 muted, 필터/정렬 여백 4px 리듬
- 책 상세: Hahmlet 34px/500 제목, 가격 muted 500, CTA 8px/500
- 한 줄 요약: accent-soft 박스 → hairline rule + muted caption
- 섹션 제목 20px/500, 관련 책 제목 500, 가용성 행 radius 8, keep-all
- 라이브: [검색 결과](unslop/search-after.png) · [책 상세](unslop/book-after.png)

## Morph story video (실제 값 보간)

- [unslop-story-morph.mp4](unslop/unslop-story-morph.mp4) — 10초 · 1080×1080 · 30fps
- before 2.0s(redline) → **실제 CSS 값 보간 morph 2.0s** → after 4.4s(caption) → 엔드카드 1.6s
- ego로 before/after computed style을 측정하고 13단계로 spacing·radius·color·type·font-weight 값을 직접 보간해 캡처 (crossfade 아님)
- 포스터: [morph-poster.png](unslop/morph-poster.png)
- 이전 crossfade 버전: [unslop-story.mp4](unslop/unslop-story.mp4)

## 모바일 검증

- 검색: [search-mobile-after.png](unslop/search-mobile-after.png) — 26px 결과 제목, 2열 표지, overflow 없음, 하단 내비 정상
- 책 상세: [book-mobile-after.png](unslop/book-mobile-after.png) — **1열 stack**, 커버 150px, 본문 350px, h1 24px/500, overflow 없음
- 발견/수정: service worker가 /book/... 문서를 cache-first로 굳혀 모바일에서 옛 레이아웃이 보이던 문제 → sw.js v4, 
eq.mode === 'navigate' network-first

