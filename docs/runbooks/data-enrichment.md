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
