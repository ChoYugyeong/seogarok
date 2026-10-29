# 검색 색인 등록 런북 (Google Search Console · 네이버 서치어드바이저)

목표: `/book/{id}` 5,000여 페이지와 홈/컬렉션/장르 페이지가 검색에 노출되도록 등록하고,
1~2주 뒤 색인 추이를 확인한다.

## 준비된 것 (개발 완료)

- `https://seogarok.com/sitemap.xml` — 홈·소개·법적고지·컬렉션 4·장르 10
- `https://seogarok.com/sitemap-books.xml` — 책 5,000권 랜딩
- 각 책 페이지: 서버 렌더 HTML + Book/Breadcrumb JSON-LD + OG/Twitter + canonical
- `/books?page=N` — 크롤 그래프용 책 목록(페이지당 60권, 내부 링크)
- `robots.txt` 에 두 사이트맵 명시
- 주간 `seo-health` 워크플로: robots/sitemaps/책 랜딩/내부 링크 생존 확인

## 1) Google Search Console

1. https://search.google.com/search-console 접속 → **도메인** 속성 추가: `seogarok.com`
   - DNS TXT 레코드로 소유 확인(도메인 DNS 관리 콘솔에서 TXT 추가)
   - 또는 **URL 접두어** 속성(`https://seogarok.com/`) → HTML 파일/메타 태그로 확인
2. **Sitemaps** 메뉴에서 아래 두 개 제출
   - `sitemap.xml`
   - `sitemap-books.xml`
3. **URL 검사**로 아래 샘플 색인 요청(하루 몇 건 제한 있음)
   - `https://seogarok.com/`
   - `https://seogarok.com/books?page=1`
   - `https://seogarok.com/book/yes24%3A197068949`
4. 1주 뒤 **페이지 색인 생성** 리포트에서 색인/제외 사유 확인
   - 제외 사유가 `수집됨-현재 색인 생성 안 됨`이면 내부 링크·콘텐츠 고유성 점검

## 2) 네이버 서치어드바이저

1. https://searchadvisor.naver.com 접속 → 사이트 등록: `https://seogarok.com`
2. 소유 확인(HTML 메타 태그 또는 파일 업로드)
   - 메타 태그 방식을 쓰면 `index.html`의 `<head>`에 아래를 추가:
     ```html
     <meta name="naver-site-verification" content="발급받은_토큰" />
     ```
   - 파일 방식이면 `seogarok-xxxx.html`을 저장소 루트에 추가(정적 서빙됨)
3. **요청 > 사이트맵 제출**에서 `sitemap.xml`, `sitemap-books.xml` 제출
4. **보고서 > 색인**에서 색인 반영 수 확인

## 3) 1~2주 추이 확인 (체크리스트)

| 시점 | 확인 항목 | 방법 |
| --- | --- | --- |
| D+2 | 사이트맵 인식 | GSC Sitemaps 상태 "성공" / 네이버 사이트맵 리포트 |
| D+3~5 | 첫 색인 | `site:seogarok.com` 검색(구글·네이버) |
| D+7 | 색인 페이지 수·제외 사유 | GSC 페이지 색인 생성 리포트 |
| D+14 | 유입 검색어·노출/클릭 | GSC 실적(Performance) 리포트 |

## 4) 자동 모니터링

- `seo-health` 워크플로(매주 월 09:00 KST): 사이트맵/책 랜딩/내부 링크가 200인지 자동 확인
- 한 번이라도 `robots.txt` 200/사이트맵 접근 불가가 되면 Actions 실패 → 즉시 대응

## 5) 주의

- sitemap-books.xml 은 현재 5,000권 상한. 색인 확장 시 `handle_sitemap_books`의 LIMIT과
  `/books` 페이지네이션을 늘린다(권장: 10,000~20,000).
- 책 페이지의 가용성 정보는 실시간 데이터(공지)이므로 `Cache-Control: public, max-age=300` 유지.
- 검증 토큰은 저장소에 커밋되므로 비밀값이 아니다(공개되어도 무방).
