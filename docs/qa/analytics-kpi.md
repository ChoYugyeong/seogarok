# 서가록 익명 이벤트 계측 · KPI 리포트

2026-10-30 도입 · 개인정보 없는 1st-party 계측

## 왜

기능은 많지만 **검색→클릭→외부 이동→알림 켜기 전환율**을 몰랐다. 다음 기능 우선순위를
데이터로 정하기 위해 최소 계측을 붙였다.

## 수집 이벤트

| 이벤트 | 속성 | 의미 |
| --- | --- | --- |
| `view` | path | 페이지 방문 |
| `search` | q(≤60자), n(결과 수), mode | 검색 실행 |
| `search_zero` | q | 결과 0건 검색 |
| `result_click` | book, src(card/rank/seasonal/…) | 검색·레일·랭킹 결과 클릭 |
| `drawer_open` | book, title, subs, real | 상세 드로어 열림 |
| `outbound_click` | to(URL), inDrawer | 예스24·원문 등 외부 이동 |
| `collection_open` | slug | 공개 추천 목록 열람 |
| `genre_click` | genre | 장르 필터 클릭 |
| `rank_kind` / `rank_cat` | kind / cat | 랭킹 축·카테고리 전환 |
| `alert_toggle` / `alert_lead` | book, platform / day, on | 종료 알림 개별 켜기 / 시점 토글 |
| `alert_enable` | leads, watches | 웹푸시 알림 켜기 |
| `share` / `report` | book / platform | 공유 · 가용성 제보 |

## 개인정보

- 세션 랜덤 ID(브라우저 생성)만 사용, 회원·쿠키·광고 식별자 없음
- 검색어는 최대 60자, IP는 **SHA-256 해시 16자**만 보관
- `navigator.doNotTrack === "1"` 이면 전송하지 않음
- 약관·개인정보처리방침에 고지(익명 통계, 최대 90일)

## 저장·집계

- 저장: GCS `analytics/events/{YYYY-MM-DD(KST)}/{timestamp}-{rand}.json` (배치 단위)
- API: `POST /api/event` (배치 ≤20, IP당 120req/min), `GET /api/kpi?days=N` (cron secret)
- 프론트: `sendBeacon`(페이지 숨김/이탈) + 5초 디바운스 배치 전송

## KPI 정의

- `search.success_rate` = 결과 ≥1 검색 / 전체 검색
- `funnel.search_to_click_rate` = 클릭 세션 / 검색 세션
- `funnel.click_to_outbound_rate` = 외부 이동 세션 / 클릭 세션
- `top_queries`, `top_books`, `ctr_by_source`, `daily`

## 조회

```bash
curl -s "https://seogarok.com/api/kpi?days=7" -H "X-Cron-Secret: $YES24_API_KEY" | python -m json.tool
```

주간 자동 리포트: `.github/workflows/analytics-report.yml` (매주 월 09:00 KST, Actions Summary)
