# 서가(seoga) SRE 운영 문서

> **이 문서가 답하는 질문:** ① 서가의 SLI/SLO는 무엇이고 어떻게 측정하는가? ② 장애 시 어떤 순서로 진단·복구하고 누가 무엇을 보는가? ③ 이 구조는 어디까지 확장되고 무엇이 한계인가?

읽는 사람을 위한 안내: **5분**이면 §1–§5로 "무엇을 어떻게 운영하는지"를 판단할 수 있고, 상세 진단 절차는 [runbooks/](runbooks/)에 있다. 실제 사고 1건은 [postmortem/2026-10-27-index-stale.md](postmortem/2026-10-27-index-stale.md)에 정리했다.

---

## 1. 한눈에 보기

| 항목 | 내용 |
|---|---|
| 서비스 | 한국어 도서 검색 API + 정적 SPA (`server/api.py`, Python 3.12 표준 라이브러리 HTTP 서버) |
| 검색 | SQLite FTS5(BM25) + sqlite-vec(KNN) 하이브리드, RRF 융합 + field boost + exact-first |
| 인덱스 | 로컬 개발 **4,865권** / 컨테이너 이미지 **500권 샘플**(저장소에는 샘플만 커밋) |
| 실행 | `docker compose` 4개 서비스: `api`(8100), `prometheus`(9090), `grafana`(3001), `k6`(profile `load`) |
| 관측 | `/healthz`, `/readyz`, `/metrics`(Prometheus 텍스트), stdout JSON 로그 1줄/요청 |
| SLO | 가용성 99.9%/30일, 검색 p95 < 300ms, 에러율 < 1%, 인덱스 신선도 < 24h |
| 운영 진입점 | [`Makefile`](../Makefile) — `make up / smoke / load / chaos / reset-chaos / dash / logs / ps / down / test` |
| 알림 | Prometheus 7개 규칙([alerts.yml](../observability/prometheus/alerts.yml)) → 런북 링크 내장 |
| CI | GitHub Actions 3 job([ci.yml](../.github/workflows/ci.yml)): 오프라인 테스트, 이미지 빌드+Trivy, compose 스모크 |

**이 환경의 인덱스 크기 구분 (문서 전체에서 혼동 방지):**

- 로컬 개발: `python -m server.sync`로 **4,865권** 전체 인덱스. 아래 §9의 인프로세스 벤치마크 수치는 이 기준이다.
- 컨테이너: [`Dockerfile`](../Dockerfile)이 빌드 시 `data/catalog.jsonl`(**예스24 Open API 수집분, 4,865권**)로 인덱스를 구워 이미지에 포함한다. 데이터는 커밋하지 않고(gitignore) CI/로컬에서 Key 로 수집한다. API Key 가 없으면 38권 seed 로 폴백하므로 `make up`/compose 스모크의 문서 수는 수집분에 따라 달라진다(스모크는 `>0` 만 확인).
- 부하테스트(k6) 결과는 §9.3·§12에 실측으로 정리했다 (p95 4.10ms / 실패율 0%).

---

## 2. 아키텍처

```
                        ┌──────────────────────────────────────────────────┐
   browser / k6 ───────▶│  api :8100  (server/api.py, ThreadingHTTPServer) │
   curl / runbook       │                                                  │
                        │   ops:  /healthz   /readyz   /metrics            │
                        │   app:  /api/search  /api/book  /api/notices ... │
                        │   drill: POST /api/_chaos   (SEOG_CHAOS=1 일 때)  │
                        └───────────────┬──────────────────────────────────┘
                                        │ SQL (WAL)
                        ┌───────────────▼──────────────────────────────────┐
                        │  /tmp/data/seoga.db  (tmpfs)                     │
                        │   books / books_fts(FTS5) / vec_books(sqlite-vec)│
                        │   notices / availability / meta                  │
                        └───────────────▲──────────────────────────────────┘
                                        │ 이미지 빌드 시 1회 생성된 DB를 복사
                        ┌───────────────┴──────────────────────────────────┐
                        │  이미지 레이어(읽기 전용): data/seoga.db + 임베딩  │
                        └──────────────────────────────────────────────────┘

   prometheus :9090 ── scrape api:8100/metrics (5s) ──▶ rules: alerts.yml
          │
          ├──▶ grafana :3001  (admin/admin, 익명 Viewer, dashboard uid=seoga-sre)
          └──▶ /alerts  (게임데이·런북에서 확인)
```

**Immutable artifact 패턴** — [`Dockerfile`](../Dockerfile) + [`scripts/docker-entrypoint.sh`](../scripts/docker-entrypoint.sh):

1. 빌드 단계에서 `pip install`, 임베딩 모델 고정(`minishlab/potion-multilingual-128M`), `python -m server.sync`로 인덱스 생성.
2. 런타임 이미지는 인덱스 DB를 레이어에 포함하고, 엔트리포인트가 `data/seoga.db` → `/tmp/data/seoga.db`(tmpfs)로 복사한 뒤 API를 띄운다.
3. 컨테이너는 `read_only: true` + `tmpfs /tmp` + `cap_drop: ALL` + `no-new-privileges`로 동작한다. SQLite는 WAL 쓰기가 필요하므로 쓰기 가능한 곳을 `/tmp`로 격리한 것이다.
4. 결과: **런타임에 인덱스를 다시 만드는 경로가 없다** → 재색인 stale 사고(§11)의 구조적 재발 방지. 롤백도 이미지 태그 교체로 단순해진다.

**요청 흐름(`GET /api/search?q=&mode=hybrid|keyword|vector`)**

1. `route_of(path)`로 라벨용 route를 정규화(`/api/search`).
2. 카오스가 켜져 있으면 지연/확률 오류를 주입(운영 엔드포인트 4종은 제외).
3. 키워드 경로: 한글 bigram FTS5 MATCH → BM25 순위.
4. 벡터 경로: model2vec 256d 임베딩 → sqlite-vec KNN.
5. 융합: 정확 일치가 있으면 exact-first, 없으면 RRF + field boost.
6. 응답에 `took_ms`, `stage_ms{keyword,vector,fuse}`, `strategy`를 포함.
7. `METRICS.observe_search(mode, strategy, stage_seconds)` + 요청 히스토그램/카운터 기록, stdout JSON 로그 1줄.

---

## 3. 관측성 설계

### 3.1 RED 메트릭 (구현: [`server/metrics.py`](../server/metrics.py), 계측: [`server/api.py`](../server/api.py))

| 메트릭 | 타입 | 라벨 | 의미 / 사용처 |
|---|---|---|---|
| `seoga_http_requests_total` | counter | `method, route, status` | Rate·Errors. 가용성 SLI, 에러율, burn-rate 알림 |
| `seoga_http_request_duration_seconds` | histogram | `route` | Duration. p95/p99, `SeogaSearchLatencyP95High` |
| `seoga_http_in_flight` | gauge | – | 동시 처리 요청 수, 포화 판단 |
| `seoga_search_queries_total` | counter | `mode, strategy` | 트래픽 구성(hybrid/keyword/vector × exact-first/rrf/vector-only) |
| `seoga_search_stage_seconds_sum` / `_count` | summary | `stage=keyword\|vector\|fuse` | 어느 단계가 느린지 분해 |
| `seoga_index_documents` | gauge | – | 실 DB 문서 수. 인덱스 신선도/비어있음 알림 |
| `seoga_index_vectors` | gauge | – | 실 벡터 수. `documents == vectors` 무결성 확인 |
| `seoga_notices_total` | gauge | – | 적재된 종료 예정 공지 수 |
| `seoga_index_age_seconds` | gauge | – | 마지막 sync 이후 경과. 24h 초과 시 `SeogaIndexStale` |
| `seoga_db_size_bytes` | gauge | – | SQLite 파일 크기, 인덱스 비대 감지 |
| `seoga_ready` | gauge | – | readiness 결과(1/0). `/readyz`와 동일 판정 |
| `seoga_build_info` | gauge | `version, embed, vector` | 빌드/임베딩/벡터 백엔드 식별자. 항상 `1` |

게이지는 `/metrics` 스크레이프 시점에 DB에서 실제 값을 다시 읽어 갱신한다(스크레이프가 실패해도 응답은 유지되고, 갱신 실패는 `metrics_gauge_refresh_failed` warn 로그로 남는다).

> 위 표의 **12계열**은 노출되는 시리즈 이름으로는 **15종**이다(히스토그램 `_bucket/_sum/_count`, summary `_sum/_count` 포함). 이 밖에 `/metrics` 렌더 자체의 소요를 재는 `seoga_scrape_duration_seconds`가 추가로 노출된다.

### 3.2 운영 엔드포인트

| 엔드포인트 | 의미 | 응답/상태 | 비고 |
|---|---|---|---|
| `GET /healthz` | liveness | 항상 `200` (`ok, version, uptime_s`) | 의존성 확인 안 함. 프로세스만 살아있으면 성공 |
| `GET /readyz` | readiness | `200` + `{ready:true, documents, vectors, embed, index_backend}` / 조건 미충족 시 **503** | **DB에서 실제 count를 읽어** `documents > 0 && vectors > 0 && documents == vectors` 판정. 메타 캐시를 믿지 않는다 |
| `GET /metrics` | Prometheus scrape | `200`, `text/plain; version=0.0.4` | 카오스 주입 제외 |
| `POST /api/_chaos` | 장애 주입(게임데이) | `SEOG_CHAOS=1`이면 `200` + 현재 상태 / 아니면 **404** | `{"latency_ms":400,"error_rate":0.3}`. GET으로 현재 상태 조회 |
| `GET /api/health` | 기존 상세 헬스 | `200` (`books, notices, embed_backend, embed_dim, vector_backend, synced_at, mode`) | **부팅 시 메타 캐시**. 재색인 후에는 재기동 전까지 옛 값을 보여준다(§11 사고의 원인) |

**왜 `/healthz`와 `/readyz`를 분리했나:** liveness 실패는 "프로세스를 재시작해야 함", readiness 실패는 "트래픽을 보내면 안 됨(인덱스 미준비)"을 뜻한다. `readyz`가 `documents == vectors`를 실제로 비교하기 때문에, 재색인 중이거나 벡터 적재가 깨진 인스턴스는 트래픽에서 빠진다.

**카오스에서 제외되는 경로 4개:** `/metrics`, `/healthz`, `/readyz`, `/api/_chaos`. 장애 주입 중에도 관측과 복구 명령은 정상 동작해야 하기 때문이다. 대신 `/api/health`는 제외 대상이 아니므로 게임데이 동안 지연/오류가 주입된다.

### 3.3 로그 (stdout JSON 1줄/요청)

컨테이너 표준출력으로 JSON 한 줄을 남긴다. 로그 수집기(예: Loki/Fluent Bit)가 파싱하기 쉬운 형태이며, 요청 ID로 API 응답 헤더 `X-Request-Id`와 상호 참조가 가능하다.

```json
{"ts":"<ISO8601>","level":"info|error","req_id":"<12hex>","method":"GET","path":"/api/search","route":"/api/search","status":200,"dur_ms":<number>,"ua":"<최대 80자>"}
```

에러 응답(5xx)은 같은 필드에 `level:"error"`. 카오스 주입은 `chaos_set` warn 로그로 남겨, 게임데이/실장애를 로그만으로 구분할 수 있다.

### 3.4 라벨 카디널리티

- route는 `_ROUTES`로 정규화한 10개(`/api/search`, `/api/book`, `/api/notices`, `/api/stats`, `/api/suggest`, `/api/health`, `/api/_chaos`, `/healthz`, `/readyz`, `/metrics`)와 fallback(`/api/other`, `/static`, `/`)만 사용한다.
- **경로 원문·질의어(`q`)·책 ID·req_id는 라벨로 쓰지 않는다.** 카디널리티 폭발은 Prometheus TSDB를 죽이는 가장 흔한 실수다. req_id는 로그/헤더로만 상관관계를 만든다.
- status는 숫자 코드, mode 3종, strategy 3종, stage 3종으로 유한하다.
- `seoga_http_requests_total`은 route × method × status 조합으로 증가하지만 상한이 구조적으로 제한된다.

### 3.5 로그·메트릭 비용

- `/metrics` 스크레이프는 5초마다 문서 수/벡터 수/공지 수 count를 실행한다. 현재 규모(4,865권/500권)에서는 무시할 수준이지만, 100만 권 규모로 가면 count 쿼리를 캐시하거나 `sweep` 주기로 분리해야 한다(§10 한계).
- 요청 로그는 1줄/요청이며 `dur_ms`를 포함해, 메트릭에서 놓친 개별 요청의 p99 이상치를 사후 추적할 수 있다.

---

## 4. SLI/SLO와 에러 버짓

### 4.1 SLO 표 (30일 롤링)

| SLI | 정의 | 측정(PromQL) | SLO | 에러 버짓(30일) |
|---|---|---|---|---|
| **가용성** | 1 − (5xx 요청 / 전체 요청) | `1 - (sum(rate(seoga_http_requests_total{status=~"5.."}[5m])) / sum(rate(seoga_http_requests_total[5m])))` | **99.9%** | **0.1% = 43분 12초** |
| **검색 지연** | `/api/search` p95 | `histogram_quantile(0.95, sum(rate(seoga_http_request_duration_seconds_bucket{route="/api/search"}[5m])) by (le))` | **p95 < 300ms** | 5분 윈도우의 1% (≈ 7시간 12분 상당) |
| **에러율** | 5xx 비율 | `sum(rate(seoga_http_requests_total{status=~"5.."}[5m])) / sum(rate(seoga_http_requests_total[5m]))` | **< 1%** | 1% = 7시간 12분 |
| **인덱스 신선도** | 마지막 sync 이후 경과 | `seoga_index_age_seconds` (임계 86,400s) | **< 24시간** | 예산 대신 "위반 0회" 목표, 10분 지속 시 경보 |

- 30일 = 43,200분. 99.9% SLO의 허용 불가 시간은 `43,200 × 0.001 = 43.2분 = **43분 12초**`.
- 가용성/지연/에러율은 5xx·지연 사용자 영향, 신선도는 "정상 응답이지만 오래된 데이터"를 잡는 SLI다. **신선도는 가용성 SLO로 잡히지 않는다** — 2026-10-27 사고가 이 사각지대에서 발생했다.

### 4.2 에러 버짓 정책 (배포 동결 규칙)

에러 버짓은 "이번 30일 동안 허용된 실패 시간"이며, 소진 속도(burn rate)로 배포를 통제한다. burn rate = 현재 에러율 ÷ SLO 허용 에러율(0.1%). 예: 실제 에러율 1% → burn rate 10x.

| 상태 | 판단 기준 | 행동 |
|---|---|---|
| 정상 | burn rate < 2x, 버짓 잔여 > 50% | 정상 배포 |
| 주의 | 버짓 잔여 25–50% | 신규 기능 배포 전 `make smoke` + 당일 변경 1건 제한 |
| **동결** | `SeogaErrorBudgetBurnFast` 발화(1h burn > 14.4x, 2분 지속) 또는 버짓 75% 소진 | **즉시 배포 중단**, 롤백 여부 판단, 인시던트 채널 공유 |
| **소진** | 버짓 100% 소진 | 배포 동결 + 포스트모템 의무, 신뢰성 작업만 허용 |

배포 전후 규칙: (1) `make test` → `make smoke` 통과 필수, (2) 배포 후 최소 30분은 Grafana `seoga · SRE Overview`(uid `seoga-sre`)의 Error ratio / p95를 관찰, (3) fast burn이 발화하면 롤백을 기본 선택으로 한다(§8 롤백, [runbooks/api-down.md](runbooks/api-down.md)).

### 4.3 멀티윈도우 멀티번레이트 알림

에러 버짓 소진은 "얼마나 빠르게" 소진하는지가 핵심이다. 서로 다른 윈도우로 **빠른 소진**과 **느린 소진**을 분리한다.

| 알림 | 윈도우/임계 | 소진 의미 | for | severity | 런북 |
|---|---|---|---|---|---|
| `SeogaErrorBudgetBurnFast` | 1시간 burn > **14.4x** (5xx 비율 > 0.0144) | 1시간에 월 버짓의 **2%** 소진 | 2m | critical | api-down |
| `SeogaErrorBudgetBurnSlow` | 6시간 burn > **6x** (5xx 비율 > 0.006) | 6시간에 월 버짓의 **5%** 소진 | 15m | warning | api-down |

- 14.4x의 유도: 30일 예산 대비 1시간 비율 `1/720`, `14.4/720 = 2%`. 6x·6시간은 `36/720 = 5%`.
- 두 단계로 나눈 이유: 1h 윈도우는 **빠른 감지**를, 6h 윈도우는 **지속성 있는 소진**을 잡는다. 단발 스파이크는 1h가 잡고, 천천히 새는 문제는 6h가 잡는다.
- 현재 구현은 각 알림이 단일 윈도우다. 표준 패턴대로라면 같은 알림에 짧은 윈도우(5m/30m)를 AND로 붙여 오탐을 줄이는 것이 다음 개선 후보다.
- 그 외 알림 5종: `SeogaApiDown`(up==0, 30s), `SeogaNotReady`(ready==0, 1m), `SeogaSearchLatencyP95High`(p95>0.3s, 2m), `SeogaIndexStale`(age>86400s, 10m), `SeogaIndexEmpty`(documents==0, 1m). 전체 정의와 임계값은 [alerts.yml](../observability/prometheus/alerts.yml)이 단일 소스다.

---

## 5. 알림 → 런북 매핑 (온콜이 가장 먼저 보는 표)

| 알림 | 첫 질문 | 런북 | 판정 기준(복구) |
|---|---|---|---|
| `SeogaApiDown` | 프로세스가 떴나? | [api-down.md](runbooks/api-down.md) | `up{job="seoga-api"}==1` + `/healthz` 200 |
| `SeogaErrorBudgetBurnFast/Slow` | 5xx의 원인이 배포인가 외부인가? | [api-down.md](runbooks/api-down.md) | 5xx 비율 정상화(알림 resolve), 롤백 여부 결정 |
| `SeogaSearchLatencyP95High` | 어느 단계(keyword/vector/fuse)가 느린가? | [slow-search.md](runbooks/slow-search.md) | p95 < 300ms로 10분 유지 |
| `SeogaNotReady` | docs/vectors 중 무엇이 0이거나 불일치인가? | [index-stale.md](runbooks/index-stale.md) | `/readyz` `ready:true`, `docs==vectors` |
| `SeogaIndexStale` / `SeogaIndexEmpty` | 인덱스가 마지막으로 언제 갱신됐나? | [index-stale.md](runbooks/index-stale.md) | `seoga_index_age_seconds` < 86400, documents > 0 |
| (게임데이) | 주입한 파라미터와 기대 알림이 맞나? | [chaos-drill.md](runbooks/chaos-drill.md) | 리셋 후 전 알림 resolve, SLO 지표 기준선 복귀 |

원칙: **알림 이름 → 런북 파일이 1:1로 연결**되어 있다. 모든 alert rule의 annotation에 `runbook:` 경로가 들어 있어, 알림을 받은 사람이 저장소에서 바로 문서를 찾는다.

---

## 6. 배포·운영 모델

| 계층 | 방식 | 링크 |
|---|---|---|
| 이미지 | 멀티스테이지 빌드, 빌드 시 인덱스/임베딩 고정(immutable) | [Dockerfile](../Dockerfile) |
| 로컬 스택 | compose 4서비스(`api`,`prometheus`,`grafana`, profile `load`의 `k6`) | [docker-compose.yml](../docker-compose.yml) |
| 운영 진입점 | Makefile 10타깃(아래 표) | [Makefile](../Makefile) |
| CI | 3 job: 오프라인 테스트 / 이미지 빌드+Trivy / compose 스모크 | [.github/workflows/ci.yml](../.github/workflows/ci.yml) |
| 관측 설정 | Prometheus rule + Grafana provisioning을 전부 코드로 관리 | [observability/](../observability/) |

| Makefile 타깃 | 실제 동작 | 서비스/엔드포인트 |
|---|---|---|
| `make up` | `docker compose up -d --build` | api:8100, prometheus:9090, grafana:3001 |
| `make ps` / `make logs` | compose 상태/로그 | 전체 서비스 |
| `make down` | `docker compose down` (볼륨 유지) | – |
| `make smoke` | 기동 대기 후 4개 경로 검증 | `/healthz`, `/readyz`, `/metrics`, `/api/search` |
| `make load` | `docker compose --profile load run --rm k6 run /scripts/search.js` | k6 → `api:8100` |
| `make chaos` / `make reset-chaos` | `POST /api/_chaos` | latency 400ms / error 0.3 주입, 0으로 리셋 |
| `make dash` | Grafana 대시보드 열기 | `http://localhost:3001/d/seoga-sre` |
| `make test` | seed 인덱스 + 오프라인 검색 단언 (Docker 불필요) | `python -m server.sync --embed hashing` |

배포 순서(컨테이너): `docker compose build api`(→ 빌드 시 500권 샘플 인덱스 생성) → `docker compose up -d api` → `make smoke` → Grafana 30분 관찰. 롤백은 이전 이미지 태그로 교체. 인덱스까지 함께 구워지므로 **데이터와 코드의 버전이 항상 일치**한다.

---

## 7. CI/CD 파이프라인

| job | 목적 | 핵심 단계 | 실패 의미 |
|---|---|---|---|
| `test` | 오프라인 회귀 | Python 3.12 + `requirements.server.txt` 설치(패키지 설치에는 PyPI 네트워크 필요, **모델 가중치 다운로드는 없음**) → `server.sync --embed hashing`(seed 38권) → 검색 단언 | 검색 파이프라인/스키마 깨짐 |
| `build` | 이미지·보안 | `docker build -t seoga-api:ci .` → **Trivy** `HIGH,CRITICAL` 발견 시 fail(`ignore-unfixed: true`) | 취약 베이스/의존성, 빌드 실패 |
| `compose-smoke` | 실제 기동 검증 | `docker compose up -d --build api prometheus` → `/healthz` 200, `/metrics`에 `seoga_index_documents 500`, `/api/search` 200 → `down -v` | compose/엔트리포인트/read-only+tmpfs 구성 회귀 |

- `permissions: contents: read` 최소 권한, `concurrency`로 같은 ref의 중복 실행 취소, job별 timeout 지정.
- 알림봇(별도 저장소의 `alertbot`) 테스트는 이 저장소 CI 범위가 아니어서 job을 만들지 않았다. (원래 계획의 `bot-test`는 저장소 경계 때문에 제외.)
- Trivy는 **이미지 스캔** 기준이며, HIGH/CRITICAL이 남아 있으면 빌드가 성공해도 job이 실패한다. `ignore-unfixed: true`는 "패치가 아직 없는 CVE"로 영구 실패하는 상황을 막기 위한 선택이다.
- CI에는 실측 부하테스트(`k6`)를 넣지 않았다. 25 VU 부하를 매 PR에 돌리면 러너 비용/노이즈가 크고, 지연 SLO 검증은 게임데이에서 한다.

---

## 8. 장애 대응 개요 (상세는 런북)

| 단계 | 질문 | 도구 |
|---|---|---|
| 1. 탐지 | 지금 사용자 영향이 있는가? | Prometheus `/alerts`, Grafana 상단 stat 5개 |
| 2. 분류 | 프로세스 문제(api-down) / 준비 실패(index-stale) / 성능 저하(slow-search) | 런북 매핑 표(§5) |
| 3. 복구 | 재시작 / 재빌드 / 카오스 리셋 / 롤백 | `make up`, `docker compose restart api`, `make reset-chaos` |
| 4. 검증 | 정상 기준선으로 돌아왔나? | `make smoke`, `/readyz`, 알림 resolve |
| 5. 기록 | 재발 방지 액션이 있는가? | [postmortem/TEMPLATE.md](postmortem/TEMPLATE.md) |

복구 기본값: 5xx가 배포 직후 시작됐으면 **롤백이 1순위**, 배포와 무관하면 **카오스 주입 여부 확인이 1순위**(2차원: 지연인지 오류인지). 롤백은 이미지 태그 교체로 끝나며 데이터 마이그레이션이 없다(인덱스가 이미지에 포함).

---

## 9. 성능 기준선과 부하테스트

### 9.1 인프로세스 기준선 (로컬 4,865권, 네트워크·HTTP 제외)

측정: `python -m benchmarks.bench_search` (결과 파일 `data/bench_report.json`, 저장소에는 미커밋). 수치는 [README](../README.md)의 "성능 (실측)" 절에 기록된 실측값이다.

| 모드 | p50 | p95 | 비고 |
|---|---|---|---|
| 키워드 (FTS5 BM25) | **0.25ms** | 1.91ms | 한글 bigram 색인 |
| 벡터 (sqlite-vec KNN) | **6.53ms** | 10.42ms | 4,865개 exact KNN + 임베딩 |
| 하이브리드 | **2.88ms** | 7.79ms | RRF + boost + 전략 판정 |

- 인덱스 구축: 4,865권 임베딩+FTS+벡터 **9.5초**.
- sqlite-vec KNN은 exact라 선형 증가: 합성 벡터 1k 0.94ms / 10k 10.1ms / 50k 48.6ms.
- 위 수치는 **함수 호출 기준**이다. SLO(HTTP p95 < 300ms)는 직렬화·큐잉·네트워크가 포함되므로 k6 결과로 판정한다(§9.2).

### 9.2 k6 시나리오 ([loadtest/search.js](../loadtest/search.js))

- 실행자: `ramping-vus` — 10s에 1→10 VU, 30s에 10→25 VU, 10s에 25→0 (warm-up/steady/ramp-down), `gracefulRampDown: 5s`.
- 질의: 10종(한강, 채식주의자, 김초엽, 우주 과학 소설, SF 소설, 따뜻한 힐링 소설, 에세이, 인공지능과 미래, 역사 교양, shakespeare)을 랜덤 선택, `limit=12`, think time 0.1–0.4s.
- 임계값(thresholds): `http_req_failed rate < 0.01`, `http_req_duration{route:search} p(95) < 300`, `p(99) < 800`, `checks rate > 0.99`.
- 실행 `make load`. 임계값을 넘기면 k6가 비-0 exit code로 종료되어 CI/게임데이에서 판정 가능.

### 9.3 부하테스트 결과 (실측)

컨테이너 이미지(500권 샘플 인덱스) + compose 스택에서 `make load` 로 측정했다.
측정 환경: Windows 11 / Docker Desktop 29.6.1 / Ryzen 5 7500F / Python 3.12.10 slim 이미지.
이미지 다이제스트·빌드 시각은 `docker images seoga-api:local --digests` 로 확인한다.

| 시나리오 | VU 최대 | 실행시간 | p50 | p95 | p99 | 실패율 | RPS | API CPU/메모리 (idle) |
|---|---|---|---|---|---|---|---|---|
| `search_ramp` (steady 25 VU) | 25 | 50s | **2.47ms** | **4.10ms** | **5.74ms** | **0.00%** (0/2,844) | **56.9** | CPU 0.02% / 1.80GiB (idle 측정) |

- 전체 요청(`/healthz` 포함) 기준: p50 2.51ms / p95 6.47ms / p99 43.78ms, 최대 47.58ms
- `checks` 통과율 **100.00%** (8,151/8,151) — status 200 · 결과 존재 · 300ms 이내
- SLO(p95 < 300ms) 대비 **약 73배 여유**

> 측정 시 반드시 함께 기록: 이미지 다이제스트/빌드 시각, 호스트 스펙, 호스트에서 동시에 돌린 작업 유무. 로컬 4,865권 인덱스와 컨테이너 500권 인덱스는 비교 대상이 아니므로 같은 표에 섞지 않는다.

---

## 10. 한계와 확장 계획

| # | 한계 | 근거 | 확장 전략 |
|---|---|---|---|
| 1 | **단일 SQLite writer** | 서빙 프로세스가 WAL 쓰기를 수행, 쓰기 1개 | 쓰기는 배치 sync로만 수행(현재 구조), 수평 확장 시 API는 read-only 복제를 열고 writer는 별도 job으로 분리 |
| 2 | exact KNN의 선형 증가 | 50k 벡터 48.6ms(측정) | 100만 규모는 IVF/HNSW(pgvector, Qdrant)로 전환. 인터페이스는 `VectorStore.search()` 한 곳 |
| 3 | 임베딩 인코딩 직렬화 | `_lock_encode`로 프로세스 내 단일 임베더 보호 | 다중 워커/복제로 확장. 인코딩은 CPU 바운드라 WSGI면 워커 프로세스, 현 구조면 복제 수평 확장 |
| 4 | 단일 프로세스 `ThreadingHTTPServer` | stdlib 서버, TLS/keepalive 최적화 부재 | 리버스 프록시 뒤로 숨기거나 gunicorn/uvicorn으로 교체 |
| 5 | **인덱스가 이미지에 고정(immutable)** | 런타임 재색인 불가, 콘텐츠 갱신 = 재빌드 | 수평 확장 시 인덱스 스냅샷(DB 파일)을 오브젝트 스토리지에 두고 배포 시 마운트/복사. 스냅샷 버전을 `seoga_build_info{version}`과 함께 기록 |
| 6 | 인덱스 신선도 게이지가 빌드 시각 기준 | `synced_at`은 이미지 빌드 시 찍힘 | 장기 실행 컨테이너에서는 24h 경보가 "배포 후 경과"를 의미할 수 있다. 운영 기준을 배포 주기와 함께 정의하거나 정기 재배포로 신선도 유지([index-stale.md](runbooks/index-stale.md) §6 참조) |
| 7 | `/api/health`가 부팅 시 메타 캐시 | 재색인 후 재기동 전 stale | **재색인 절차에 재기동을 포함**([index-stale.md](runbooks/index-stale.md)). 장기적으로 `/api/health`도 live count로 통일하는 것이 개선안 |
| 8 | 카오스 엔드포인트가 기본 활성(데모) | compose/Dockerfile `SEOG_CHAOS=1` | 운영 프로필에서는 `SEOG_CHAOS=0`으로 내리고 `/api/_chaos`가 404가 되는 것을 배포 후 확인 |

**수평 확장 시나리오(요약):** writer 1개(sync job) → read-only 복제 N개(각자 로컬 DB 파일, 주기적 스냅샷 교체) → API 무상태화 → LB 뒤로. 지연 SLI는 복제본별로 동일하게 측정하고, 신선도 SLI는 스냅샷 버전으로 추적한다. 지금의 `seoga_ready`(docs==vectors) 판정은 복제본 교체 시에도 그대로 유효하다.

---

## 11. 실제 사고로 본 설계 교훈 (요약)

2026-10-27, 카탈로그를 4,865권으로 재색인했지만 **실행 중이던 API 프로세스가 38권 시점 메타데이터를 계속 "정상"으로 노출**했다. 자동 탐지 수단이 없어 수동 대조로 발견했고, 같은 날 `/readyz` live-count 판정 + 문서 수 메트릭 + `SeogaNotReady`/`SeogaIndexStale`/`SeogaIndexEmpty` 알림 + 재색인 런북으로 재발 방지를 넣었다. 상세 타임라인과 액션 아이템은 [postmortem/2026-10-27-index-stale.md](postmortem/2026-10-27-index-stale.md).

교훈 3줄:
1. liveness(살아있음)와 readiness(최신·준비됨)는 다른 질문이다. 하나의 헬스체크로 둘을 겸하면 stale을 정상으로 보고한다.
2. 상태 엔드포인트는 캐시된 메타가 아니라 **실제 리소스에서 읽어야** 한다.
3. 재색인은 "데이터 교체 + 프로세스 교체" 2단계 연산이다. immutable 이미지로 굽는 구조가 이 실수를 원천 차단한다.

---

## 12. 실측 (측정 완료)

측정 환경: Windows 11 / Docker Desktop 29.6.1 / Ryzen 5 7500F / Python 3.12.10.
측정 일시: 2026-10-28 00:00–00:06 KST. 재현: `make load`, `make chaos`, `docker stats --no-stream`.

| 측정 항목 | 시나리오/조건 | 값 |
|---|---|---|
| k6 검색 p50 / p95 / p99 | compose 스택, `search_ramp` 25 VU | **2.47ms / 4.10ms / 5.74ms** |
| k6 실패율 (`http_req_failed`) | 〃 | **0.00%** (0/2,844) |
| k6 checks 통과율 | 〃 | **100.00%** (8,151/8,151) |
| 처리량(RPS) | 〃 | **56.9 req/s** (50초, 2,844건) |
| API CPU/메모리 (idle) | `docker stats`, 부하 종료 후 idle | CPU **0.02%** / MEM **1.80GiB** |
| `/metrics` 스크레이프 소요 | Prometheus `avg(scrape_duration_seconds{job="seoga-api"})` | **2.0ms** |
| 컨테이너 cold start (기동→ready) | `docker compose up` 후 `/readyz` 200까지 | **약 10–12초** |
| 게임데이 알림 발화 지연 | 주입(00:00:33) → 첫 firing 관측(00:02:57) | **약 2분 24초** (`for: 2m` + 평가주기 5s) |
| 게임데이 알림 복구 | 리셋 직후 정상 응답 | **5초 내 200 복구**. 알림 resolve는 for 윈도우 경과 후(정밀 측정 생략) |
| 재색인 소요(4,865권 전체) | 로컬 `python -m server.sync` | 9.5초 (실측) |
| 이미지 크기 | `seoga-api:local` (모델+인덱스 포함) | 1.36GB |

**게임데이 실측 요약:** `latency 400ms / error_rate 0.45` 주입 + 10스레드 지속 트래픽 →
`SeogaSearchLatencyP95High` **FIRING**, `SeogaErrorBudgetBurnFast` **FIRING**, `SeogaErrorBudgetBurnSlow` PENDING.
Grafana에서 에러버짓 연소 **192x**, 5xx 비율 **~45%**, 검색 p95 **~5초**까지 상승 확인 후 리셋 → 즉시 200 복구.

---

## 13. 문서 지도

| 문서 | 무엇을 답하나 |
|---|---|
| [runbooks/api-down.md](runbooks/api-down.md) | API가 죽었을 때 분류·복구·롤백 |
| [runbooks/slow-search.md](runbooks/slow-search.md) | p95 상승 시 단계별 진단(키워드/벡터/융합) |
| [runbooks/index-stale.md](runbooks/index-stale.md) | `/readyz` 실패·문서 수 불일치 시 재색인/재기동 |
| [runbooks/chaos-drill.md](runbooks/chaos-drill.md) | 게임데이 절차(주입→알림 확인→복구→기록) |
| [postmortem/TEMPLATE.md](postmortem/TEMPLATE.md) | 포스트모템 작성 템플릿 |
| [postmortem/2026-10-27-index-stale.md](postmortem/2026-10-27-index-stale.md) | 실제 사고 기록과 재발 방지 |
| [../PORTFOLIO.md](../PORTFOLIO.md) | 이 프로젝트가 증명하는 역량과 5분 데모 |
| [../README.md](../README.md) | 제품/데이터/검색 스택의 원래 설명 |

**단일 소스 원칙:** SLO 임계값과 알림 정의는 [alerts.yml](../observability/prometheus/alerts.yml), 대시보드 패널은 [seoga.json](../observability/grafana/dashboards/seoga.json), 실행 명령은 [Makefile](../Makefile)이 소스다. 이 문서는 그것을 설명하고, 값이 바뀌면 같은 커밋에서 함께 갱신한다.
