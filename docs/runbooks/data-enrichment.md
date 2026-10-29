# 데이터 설명 보강 런북 (주간 배치 · 대체 소스)

## 현재 상태 (2026-10-30)

- 카탈로그 설명 커버리지: **16,332 / 18,917 (86%)**
- 남은 14%는 **YES24 API·HTML 모두 책소개가 없는 책** (잡지·세트·예판·구판 등)
- 키 없이 사용 가능한 대체 소스(Open Library)는 한국어 커버리지 0/12로 확인됨
- Google Books는 **키 없이 429(할당량)** → API 키 필요
- 네이버 책 API도 Client ID/Secret 필요
- 도서관정보나루는 data.go.kr 인증키 필요

## 주간 로컬 배치 (권장)

```powershell
# 1) 1회 실행
pwsh -NoProfile -File C:\Dev\seoga\scripts\enrich_weekly.ps1

# 2) Windows 작업 스케줄러 등록 (매주 일 04:30)
schtasks /Create /TN "seogarok-enrich-weekly" /SC WEEKLY /D SUN /ST 04:30 `
  /TR "pwsh -NoProfile -File C:\Dev\seoga\scripts\enrich_weekly.ps1"
```

스크립트 동작
1. YES24 API로 누락 설명 보강 (`--limit 1200`)
2. YES24 HTML 상세페이지 보강 (`--html --skip-api --limit 800`, robots 준수)
3. fallback 스냅샷 재생성 (`scripts/rebuild_fallback.py`)
4. 커버리지 출력 (`python -m ingest.books.desc_coverage`)
5. 커밋/푸시는 출력되는 명령으로 수동(또는 CI 자동 배포가 다음 날 반영)

## 대체 소스 키 설정 (선택)

### Google Books (ISBN 설명/페이지수)
1. https://console.cloud.google.com → API "Books API" 사용 설정
2. API 키 발급 → `.env`에 추가
3. 배치 실행: `python -m ingest.books.enrich_descriptions --limit 500 --workers 3`
   (키가 있으면 YES24에 소개 없을 때 자동 시도)

### 네이버 책 검색 API
1. https://developers.naver.com → 애플리케이션 등록 → "책 검색" API 추가
2. Client ID/Secret 발급 → `.env`에 추가
3. 위와 동일하게 배치 실행 (자동 시도)

### 도서관정보나루 (data4library)
1. https://www.data4library.kr → 인증키 신청
2. (구현 예정) `NL_API_KEY` 로 adapter 추가 — 현재는 수동 확인용

## 검증

```bash
python -m ingest.books.desc_coverage      # d/n
curl -s https://seogarok.com/api/stats | python -m json.tool | grep description_count
```

- `/api/stats.description_count` 가 배포마다 갱신되는지 확인
- 고유 정보가 없는 책은 랜딩에 `noindex,follow` 자동 적용

---

## Google Books 실측 결과 (2026-10-30)

- **ISBN 조회: 0/20** — 한국어 ISBN이 Google Books에 색인되지 않은 경우가 대부분
- **제목 검색: 표본 60권 중 6권(10%)**, 한국어 유명 도서는 2,000자 내외 소개 확보 (예: 소년이 온다 5,184자→2,000자 cap)
- 우리 파이프라인 제목 정규화 매칭 적용 후: 600권 시도 → 57권 보강(9.5%), 추가 400권 → 6권(일일 쿼터 소진 영향)
- **무료 한도**: 분당 100회/일일 1,000회 → `_google_get()` 레이트 리미터(0.75s, 80/min) + 429 재시도 적용
- 현재 카탈로그 설명 커버리지: **16,391 / 18,917 (86.6%)**, fallback 스냅샷 16,458건
- CI: `GOOGLE_BOOKS_API_KEY` Secret 등록, 배포 시 200권/일 best-effort, 주간 로컬 배치 600권/일

## 대체 소스 상태

| 소스 | 상태 |
| --- | --- |
| Google Books | ✅ 키 등록 완료(로컬+CI), 제목 검색으로 일부 보강 |
| 네이버 책 API | ⛔ 가입/발급 불가 확인(사용자) → **보류** |
| 도서관정보나루(data4library) | ⛔ 인증키 발급 불가 확인(사용자) → **보류** |
| Open Library | ⛔ 한국어 커버리지 0/12 |
| 알라딘 Open API | ⛔ 현재 중단 |

---

## API 응답 캐시/아카이브 정책 (2026-10-30)

### 저장하는 것 (OK)
- **카탈로그/DB에 결과 저장**: 제목·저자·출판사·ISBN·가격·표지·**설명·페이지·평점**을 `data/catalog.jsonl` → DB로 아카이브. 서빙 시 API 호출 없음(빠름).
- **원본 API 응답 디스크 캐시**: `data/enrich_cache/` (gitignored, 커밋 금지)
  - YES24: ISBN/아이템 단위, 30일 TTL, 실패는 3일 TTL
  - Google Books: ISBN/제목 단위. **0건 응답도 캐시**(쿼터 절약), 429/네트워크 오류는 캐시 안 함
  - `--refresh` 로 강제 재조회
- **런타임 extras 캐시**: 서버 메모리 10분 캐시(`server/on_demand.py`) — 책 상세에 붙는 평점/페이지용.

### 저장하지 않는 것
- 원본 응답 벌크를 공개 저장소/공개 API로 재배포하지 않음 (약관·저작권)
- 캐시 디렉토리는 `.gitignore` (`data/enrich_cache/`) — 로컬/배치 머신에만 존재
- 출처 표기 유지: 카드/랜딩에 YES24/Google Books 링크 유지

### 효과
- 같은 책을 다시 보강할 때 네트워크 호출 0회 → 주간 배치가 수십 초~수 분으로 단축
- Google 쿼터 소진 시 **서킷브레이커**(연속 429 3회 → 남은 호출 즉시 스킵)로 배치가 빠르게 종료
