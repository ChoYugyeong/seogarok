# 검색 노출(색인) 런북

목표: `seogarok.com`이 Google·네이버 검색에 노출되게 하기.
기술 SEO는 대부분 완료되어 있고, **검색엔진 등록·사이트맵 제출·색인 요청**이 남은 핵심이다.

## 현재 상태 (2026-10-30 진단)

| 항목 | 상태 |
| --- | --- |
| robots.txt | 200, Sitemap·Content-Signal 포함 |
| sitemap-index.xml | 200 (sitemap.xml 2,159 / sitemap-books.xml 5,000 URL) |
| 홈 메타 | title·description·canonical·OG 7개·JSON-LD(WebSite+SearchAction, Organization) |
| 책 랜딩 | JSON-LD `Book`, 한 줄 요약, 관련 책 10, canonical, md 대안 |
| thin 페이지 | 고유 정보 없는 책은 `noindex,follow` |
| 봇 방문 | **Googlebot·네이버 Yeti 방문 확인** (홈/robots/app.js) |
| 구글 소유확인 | ❌ 아직 (Search Console 등록 필요) |
| 네이버 소유확인 | ✅ meta 태그 심어둠 (`naver-site-verification`) |
| www.seogarok.com | ❌ DNS 없음 (getaddrinfo 실패) → 필요 시 CNAME 추가 |
| IndexNow | ✅ 키 라우트 + 배포 후 자동 제출 (Bing/Yandex) |

## 1) Google Search Console (필수)

1. https://search.google.com/search-console 접속
2. **속성 추가 → URL 접두어** `https://seogarok.com` (도메인 속성은 DNS TXT 필요)
3. 소유 확인: HTML 파일 업로드 또는 DNS TXT — GSC가 준 값을 알려주면 사이트에 반영/등록
4. **Sitemaps** → `https://seogarok.com/sitemap-index.xml` 제출
5. **URL 검사** → `https://seogarok.com/` 색인 요청
6. 대표 책 랜딩 2~3개도 URL 검사 → 색인 요청
7. 며칠 뒤 Coverage/Pages 리포트에서 색인 수 확인

> 사이트맵이 5,000개 책 URL을 포함하므로, GSC 제출만으로 대량 크롤이 시작된다.

## 2) 네이버 서치어드바이저 (필수)

1. https://searchadvisor.naver.com 접속 → 사이트 등록 `https://seogarok.com`
2. 소유 확인: **HTML meta 태그** 방식 (이미 `<meta name="naver-site-verification" ...>` 심어둠) → "확인" 클릭
3. **요청 → 사이트맵 제출** → `https://seogarok.com/sitemap-index.xml`
4. **요청 → 웹페이지 수집** → 홈/대표 책 URL
5. **검증 → robots.txt** 확인 (`Yeti` 허용)
6. 색인 반영은 보통 3일~2주

## 3) Bing Webmaster Tools (권장)

1. https://www.bing.com/webmasters → 사이트 추가
2. GSC에서 가져오기(Import) 또는 URL/메타 인증
3. Sitemaps 제출 `https://seogarok.com/sitemap-index.xml`
4. IndexNow 자동 제출이 배포마다 동작 (`scripts/submit_indexnow.py`)

## 4) Daum(카카오) 검색

- https://search.daum.net/register (또는 카카오 검색등록)에서 사이트/페이지 등록
- Daum은 자체 크롤러(Daumoa)의 수집 주기가 길어 1~4주 소요

## 5) www 도메인 (권장)

- DNS에 `www.seogarok.com` CNAME → Cloud Run 매핑 대상 추가
- 없으면 `www`로 들어온 사용자/봇은 실패 → 대표 도메인을 `https://seogarok.com`으로 통일 (canonical 이미 https)

## 6) 색인 촉진 팁

- **콘텐츠 고유성**: 책 랜딩 5,000개 + 컬렉션·타임라인·랭킹 페이지 (이미 있음)
- **내부 링크**: 홈 → 책 랜딩 60개, 관련 책 10개씩 연결 (이미 있음)
- **외부 링크 1~2개**: GitHub README, 블로그/브런치 소개 글, 커뮤니티 공유 → 신규 도메인 신뢰도 상승
- **업데이트 신호**: 매일 랭킹/공지 갱신 (이미 자동 배포)

## 7) 확인 명령

```bash
# 구글 색인 확인 (브라우저)
site:seogarok.com
# 네이버 색인 확인
site:seogarok.com
# 봇 방문 로그
gcloud logging read 'httpRequest.userAgent:"Googlebot"' --limit 10 --freshness=1d
# IndexNow 수동 제출
python scripts/submit_indexnow.py --limit 200
```

## 예상 타임라인

| 단계 | 기간 |
| --- | --- |
| 소유확인·사이트맵 제출 | 즉시 |
| 첫 색인(홈/대표 페이지) | 2~7일 |
| 책 랜딩 대량 색인 | 1~4주 |
| 주요 키워드 노출 | 2~8주 (콘텐츠·링크에 따라) |

---

## 색인 모니터링 (자동, 2026-10-30 추가)

### 1) GSC URL Inspection API (`seo-index` 워크플로)
- 매주 월요일 09:10 KST: 홈·책 표본 30개의 **색인 verdict / 마지막 크롤**을 확인해 Actions Summary에 기록
- 준비(1회): GSC → 설정 → 사용자 및 권한 → `seogarok-api-deploy@seoga-prod.iam.gserviceaccount.com` 추가 (**전체/소유자 권한**)
- 수동 실행: `gh workflow run seo-index.yml`
- Search Console API는 활성화 완료(`searchconsole.googleapis.com`)

### 2) 사이트맵 확대
- `sitemap-books.xml`: **5,000 → 16,073+ URL** (설명 보유 책 전체)
- GSC/네이버 서치어드바이저에서 사이트맵을 다시 제출하면 새 URL까지 크롤 대상이 됨

### 3) 색인 확인
- GSC → 색인 → 페이지: 색인됨/발견됨-현재 색인 안 됨 추이
- `site:seogarok.com` (구글/네이버)
- `python scripts/gsc_index_status.py --limit 20` (로컬은 OAuth webmasters 스코프 필요, CI는 자동)

### 4) GSC 색인 모니터링 자동화 (OAuth refresh token, 1회 설정)

1. GCP Console → API 및 서비스 → 사용자 인증 정보 → **OAuth 클라이언트 ID 만들기**
   - 애플리케이션 유형: **데스크톱 앱**
   - 생성 후 Client ID / Client Secret 복사
2. `scripts/gsc_oauth_setup.py` 실행 (값은 로컬 .env에 저장)
   ```powershell
   $env:GSC_CLIENT_ID="..."
   $env:GSC_CLIENT_SECRET="..."
   python scripts/gsc_oauth_setup.py
   ```
3. GitHub Secret 등록
   ```powershell
   pwsh -NoProfile -File scripts/set_gsc_secrets.ps1
   ```
4. 테스트: `gh workflow run seo-index.yml` → Actions Summary에서 색인 verdict 확인
- 매주 월요일 09:10 KST 자동 실행
