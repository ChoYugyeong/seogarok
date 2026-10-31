# GSC 자동화 (쓰기 권한)

## 왜 재연결이 필요한가

기존 GSC 토큰은 `webmasters.readonly` scope로 발급되어:
- URL 검사·검색 성과 조회는 가능
- **사이트맵 제출은 403** (`insufficient authentication scopes`)

서가록 서버는 `auth/gsc_token.json`의 refresh token을 사용한다. scope를
`https://www.googleapis.com/auth/webmasters`로 바꿨으니 **한 번 재승인**하면
사이트맵 자동 제출이 켜진다.

## 재연결

1. 로컬에서 연결 링크 생성 (30분 유효):
   ```bash
   cd C:\Dev\seoga
   python scripts/gsc_connect_link.py
   ```
2. 출력된 `https://seogarok.com/api/auth/gsc/start?t=...` 를 브라우저에서 열고
   `seogarok.com` 속성 소유 Google 계정으로 승인
3. `/?gsc=ok` 리디렉션 확인

## 자동화

매일 04:10 KST `ai-crawl.yml`이 서버 `POST /api/gsc/cron`을 호출한다.

- `sitemap-books.xml` · `sitemap.xml` · `sitemap-index.xml` 자동 제출
- 사이트맵 목록/처리 상태 확인
- 검색 성과(최근 7일)와 URL 검사 표본(PASS/NEUTRAL) 수집
- 결과를 GCS `reports/gsc/{date}.json`에 저장
- GitHub에 **AI crawl daily 이슈**로 리포트

재연결 전에는 `/api/gsc/cron`이 409(`gsc_reauth`)를 반환하고, 리포트에 재연결 필요가 표시된다.

## 한계

- Google URL Inspection API는 **색인 요청**을 지원하지 않는다. 색인 요청은 Search Console UI에서 해야 한다.
- 인증 오류(재연결 전)에서는 사이트맵 자동 제출이 되지 않는다.
