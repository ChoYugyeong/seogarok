# 서가록 전 기능 테스트 리포트 — 2026-10-30

작성: Lead · 대상: `https://seogarok.com` (배포 40919211363 이후 + 대비 수정)
도구: 자체 API 스위트(`_qa/feature_api_test.py`), ego-browser 기능 플로우 2종(`browser_core_test`, `browser_features_test`), axe-core, `_qa/qa_suite.py`

## 1. 테스트 범위

| 영역 | 케이스 수 | 결과 (라이브) |
| --- | --- | --- |
| API 기능 | **57** | **57/57 PASS** |
| 브라우저 핵심 플로우 | **16** | **16/16 PASS** |
| 브라우저 기능 플로우 | **21** | **21/21 PASS** |
| 접근성(axe) | home/search/drawer | 수정 후 **0 violations** |
| QA 스위트(스모크·SEO·PWA·부하) | 26 endpoint | **PASS (0 fails/warns)** |

### API 커버리지
검색(한강/초성/모드 3종/0건/limit clamp/장문/인젝션) · 자동완성 · 책 상세(DB/예약판매/404) · 컬렉션 4개/404 · 랭킹 4축×카테고리 · overview/pick/stats · SEO 랜딩/`.md`/`/books`/사이트맵 3종/llms/robots/404 · 푸시(key/subscribe 검증/403) · 분석(event 검증/kpi 403) · 제보 검증 · ops(livez/readyz/metrics).

### 브라우저 커버리지
홈 섹션/이미지/오버플로 · 검색 자동완성·결과·필터 · 드로어(메타/가용성/유사/서재/공유/Esc/해시/포커스) · 딥링크·뒤로가기 · 404 · 컬렉션 열기/뒤로 · 랭킹 4축+카테고리+클릭 · 타임라인 날짜 전환 · 내 서재(탭/알림/푸시카드) · 취향 퀴즈 완료 · 내 구독 팝오버 · `/` 단축키 · 모바일 하단 내비/검색 · 분석 이벤트 전송 · 콘솔 오류 0.

## 2. 발견·수정한 버그

| # | 증상 | 원인 | 수정 | 심각도 |
| --- | --- | --- | --- | --- |
| 1 | **내 서재 탭이 빈 화면/깨짐** | `state.pushOn/pushLeads/personalLoading`이 `DEFAULT_STATE`에 잘못 들어가 `pushBlockHTML`에서 `undefined.includes` 예외 → render 중단 | `state`에 필드 배치 + 방어 코드(기본값) | **치명** |
| 2 | **"이어 읽기"가 비거나 일부만 표시**(사용자 제보) | 서재 책을 API에서 불러오기 전에 렌더 → 캐시에 우연히 있는 책만 노출 | `loadPersonalBooks()` 병렬 하이드레이션 + 스켈레톤 + 읽는 중→관심 순 정렬 | 높음 |
| 3 | 무의미 검색어에도 저관련 결과 5건 | keyword 후보 0일 때 벡터 근접(0.28~0.32) + YES24 유사검색 결과를 필터 없이 병합 | keyword 0 + sim<0.4 → 제거, 온디맨드 결과는 질의 토큰 어휘 매칭만 병합 | 중 |
| 4 | 랭킹 "일간" 탭 간헐적 503 | YES24 upstream 일시 오류 | 1회 재시도 + 프론트는 기존 폴백(서가 추천) | 중 |
| 5 | 도서관 대기 pill 대비 4.27:1 | gold `#8a6a24` on `#f4ecd8` | `--gold: #6b4f13` (6.5:1) | 중(접근성) |

## 3. 라이브 검증 (수정 후)

```
API      57/57 PASS
CORE     16/16 PASS   (콘솔 오류 0)
FEATURES 21/21 PASS   (콘솔 오류 0)
QA       PASS (26 endpoints, p95 519ms)
axe      home/search/drawer 수정 후 0 violations
```

## 4. 남은 알려진 이슈 (낮은 우선순위)

| 항목 | 설명 | 다음 조치 |
| --- | --- | --- |
| 운영 DB 설명 부재 | 배포 파이프라인 스냅샷 기반이라 `description`이 비어 있음(로컬 16,073건). 책 랜딩은 속성 기반 fallback으로 대체 | YES24 itemDetail 설명 수집 파이프라인 |
| 랭킹 일간 upstream | YES24 일간 API가 간헐 503 → 화면은 "서가 추천" 폴백 | 주기 모니터링(Sentry-like 로그) |
| 필터 0건 안내 | "구독 제공" 필터 시 결과 0이면 일반 empty 문구 | “필터를 해제해 보세요” 문구/버튼 추가 |
| 취향 퀴즈 종료 | API 모드에선 결과 페이지 대신 실제 검색 결과로 이동(의도된 설계) | 결과 헤더에 "취향으로 고른 책" 라벨 |
| 공유 토스트 | 이전 액션 토스트가 남아 보일 수 있음 | 공유 후 명시 토스트 |
| GSC/네이버 | 소유확인·사이트맵 제출 진행 중 | 제출 후 색인 추이 확인 |

## 5. 재현

```bash
# API 57케이스
python _qa/feature_api_test.py https://seogarok.com

# 브라우저 플로우(ego, 단일 세션 + 자동 종료)
ego-browser nodejs -e "await import('file:///C:/Dev/seoga/_qa/browser_core_test_live.mjs')"
ego-browser nodejs -e "await import('file:///C:/Dev/seoga/_qa/browser_features_test_live.mjs')"
```

---

## 6. 후속 개선 완료 (2026-10-30)

| 개선 | 내용 | 검증 |
| --- | --- | --- |
| **필터 0건 UX** | "선택한 조건에 맞는 책이 없어요" + 전체 N권 안내 + **필터 해제** 버튼(`reset-filters`) | 라이브: 필터 0건 → 안내/버튼 → 해제 시 24권 복귀 |
| **설명 데이터 파이프라인** | ① 수집 목록 API에 `detail=Y`(contentDetail 포함) ② fallback 스냅샷 재생성(18,917권 중 **16,140권 설명**, 6.7MB) ③ 런타임 `fetch_extras`에 description 추가 → `/api/book`·`/book` SSR 보강 | 라이브 SSR/JSON-LD 설명 **280자 실제 소개** (fallback 문구 제거), `/api/book` 471자 |
| **API 회귀 CI** | 원인: `_qa/`가 gitignore라 CI에 스크립트 없음 → **`tests/`로 이동해 커밋**, qa-gate에 57케이스 실행 | **qa-gate PASS** (run 40926141005) |

### 남은 것
- 일부 책(예: 소년이 온다) DB 설명 공백 → 상세/SSR 런타임 보강으로 커버, 배치 보강은 후속
- 랭킹 일간 upstream 간헐 503 (폴백 동작)
- GSC/네이버 색인 추이 확인
