# 서가록 경쟁력 QA 리포트 — 2026-10-29

대상: `https://seogarok.com` · 배포 `40869341886` (success) · 작성: Lead
도구: 자체 QA 스위트(`_qa/qa_suite.py`), axe-core 4.10.2, ego-browser(Chromium), YES24 Open API

## 0) 이번 라운드에 추가한 경쟁력 기능

| 기능 | 내용 | 검증 |
| --- | --- | --- |
| 상세 메타 강화 | 예스24 `itemDetail(detail=Y)`로 평점·쪽수·판형·ISBN·판매지수·시리즈 표시. 예약판매/절판도 상세 열림 | `가호` ★8.8 · 376쪽 · 128×188mm · ISBN · 판매지수 465,066 |
| 랭킹 × 가용성 | 랭킹 API가 ISBN13으로 카탈로그와 조인 → 랭킹 카드에 구독사 배지·종료 D-day(매칭 시) | `/api/rank` `subs` 필드 응답 |
| 공유 | 상세 드로어 공유 버튼(Web Share API → 미지원 시 링크 복사) | `drawer-share` 렌더 확인 |
| 보안 헤더 | X-Content-Type-Options · Referrer-Policy · X-Frame-Options · Permissions-Policy · HSTS | 라이브 헤더 확인 |
| SEO | JSON-LD(WebSite+SearchAction) · sitemap 2→17 URL | 라이브 확인 |

## 1) 서버/API QA

| 항목 | 결과 |
| --- | --- |
| API 스모크 18종 (`/livez` `/readyz` `/api/search` 초성 포함 `/api/suggest` `/api/overview` `/api/pick` `/api/stats` `/api/notices` `/api/collections` `/api/collection` `/api/rank`×2 `/api/book` DB·예약판매·404) | **18/18 PASS** |
| 부하 48req / 12 workers | p50 **479ms** · p95 **625ms** · max 648ms · **0 errors** · 25.6 rps |
| 에러 응답 | 미지원 경로 404 JSON 정상 |
| 압축 | JSON gzip 동작(512B+) |

## 2) 보안 헤더

| 헤더 | 값 |
| --- | --- |
| Strict-Transport-Security | `max-age=31536000; includeSubDomains` |
| X-Content-Type-Options | `nosniff` |
| Referrer-Policy | `strict-origin-when-cross-origin` |
| X-Frame-Options | `SAMEORIGIN` |
| Permissions-Policy | `geolocation=(), microphone=(), camera=()` |

## 3) SEO / 메타

| 항목 | 이전 | 현재 |
| --- | --- | --- |
| title / description / canonical | PASS | PASS |
| OG / Twitter 카드 | PASS | PASS |
| JSON-LD | **FAIL(누락)** | **PASS** (WebSite+SearchAction) |
| sitemap.xml | 2 URL | **17 URL** (홈·about·legal·컬렉션4·장르10) |
| robots.txt | PASS | PASS |
| h1 개수 | 1 | 1 (검색 페이지 h1 추가) |

## 4) 접근성 (axe-core)

| 페이지 | 이전 | 현재 |
| --- | --- | --- |
| 홈 | color-contrast **31노드** + heading-order | **0 violations** |
| 검색 | axe 미주입(검사 불가) | **0 violations** |
| 상세 드로어 | contrast 1노드 + aria-allowed-role | **0 violations** |

수정 내역
- `--text-3` `#867a6a`(3.75:1) → `#63584b`(5.1~6.2:1)
- 랭킹 배지: ▲`#b42318`, ▼`#1d4ed8`, ★`#7a4f00` (전부 4.5:1 이상)
- 섹션 제목 h3→h2, 검색 결과 제목 h1화, drawer `<aside role=dialog>`→`<div>`
- 작은 타깃(`.sec-more`·`.notice-src`·푸터 링크) 최소 24px

## 5) 성능 (홈, 데스크톱, 캐시 콜드)

| 지표 | 값 |
| --- | --- |
| TTFB | **122ms** |
| FCP | **508ms** |
| DOMContentLoaded | 523ms |
| Load | **587ms** |
| 전송량 | **114KB** (JS/CSS 약 82KB + fetch 31KB) |
| 깨진 이미지 | 0 |
| alt 누락 | 0 (커버는 `alt=""` 장식 처리) |

## 6) 모바일 / 반응형

| 항목 | 결과 |
| --- | --- |
| 375 / 390 / 768px 가로 넘침 | **없음** |
| 하단 내비 5개 | 정상 |
| 터치 타깃 24px 미만 | 1건(문맥 링크) — WCAG 인라인 예외 |
| 12px 미만 텍스트 | 89노드(배지·등락 표시) — 정보성 배지로 유지 |

## 7) PWA / 오프라인

| 항목 | 결과 |
| --- | --- |
| manifest | name·display·start_url·icons(3) · theme #f7f2e8 |
| service worker | 등록·제어 정상 |
| 오프라인 재방문 | **앱 셸 렌더 정상** (오프라인에서도 홈 UI 표시/API는 graceful fail) |

## 8) 상호작용 회귀 확인

| 시나리오 | 결과 |
| --- | --- |
| 딥링크 `?q=한강` → 복원·뒤로가기 | PASS |
| 랭킹 종류 탭(베스트→스테디) | PASS (1위 가호→모순) |
| 카테고리 필→랭킹 전환 | PASS (에세이) |
| 상세 드로어 Esc·포커스·공유 | PASS |
| 검색 자동완성 키보드 | PASS |

## 9) 남은 리스크

1. **랭킹 등락 ▲▼**: 10/29 스냅샷이 첫 기록 → **10/30부터 실제 표시**. (GCS `rank/2026-10-29/*.json` 확인)
2. **가용성 배지 매칭률**: 공지·제보 기반이라 랭킹 책 대부분 “미확인” → 데이터 축적 필요.
3. **HSTS**: 서버 응답에 적용했으나 Cloud Run GFE에서 최종 확인 필요(라이브 헤더 PASS).
4. **tiny text(89)**: 배지류 11~11.5px. 모바일 가독성 민감 사용자 대상으로 12px 상향 여지 있음.

## 10) 다음 배포 게이트(권장)

- CI에 `qa_suite.py`(스모크+SEO+헤더) 연결: PR마다 자동 PASS/FAIL
- axe 검사 CI(Playwright/axe-core) 주 1회
- 랭킹 스냅샷 일별 성공 여부 모니터링(GCS 오브젝트 신선도)

---

# 2차 라운드 — SEO/푸시/개인화/CI (2026-10-29 저녁)

## 구현 결과

| 항목 | 내용 | 라이브 검증 |
| --- | --- | --- |
| 책별 SEO 랜딩 | `/book/{id}` 서버 렌더 HTML + Book JSON-LD + OG/canonical | 200 · 5,315B · `"@type": "Book"` · canonical · og:image |
| 책 사이트맵 | `/sitemap-books.xml` 5,000권, robots.txt 연결 | 200 · 749KB · `<loc>` 5,000 |
| 웹푸시 종료 알림 | VAPID 자동 생성(GCS `push/vapid.json`), `/api/push/{key,subscribe,unsubscribe,cron}` | key 200 · subscribe 200 · cron dry 200 · 무인증 403 |
| 알림 UI | 내 서재에 "종료 알림 켜기", 서재/알림 변경 시 watches 자동 동기화 | `.push-card` + 버튼 라이브 확인 |
| SW 푸시 | `push` → 알림 표시, `notificationclick` → 해당 책 딥링크, 캐시 v3 | SW 캐시 `seogarok-v3` 등록 |
| 개인화 홈 | 최상단 "이어 읽기 / 내 서재에서 볼 책 / 최근 본 책" | `.personal-section` 첫 섹션 · "읽던 책부터 이어가세요 · 내 구독 2곳" |
| CI 게이트 | `qa.yml`(라이브 QA), `push-digest.yml`(매일 09:00 KST 발송) | 워크플로 파일 추가 |

## 최종 QA (라이브)

```
QA PASS (warn 0건)
- API 21종 전부 200(기대 404 포함)
- sitemap.xml 17 URL + sitemap-books.xml 5,000 URL
- JSON-LD ✓ · h1 1
- 부하 48req/12workers: p50 342ms · p95 491ms · max 515ms · 0 errors · 29.5 rps
```

## 남은 검증/리스크

1. **실제 푸시 발송 E2E**: 기기 알림 권한·푸시 엔드포인트가 필요해 서버 측 dry-run까지 검증. 실제 발송은 사용자가 내 서재에서 "종료 알림 켜기"를 누른 브라우저에서 동작.
2. **종료 3일 내 공지 부재 시 알림 없음**: 현재 데이터 기준 3일 내 종료 공지가 없어 cron 발송 0건(정상). 메시지 생성 로직은 16일 뒤 종료 건으로 별도 검증.
3. **cron 인증**: 별도 시크릿 대신 `YES24_API_KEY`를 `X-Cron-Secret`으로 사용(GitHub Secrets에 이미 존재). 추후 전용 시크릿 회전 권장.
4. **SEO 색인**: sitemap-books는 Google Search Console에 제출 권장.
