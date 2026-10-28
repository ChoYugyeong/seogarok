# 서가(seoga) — 종료 예정 공지 수집·정규화 파이프라인

> 구독형 전자책 플랫폼에서 **"곧 종료/내려가는 작품"** 을 수집해 하나의 JSONL 스키마로 정규화한다.
> **실수집과 fixture(데모 자리표시자)를 `source_kind` 로 반드시 구분**하며, 실데이터로 위장하지 않는다.

- 실행 위치: `C:\Dev\seoga`
- 최종 산출물: [`data/notices.jsonl`](../../data/notices.jsonl) (UTF-8, 1줄 1작품)
- 최근 실행 결과: **338줄 = 실제 수집 329건(밀리의서재) + fixture 9건(리디셀렉트/교보sam/윌라)**

## 1. 실행

```powershell
cd C:\Dev\seoga

# 수집 + 보고서
python -m ingest.notices.run --out data/notices.jsonl --report

# 스키마/정규화/매칭 오프라인 self-test (네트워크 불필요)
python -m ingest.notices.run --self-test

# 옵션
python -m ingest.notices.run --report --refresh            # 원본 캐시 무시하고 재요청
python -m ingest.notices.run --report --no-fixtures        # 실수집만 출력
python -m ingest.notices.run --report --platforms millie   # 특정 플랫폼만
python -m ingest.notices.run --report --verify-blocked     # 차단 플랫폼 현재 HTTP 상태 재확인(선택)
python -m ingest.notices.run --out data/notices.jsonl --report --report-json ingest/notices/_cache/report.json
```

요청 정책(코드로 강제): 설명형 UA `seoga-research-bot/0.1 (+contact: demo)`, **요청 간격 ≥ 1초**,
robots.txt Disallow 경로 미요청, 모든 원본 응답은 `ingest/notices/_cache/` 에 저장.

## 2. 플랫폼별 조사 결과 (핵심 표)

| 플랫폼 | 공개 종료목록 | 접근 경로(URL/엔드포인트) | robots | 검증 결과(HTTP/샘플) | 구현 상태 | 법적 리스크 |
|---|---|---|---|---|---|---|
| **밀리의서재** (`millie`) | ✅ **있음** (공개 JSON API) | `GET https://live-api.millie.co.kr/v3/today/servicelimit/ebook?limit=100&page=N`<br>작품 페이지 패턴 `https://www.millie.co.kr/v4/book/{book_id}` | 200, `User-agent: *` `Allow: /`<br>(Disallow `/h4/`, `*/viewer/*` 만) · API 호스트 robots 404 | **HTTP 200 JSON**, `RESP_CD=200`, `total_count=329`, `service_limit_date` 2026-10-27~2026-11-15, **실수집 329건** | **실수집 구현 완료** | 중간 — 공개 엔드포인트이나 약관상 무단 대량수집/재배포 제한 가능. 요청 최소화·캐시·출처 표기, 장기적으로 제휴 권장 |
| **리디셀렉트** (`ridiselect`) | ❌ 비공개(차단·로그인 영역) | 고객센터가 안내하는 목록: `https://select.ridibooks.com/closing-reserved-book`<br>정책 문서: `https://ridihelp.ridibooks.com/support/solutions/articles/154000204604` (SSR 200) | **확인 불가** (robots.txt 자체가 403) | `ridibooks.com`·`book-api`·`search-api`·`select.ridibooks.com` **전부 HTTP 403 Cloudflare "Just a moment..."**. `ridiselect.ridibooks.com` 은 DNS NXDOMAIN | 차단 확인 / fixture + 제휴 API 어댑터만 | **높음** — Cloudflare 우회·로그인 필요 → 수집하지 않음(리스크 회피) |
| **교보 sam** (`sam`) | ❌ 작품별 목록 없음 (공지 게시판만 공개) | 공지: `https://ebook.kyobobook.co.kr/dig/cff/notice` (SSR),<br>공지예시 `.../notice/100865`, 작품상세 `https://ebook-product.kyobobook.co.kr/dig/epd/sam/{id}` | 200 `Allow: /` (`sam.kyobobook.co.kr/robots.txt`, `ebook.kyobobook.co.kr/robots.txt`) | 공지게시판 **200**("서비스 일시 중지 안내" 등 파싱), 작품상세 **200**이나 **종료일 필드 없음** → 종료 데이터 0건 | 공지 접근 확인 / fixture + 어댑터만 | 낮음(공개 페이지 열람) — 작품별 종료일 데이터는 비공개 영역 |
| **윌라** (`willa`) | ❌ 없음 / 차단 | 실제 도메인은 `willa.co.kr` 이 아니라 **`https://www.welaaa.com/`** (`/ebook`, `/support/notice/286`) | **확인 불가** (403 WAF) | `www.welaaa.com` **전 경로 HTTP 403** — 자체 "Access Denied by Security Engine"; `api.welaaa.com`/`wapi.welaaa.com` DNS만 존재(HTTPS connect timeout); `willa.co.kr` DNS NXDOMAIN | 차단 확인 / fixture + 어댑터만 | 중간 — WAF 차단, 우회 금지 |
| **크레마클럽** (`crema`) | ❌ 없음 | 공지: `https://cremaclub.yes24.com/BookClub/Notice` (SSR),<br>상세: `https://cremaclub.yes24.com/BookClub/Detail/{goodsId}` | 200, `/MyPage/`·`/Member/`·`/Goods/`·`/Help/` 등 Disallow (공지·상세 경로는 허용) | 공지 **200**(최근 24건 파싱, "종료 예정 도서" 공지 없음), 상세 **200**(종료일 필드 없음) | 공지 접근 확인 / fixture 0 + 어댑터만 | 낮음(공개 페이지) — 종료 데이터 자체가 비공개/미제공 |

**요약 한 줄**: 제휴 없이 **지금 실제로 수집 가능한 것은 밀리의서재 1곳(329건)**.
나머지 4곳은 (a) 봇 차단(리디·윌라), (b) 공개 종료 예정 목록 미제공(교보 sam·크레마클럽) 이라
**추측으로 채우지 않고** fixture + 제휴 API 어댑터 골격만 남겼다.

## 3. 플랫폼별 상세 근거 (검증 원문은 `ingest/notices/_cache/`)

### 3.1 밀리의서재 — 유일한 실수집 성공
- 웹 v4는 Next.js SPA지만, 공개 JS 번들(`pages/_app-*.js`)의 설정에서 API 호스트를 확인:
  `millieHost=https://www.millie.co.kr`, `phpHost=https://api.millie.co.kr`,
  `apiHost=https://live-api.millie.co.kr`, `apisHost=`, `bffHost=`, 라우트 맵
  `"/v3/today/servicelimit/:category" -> "/public/today/servicelimit/:category"` (= **종료 예정 도서**).
- `GET https://live-api.millie.co.kr/v3/today/servicelimit/ebook` → **200, 비로그인**,
  `RESP_DATA.total_count = 329`, `result[]` 20건 기본.
  각 항목: `book_seq`, `service_limit_date`(= 종료일), `book_name`, `author`, `publisher_name`,
  `book_cover_image`, `category2`(예: 매거진) 등.
- 페이지네이션 실측: `?limit=100&page=1..4` → **100 + 100 + 100 + 29 = 329건**.
  (`?page=2` 는 다른 `book_seq`부터 시작함을 확인 / `?pageNo=`·`?offset=`·카테고리 경로 세그먼트는 무시됨)
- robots: `https://www.millie.co.kr/robots.txt` → 200 `Allow: /` (Disallow `/h4/`, `*/viewer/*` 만).
  `live-api.millie.co.kr/robots.txt` → 404(정책 없음). `/viewer/*` 뷰어 경로는 수집하지 않음.
- 출력: `source_kind="notice_page"`, `confidence="high"`, `ends_at=service_limit_date`.
  `isbn13` 은 목록 API에 없어 `null` (제목/저자 매칭 사용, 필요 시 작품 상세 API로 보강 가능).

### 3.2 리디셀렉트 — 차단 (우회하지 않음)
- 고객센터 문서(SSR 200) 제목: **"[셀렉트] 서비스 종료 / 중지 작품 이용 기간"**
  본문 발췌: *"종료 예정 작품은 작품홈 내 예정일자 확인 및 기한 내 마이셀렉트에 추가할 수 있습니다"* /
  *"셀렉트 서비스 종료 예정 작품은 [셀렉트 홈 > 종료 예정 도서] 에서 확인할 수 있으며 작품 이미지를 눌러
  작품홈 내 자세한 날짜를 확인할 수 있습니다"* → **목록 URL은 `select.ridibooks.com/closing-reserved-book`**.
- 그러나 실제 요청은 **전부 HTTP 403 Cloudflare 챌린지**:
  `ridibooks.com/robots.txt`, `ridibooks.com/`, `book-api.ridibooks.com/books/...`,
  `search-api.ridibooks.com/search?q=한강`, `select.ridibooks.com/closing-reserved-book`.
  응답 title `Just a moment...` (봇 차단). `ridiselect.ridibooks.com` 은 DNS NXDOMAIN.
- 결론: robots.txt 조차 열람 불가 → **robots 준수 판단 자체가 불가능**하므로 수집하지 않는다.
  제휴 API 가 있으면 `ingest/notices/ridi.py::RidiSelectCollector.collect_from_partner_api()` 에 연결.

### 3.3 교보 sam — 공지 게시판은 공개, 작품별 종료일 목록은 없음
- `https://sam.kyobobook.co.kr/` SSR 200 (sam 상품 목록 SSR), robots 200 `Allow: /`.
- 교보eBook 공지사항 `https://ebook.kyobobook.co.kr/dig/cff/notice` SSR 200.
  샘플 공지 `.../notice/100865` → **"[sam] sam스페셜(동아사이언스) 서비스 일시 중지 안내 (~1/2)"**
  (서비스/상품 단위 공지이며 작품별 종료일 목록이 아님).
- 샘플 작품 상세 `.../dig/epd/sam/E000005221953`(구의 증명) SSR 200 — 종료 예정일 필드 없음.
- 공지 목록은 JS로 페이징되는 구조이며 현재 노출분에 "종료 예정 도서" 목록 공지 없음.

### 3.4 윌라 — 도메인 정정 + WAF 차단
- `willa.co.kr` / `www.willa.co.kr` → **DNS NXDOMAIN** (윌라 도메인이 아님).
  실제 서비스 도메인은 **`https://www.welaaa.com/`** (검색으로 확인, `/ebook` 존재).
- `www.welaaa.com` 의 `/`, `/robots.txt`, `/ebook`, `/support/notice/286` **모두 HTTP 403**,
  본문: *"보안 정책에 따라 해당 요청 처리가 거부되었습니다"* / `Access Denied by Security Engine`.
- `api.welaaa.com`, `wapi.welaaa.com` 은 DNS A 레코드만 존재하고 HTTPS connect timeout (공개 API 아님).
- 결론: WAF 우회(브라우저 위장 등) 금지 원칙에 따라 수집하지 않는다.

### 3.5 크레마클럽 — 공개 공지/상세 접근 가능하나 종료 정보 없음
- robots 200: `/MyPage/`, `/Member/`, `/Partner/`, `/Momo/`, `/Recommend/`, `/bs/`, `/Help/`,
  `/Error/`, `/Goods/`, `/GiftPick/` 등 Disallow. `BookClub/Notice`, `BookClub/Detail` 은 허용.
- `https://cremaclub.yes24.com/BookClub/Notice` SSR 200 → 최근 공지 24건 파싱
  (2026.01~2026.10, 이벤트/점검/업데이트 안내). "종료 예정 도서" 성격 공지 없음.
- `https://cremaclub.yes24.com/BookClub/Detail/198057351` SSR 200 — 종료일 필드 없음.
- 결론: 공개 종료 예정 목록 미제공. fixture 는 `data.js` 데모 카탈로그에 crema 항목이 없어 0건.

## 4. 산출물 스키마 (서버 연동 계약)

파일: `C:\Dev\seoga\data\notices.jsonl` — **UTF-8, JSON Lines, 1줄 1작품, 마지막 줄 개행**.

```json
{"platform":"millie","title":"[BL] 밤의 해","author":"그림 : 밤만득","isbn13":null,"ends_at":"2026-10-27","status":"ending","source_url":"https://live-api.millie.co.kr/v3/today/servicelimit/ebook#book_seq=9325f71a5e644f69","source_kind":"notice_page","collected_at":"2026-10-27T22:34:53+09:00","confidence":"high","raw_note":"service_limit_date=2026-10-27; book_seq=9325f71a5e644f69"}
```

| 필드 | 타입 | 규칙 |
|---|---|---|
| `platform` | string | `millie` \| `ridiselect` \| `sam` \| `willa` \| `crema` |
| `title` | string | **필수**, 비어 있으면 안 됨 |
| `author` | string \| null | 원문 표기 그대로(공동저자 포함 가능) |
| `isbn13` | string \| null | 13자리 숫자만. 밀리 목록 API 는 미제공 → null |
| `ends_at` | string \| null | `YYYY-MM-DD` (실제 달력 유효일). **fixture 는 항상 null**(날짜 날조 금지) |
| `status` | enum | `ending` \| `ended` \| `unknown` (fixture 는 `unknown` 또는 데모 표기 `ending`) |
| `source_url` | string | 근거 URL. 밀리는 API URL + `#book_seq=...` |
| `source_kind` | enum | `notice_page` \| `per_title_page` \| `search_api` \| **`fixture`** |
| `collected_at` | string | ISO8601 **timezone 포함** (`+09:00`) |
| `confidence` | enum | `high` \| `medium` \| `low` (fixture 는 항상 `low`) |
| `raw_note` | string | ≤120자 원문 발췌/근거 메모 |

**서버가 반드시 지킬 것**
1. `source_kind === "fixture"` 행은 **데모 자리표시자**다. 실서비스 노출 시 필터링하거나 UI에 "데모" 표기.
2. `ends_at === null` 은 "종료일 미확인"이지 "종료 없음"이 아니다.
3. 중복 제거 키 추천: `platform + source_url`(실수집) / `platform + title + ends_at`(표시용).
4. `collected_at` 은 수집 시각(+09:00). 파일은 `run.py` 가 `platform` → `ends_at` 오름차순 정렬(미정 null 은 뒤).

**읽기 예시 (서버)**

```python
# Python (server/api.py 등)
import json
from pathlib import Path

NOTICES_PATH = Path(r"C:\Dev\seoga\data\notices.jsonl")

def load_notices(include_fixtures: bool = False):
    rows = []
    with NOTICES_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if not include_fixtures and row["source_kind"] == "fixture":
                continue
            rows.append(row)
    return rows
```

```javascript
// Node.js
const rows = require('node:fs').readFileSync('data/notices.jsonl', 'utf8')
  .split('\n').filter(Boolean).map((line) => JSON.parse(line))
  .filter((row) => row.source_kind !== 'fixture');
```

같은 디렉터리의 `data/seed_catalog.jsonl`, `data/seoga.db`, `ingest/books/` 는 **다른 에이전트 산출물**이며
이 파이프라인은 읽지도 쓰지도 않는다(이 파이프라인의 쓰기 범위: `ingest/notices/`, `data/notices.jsonl`).

## 5. 매칭 유틸 (`match.py`)

```python
from ingest.notices.match import load_data_js_catalog, match_many, normalize_title
catalog = load_data_js_catalog("data.js")          # 읽기 전용, 38권 파싱 확인
rows = match_many([{"title": "소년이 온다 (개정판)", "author": "한강 지음"}], catalog)
rows[0]["match"]  # {'book_id': 'sonyeon', 'score': 1.0, ...}
```

- 정규화: NFKC → 괄호/대괄호 내용 제거 → 부제 분리자(`-`, `:`, `—`, `|`) 이후 제거 → 판본어
  (개정판/리커버판/완역판/… )·시리즈 표기(`1권`, `Vol.06`) 제거 → 공백 정리 → 소문자.
- 저자: 역할어(지음/엮은이/옮김/역/…) 제거, 공동저자는 첫 저자 사용.
- 매칭: 제목 시퀀스 유사도 + 토큰 자카드(max) × 0.9 + 저자 일치 보너스 0.12, 임계 0.78.
- `--self-test` 가 38권 파싱, 판본/부제 변형, 오타 퍼지 매칭, fixture 안전성까지 검증한다.
- 참고: 현재 밀리 종료 예정 329건 중 `data.js` 38권과의 매칭은 1건(0.3%)이다.
  데모 카탈로그가 주류 도서라 밀리의 잡지/구작 목록과 겹치지 않기 때문이며, 실서비스에서는
  `isbn13` 보강(작품 상세 API) 또는 카탈로그 규모 확장이 필요하다.

## 6. 원본 캐시 · 재현성

```
ingest/notices/_cache/
  <sha1(url)[:12]>.<html|json|xml|txt|js>       # 원본 응답 바이트
  <sha1(url)[:12]>.….meta.json                  # url/status/content-type/fetched_at/bytes/sha1
  robots/<host>.txt                             # robots.txt 원문
```

- 같은 URL 재실행 시 캐시를 사용(요청 0회). `--refresh` 로 강제 재요청.
- 조사 재현 도구(개발 보조, 수집기 본체 아님): `ingest/notices/_research/{probe,extract,grep_ctx,next_data,js_grep}.py`
  — 모두 같은 `HttpClient`(UA/레이트리밋/robots/캐시)를 통과한다.

## 7. "제휴 없이 할 수 있는 최선" vs "제휴가 필요한 부분"

### 제휴 없이 할 수 있는 최선 (현재 구현됨)
1. **밀리 종료 예정 도서 전체 목록 실수집** — 공개 JSON API, 329건, 종료일 포함. 하루 1회면 충분(전체 4~5요청).
2. 교보eBook/크레마클럽 **공지 게시판 모니터링** — 향후 "종료 예정 도서 안내" 공지가 올라오면 감지 가능
   (`sam.ENDING_LIST_RE`, `crema.ENDING_RE` 로 후보 탐지, 현재 0건).
3. 리디 고객센터 **정책 문서 모니터링** — 종료 예정 도서의 "조회 경로" 변경 여부 감지
   (목록 자체는 비공개/차단).

### 제휴가 필요한 부분 (어댑터 골격만 존재)
| 플랫폼 | 필요한 것 | 필요한 필드 | 연결 지점 |
|---|---|---|---|
| 리디셀렉트 | "셀렉트 종료 예정 도서" 목록 API 또는 제휴 피드 | `title, author, isbn13, end_date, book_url, updated_at` | `ridi.py::RidiSelectCollector.collect_from_partner_api()` |
| 교보 sam | 작품별 sam 서비스 종료일 (목록/상세 API) | 위와 동일 + `sam_service_end_date` | `sam.py::SamCollector.collect_from_partner_api()` |
| 윌라 | 종료 예정 작품 목록 API | 위와 동일 + `end_date` | `willa.py::WillaCollector.collect_from_partner_api()` |
| 크레마클럽 | 종료 예정 작품 목록 API | 위와 동일 + `end_date` | `crema.py::CremaCollector.collect_from_partner_api()` |

어댑터 구현 시 지켜야 할 매핑: `ends_at=YYYY-MM-DD`, `status="ending"`,
`source_kind="notice_page"(목록) 또는 "per_title_page"(상세)`, `confidence="high"`,
`raw_note` 에 응답 필드/발췌 기록. **로그인 쿠키 재사용·결제 우회·봇 차단 우회는 금지.**

## 8. 법적/윤리 리스크 메모

- 전 플랫폼 공통: 종료 예정 정보는 **작품 메타데이터**이며 개인정보는 수집하지 않는다.
  다만 각 사 이용약관은 "자동화된 수집/재배포"를 제한할 수 있으므로, 상업적 서비스 반영 전
  robots/약관 재확인 + 출처 표기 + 제휴 협의가 안전하다.
- 리디(Cloudflare)·윌라(WAF)는 기술적 차단이 명시적 의사표시에 가깝다 → **우회 시도 자체를 하지 않았다.**
- 밀리 공개 API도 대량/고빈도 호출은 피해야 한다: 이 파이프라인은 **1일 1~2회, 전체 4~5요청** 수준을 전제로 한다.
- fixture 행은 마케팅/데모 화면에서도 "실제 종료 공지"로 표기하면 안 된다(`raw_note` 에 `FIXTURE` 명시).

## 9. 파일 구조

```
ingest/notices/
  __init__.py
  base.py        # 표준 스키마(Notice), HttpClient(레이트리밋/캐시/robots), Collector, fixture 헬퍼
  millie.py      # ★ 실수집 구현 (live-api servicelimit)
  ridi.py        # 차단 확인 + fixture + 제휴 어댑터
  sam.py         # 공지 게시판 공개 확인 + fixture + 제휴 어댑터
  willa.py       # WAF 차단 확인 + fixture + 제휴 어댑터
  crema.py       # 공지 공개 확인 + 제휴 어댑터
  match.py       # 제목/저자/ISBN 정규화 + data.js 카탈로그 퍼지 매칭
  run.py         # CLI(--report/--self-test/--no-fixtures/--refresh/--verify-blocked)
  README.md      # 이 문서
  _cache/        # 원본 응답 캐시(재현성)
  _research/     # 조사 스크립트(probe/extract/grep_ctx/next_data/js_grep)
data/notices.jsonl   # 최종 산출물
```

## 10. 마지막 검증 결과 (2026-10-27)

```
python -m ingest.notices.run --out data/notices.jsonl --report
  → TOTAL lines=338  real=329  fixture=9
  → millie 329(실수집) / ridiselect 3(fixture) / sam 3(fixture) / willa 3(fixture) / crema 0
python -m ingest.notices.run --self-test
  → SELFTEST pass=22 fail=0  (schema/jsonl/정규화/매칭/fixture/수집기 계약/HTTP 정책/산출물 스키마)
```
