# `ingest/books` — 서가록(seogarok) 실도서 카탈로그 수집 (리서치 모드)

알라딘 공식 OpenAPI(TTBKey 만료) 대신 **공개 목록 HTML**에서 실제 도서 메타데이터를 수집해
`data/catalog.jsonl` (1줄 1권, UTF-8)을 만든다. 모든 요청은 `robots.txt` 판정 → 1.2초 간격 →
원본 HTML 캐시 순서를 지킨다.

## 1. robots.txt 판정 (2026-10-27 실측)

### 알라딘 — **수집 금지 (fallback `Disallow: /`)**
- URL: https://www.aladin.co.kr/robots.txt → HTTP 200, 5,098 bytes, Last Updated 2026-10-13
- 그룹 구성: Tier1 AI검색봇(`Allow: /`, Crawl-delay 3) / Tier2 검색엔진(`Allow: /`, Crawl-delay 5) /
  Tier3·4·5(GPTBot·ClaudeBot·Scrapy 등 `Disallow: /`) / **Fallback `User-agent: *` → `Disallow: /`**
- 우리 UA `seoga-research-bot/0.1 (+demo; contact: local)`는 명명 그룹에 매칭되지 않아
  **fallback `*` 그룹 적용 → 모든 경로 Disallow**.
- 따라서 알라딘 `/shop/**` 요청은 **0건**이며, `aladin_html.py` 파서는 캐시 샘플
  (`_qa/probe/aladin_best.html`, 361KB → 50권 파싱 검증)로만 보존한다.
  `run.py --source aladin` 은 `--allow-disallowed` 를 명시하지 않으면 **즉시 거부(exit 3)** 한다.
  (제휴/TTBKey 확보 등 정당한 수집 권한이 생겼을 때만 사용)

### 교보문고 — robots Allow 이지만 **SPA라 HTML 수집 불가**
- https://www.kyobobook.co.kr/robots.txt → `User-Agent: * / Allow: /` (Disallow: `/api/gw`, `/private/`)
- 그러나 `https://product.kyobobook.co.kr/bestseller/total?page=1` 응답(HTTP 200, 176KB)은
  Next.js 클라이언트 렌더링 셸로 **상품 데이터 0건**(`goodsCode`/`S000`/`/detail/S` 토큰 없음,
  `self.__next_f` RSC 스트림만 존재). 상품 목록은 `/api/gw` 계열(robots Disallow)에서 로드된다.
  → HTML만으로는 수집 불가. **우회하지 않음.**

### 예스24 — robots Allow → **실제 사용 소스**
- https://www.yes24.com/robots.txt → HTTP 200, `User-agent: *` + 개별 Disallow 목록
  (`/*.pdf$`, `/templates/`, `/member/`, `/common/`, `/goods/`, `/product/goods/JsonGoodsList`,
  `/searchCenter/searchResult.aspx`, `/24/category/bestsellerExcel`,
  `/24/Category/CategoryNavBarNew/`, `/product/category/display/018` 등).
  전면 `Disallow: /` 가 아니며, 우리가 쓰는 목록·상세 경로는 **허용**이다.
- 사용 경로만: `/product/category/bestseller?...`, `/Product/Goods/<no>`, `/robots.txt`.
  Disallow 경로는 `fetch_base.RobotsPolicy` 가 **요청 전에 차단**한다.
- 목록/상세 모두 **서버사이드 렌더링(SSR)** 이라 HTML 파싱만으로 메타데이터가 나온다.

## 2. 수집 범위 / 결과

| 항목 | 값 |
|---|---|
| 소스 | 예스24 공개 카테고리 베스트 목록 (SSR) |
| 카테고리 | 상위 장르 24개 코드 목록(`001` 종합 + 23개 장르: 소설/시/희곡, 에세이, 인문, 자연과학, 자기계발, 경제경영, 역사, 예술, 여행, 청소년, 어린이, 유아, 사회 정치, 인물, 종교, 건강 취미, 가정 살림, IT 모바일, 국어 외국어 사전, 만화/라이트노벨, 대학교재, 수험서 자격증, 잡지) 중 **21개 수집** (목표 도달로 대학교재·잡지 미수집) |
| 페이지 | 카테고리당 1~2페이지 × `pageSize=120` |
| 요청 간격 | **1.2초** (`--min-interval`, 네트워크 요청에만 적용, 캐시 히트는 제외) |
| User-Agent | `seoga-research-bot/0.1 (+demo; contact: local)` |
| 원본 캐시 | `ingest/books/_cache/<sha1(url)>.html` + `.meta.json` (재실행 시 재요청 금지) |
| 상세 보강 | 상위 200권: `isbn13`, `description`, 카테고리 세분류, 발행일 정밀화 |
| 산출물 | `data/catalog.jsonl` (UTF-8, 1줄 1권) |

최신 실행 수치·카테고리 분포는 `_research/run_report.txt`, `_research/verify_report.txt` 참조.

### 실제 수집 결과 (2026-10-27 실행)

| 항목 | 값 |
|---|---|
| **최종 행 수** | **4,021권** (`data/catalog.jsonl`, 2.47MB, UTF-8/BOM 없음) |
| 목록 페이지 | 21개 카테고리 × 1~2페이지 = **40페이지** (pageSize=120, `pageNumber`로 페이지 분리, 페이지 간 상품 겹침 0 확인) |
| 상세 페이지 | 상위 **200권** (ISBN13 200건, 책소개 190건 보강) |
| 네트워크 요청 | 최초 수집 **228회** + 상세 200회 포함 / 소요 **295.9초** |
| 캐시 재실행 | 요청 **0회**, 캐시 히트 242회, **50초** (같은 페이지 재요청 금지 검증됨) |
| 결측률 | title 0% · cover_url 0% · author 0% · publisher 0% · pubdate 0% · price 0% |
| 중복 | id 0 · item_code 0 · title+author 0 |
| 카테고리 분포(2단계) | 종교 233 · 에세이 231 · 어린이 230 · 유아 229 · 자연과학 227 · 소설/시/희곡 226 · 예술 225 · 국어/외국어사전 223 · 여행 217 · 역사 214 · 인문 208 · 가정살림 208 · 청소년 204 · 경제경영 199 · IT모바일 195 · 자기계발 193 · 사회정치 167 · 건강취미 153 · 만화 118 · 인물 66 · 종합 40 · 수험서 15 |
| 한글 정상성 | title 한글 99.6%(4005/4021) · author 한글 100%(4020/4021) · cover_url https 100% · 모지바케 0 |

검증 산출물: `_research/verify_report.txt`(행수/결측/중복/분포/샘플 5권/수용기준 판정),
`_research/sample_check.txt`(샘플 3줄 원문 + 한글 확인), `_research/defensive_tests.txt`(22/22 PASS),
`_research/offline_validation.txt`(캐시 HTML만으로 파서 검증), `_research/run_report.txt`(실행 로그).

## 3. 출력 스키마

```json
{"id":"yes24:197068949","source":"yes24_html","title":"가호","subtitle":null,
 "author":"무라카미 하루키 저/ 홍은주 역","publisher":"문학동네","pubdate":"2026-10-21",
 "isbn13":"9791141691370","item_code":"197068949","price":16650,"price_list":18500,
 "rating":9.1,"cover_url":"https://image.yes24.com/goods/197068949/L",
 "link":"https://www.yes24.com/Product/Goods/197068949",
 "category":"국내도서>소설/시/희곡>일본소설>일본 장편소설","description":"...",
 "collected_at":"2026-10-27T22:34:12+09:00"}
```

- `id`/`title` 필수. `source`는 실제 수집 소스를 정직하게 표기(`yes24_html`).
- `item_code` = 예스24 상품번호. `price`=판매가, `price_list`=정가, `rating`=10점 만점 별점.
- `pubdate`는 목록의 `2026년 10월` → `YYYY-MM-01`, 상세 보강 시 정확한 일자로 대체.
- `isbn13`/`description`은 **상세페이지에서 확인된 경우에만** 채우고, 없으면 `null` (**날조 금지**).
- 중복 제거: ① `id`(상품번호) ② 정규화 `title+author`. `[전자책]`/`[중고]` 등 비종이책 항목은 제외.

## 4. 실행

```bash
cd C:\Dev\seoga

# 기본: 예스24 수집 (목표 2000, 상위 200권 상세 보강)
python -m ingest.books.run --out data/catalog.jsonl --target 2000

# 실제 사용한 명령 (카테고리 커버리지 확대 + 3000권 내외)
python -m ingest.books.run --out data/catalog.jsonl --target 4000 --pages-per-cat 2 --detail-top 200 --min-interval 1.2

# 검증 리포트 (행 수/결측률/중복/카테고리 분포/샘플)
python -m ingest.books.verify --file data/catalog.jsonl --report ingest/books/_research/verify_report.txt
```

- 알라딘(비활성): `python -m ingest.books.run --source aladin --out ...` → `--allow-disallowed` 없으면
  robots 근거를 `_research/run_report_robots_blocked.txt` 에 남기고 **exit 3**.
- 페이지 구조가 바뀌면 파서는 예외 없이 `[]` 를 반환하고, 러너는 경고 후 0건(exit 4)으로 종료한다.

## 5. 파일 구조

```
ingest/books/
├── __init__.py
├── fetch_base.py    # robots.txt 판정(RFC9309) / 인코딩 판별 / 1.2s 레이트리밋 / 원본 HTML 캐시
├── yes24_html.py    # 예스24 목록·상세 SSR 파서 (사용 중)
├── aladin_html.py   # 알라딘 파서 (robots Disallow → --allow-disallowed 없이는 비활성)
├── run.py           # CLI: 크롤 + 상세 보강 + JSONL 기록 + run_report
├── verify.py        # 검증 리포트(UTF-8) 생성
├── _cache/          # 원본 HTML + meta (재요청 금지 캐시), run_report.json
└── _research/       # 조사/검증 산출물 (robots 원문, 오프라인 파싱 검증, 최종 리포트)
```

## 6. 한계 / 리스크

- **ISBN13·책소개는 상위 200권만** 채워져 있다 → `isbn13` 결측률 95.03%, `description` 결측률 95.27%.
  전체 보강은 상세페이지 1권당 1요청 + 1.2초 간격이라 4,021권이면 약 80분이 더 필요하다
  (`--detail-top 4021` 로 재실행하면 되고, 이미 받은 상세페이지는 캐시에서 재사용된다).
- 별점이 없는 신간은 `rating: null` → 결측률 9.18%. `cover_url` 결측 0%(Noimg 0건).
- `subtitle`은 목록/상세에 별도 필드가 없어 전부 `null` (날조 금지).
- 카테고리 문자열은 예스24 분류 체계(`국내도서>소설/시/희곡>일본소설`)를 그대로 쓴다.
  상세 보강분은 3~4단계, 미보강분은 2단계(`국내도서>장르`)까지이다.
- **법적 리스크**: robots.txt 준수는 기술적 예의일 뿐, 상업적 재배포는 각 서점
  **이용약관/저작권/데이터베이스권**에 별도로 저촉될 수 있다. 운영 서비스에 쓰려면
  **알라딘·예스24 등과의 제휴(또는 공식 API 라이선스)** 가 필요하다. 본 수집물은 데모/리서치 용도다.
- 알라딘 OpenAPI는 TTBKey 만료, Google Books API는 익명 쿼터 0(HTTP 429)으로 사용 불가였다.
- 알라딘 파서(`aladin_html.py`)는 **캐시 샘플(`_qa/probe/aladin_best.html`, 361KB → 50권 파싱)** 로만
  검증했고, 상세페이지 파서는 샘플이 없어 미검증이다(제휴 확보 후 재검증 필요).
