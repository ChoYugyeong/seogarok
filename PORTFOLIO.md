# 서가(seoga) — SRE/DevOps 포트폴리오

> **이 문서가 답하는 질문:** ① 이 프로젝트가 SRE/DevOps 역량을 어떻게 증명하는가(근거 파일은 어디인가)? ② 이력서/면접에서 어떤 문장으로 쓸 수 있는가? ③ 5분 데모에서 무엇을 어떤 순서로 보여주면 되는가?

**한국어 도서 검색 서비스(4,865권 실색인)** 를 소재로, **관측성 → SLO → 알림 → 런북 → 포스트모템**을 코드와 문서로 닫은 사례다. 화려한 트래픽이 아니라 **"장애를 운영하는 방식"** 을 보여주는 포트폴리오이며, 모든 수치와 파일 링크는 저장소에서 검증 가능하다. 측정값은 모두 재현 명령(`make load`, `make chaos`)과 함께 문서에 남겼다.

---

## 1. 5분 요약 — 역량 7개와 근거 파일

| # | 역량 | 핵심 산출물(저장소에 존재) | 증명 포인트 |
|---|---|---|---|
| 1 | **관측성** | [`server/metrics.py`](server/metrics.py), [`server/api.py`](server/api.py), [`observability/prometheus/prometheus.yml`](observability/prometheus/prometheus.yml), [`observability/grafana/dashboards/seoga.json`](observability/grafana/dashboards/seoga.json) | RED+도메인 메트릭 12계열(노출 시리즈 15종)을 외부 의존성 없이 구현, 5초 스크레이프, 대시보드 13패널 provisioning |
| 2 | **SLI/SLO·에러 버짓** | [`docs/SRE.md`](docs/SRE.md), [`observability/prometheus/alerts.yml`](observability/prometheus/alerts.yml) | 99.9% 가용성 SLO → 월 **43분 12초** 버짓, 1h 14.4x / 6h 6x 번레이트 알림, 배포 동결 규칙 |
| 3 | **CI/CD·보안** | [`.github/workflows/ci.yml`](.github/workflows/ci.yml), [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml), [`scripts/deploy_canary.sh`](scripts/deploy_canary.sh) | PR: 오프라인 테스트 / 이미지 빌드 + **Trivy HIGH·CRITICAL fail** / compose 스모크. CD: **카나리 0% → 스모크 → 승격 → 실패 시 자동 롤백**, **OIDC 키 없는 배포** |
| 4 | **컨테이너·배포 설계** | [`Dockerfile`](Dockerfile), [`docker-compose.yml`](docker-compose.yml), [`scripts/docker-entrypoint.sh`](scripts/docker-entrypoint.sh) | **immutable artifact**(빌드 시 인덱스/모델 고정), read-only rootfs + tmpfs WAL, 비root(uid 10001), cap_drop, `$PORT` 대응으로 Cloud Run 호환 |
| 5 | **부하테스트·용량 계획** | [`loadtest/search.js`](loadtest/search.js), [`docs/SRE.md`](docs/SRE.md) | k6 ramping 1→25 VU + SLO thresholds(p95<300ms, 실패율<1%), exact KNN 한계와 확장 전략 문서화 |
| 6 | **장애 대응·포스트모템** | [`docs/runbooks/`](docs/runbooks/), [`docs/postmortem/2026-10-27-index-stale.md`](docs/postmortem/2026-10-27-index-stale.md), [`scripts/game_day.ps1`](scripts/game_day.ps1) | 런북 5종 + 알림 7종 매핑, **실제 사고 1건**의 타임라인/근본원인/재발방지, 카오스 드릴 절차 |
| 7 | **IaC (Terraform)** | [`terraform/`](terraform/), [`docs/runbooks/deploy-rollback.md`](docs/runbooks/deploy-rollback.md), [`.github/workflows/terraform.yml`](.github/workflows/terraform.yml) | Cloud Run + Artifact Registry + **GitHub OIDC(WIF)** 를 Terraform 으로 관리, `fmt/validate` 게이트, **Terraform↔CD 충돌 방지(`ignore_changes`)** |

- 운영 진입점은 [`Makefile`](Makefile) 하나다: `make up / smoke / load / chaos / reset-chaos / dash / logs / ps / down / test`.
- 전체 구조와 설계 근거는 [`docs/SRE.md`](docs/SRE.md)에, 진단 절차는 [`docs/runbooks/`](docs/runbooks/)에 있다.
- **데이터 규모 구분:** 도서 데이터는 **예스24 Open API(공식·Basic 무료)** 수집분 4,865권을 서비스 제공 범위 내에서 캐싱하며 저장소에는 커밋하지 않는다(`data/catalog.jsonl` 은 gitignore). 저장소에는 오프라인 테스트용 38권 seed 만 있다.

---

## 2. 역량별 상세 (면접 답변용)

### ① 관측성 — "무엇이 느린지/깨졌는지 1분 안에 말할 수 있는가"

- **구현:** 표준 라이브러리만으로 Prometheus 텍스트 포맷을 직접 생성([`server/metrics.py`](server/metrics.py)). 요청 히스토그램, 검색 단계별 소요(`keyword/vector/fuse`), 검색 전략 분포(`exact-first/rrf/vector-only`), 인덱스 상태 게이지를 노출.
- **운영 엔드포인트 분리:** `/healthz`(liveness), `/readyz`(DB live count로 `documents == vectors` 판정), `/metrics`, `POST /api/_chaos`(게임데이). `readyz`가 메타 캐시가 아니라 **DB 실제 count**를 읽는 것이 핵심.
- **로그:** stdout JSON 1줄/요청(`req_id, method, path, route, status, dur_ms, ua`). 응답 헤더 `X-Request-Id`와 상관관계를 만들 수 있다.
- **카디널리티 통제:** route 10종으로 정규화하고 질의어/책 ID를 라벨에서 제외(TSDB 보호).
- **근거:** [`server/api.py`](server/api.py)(엔드포인트/계측), [`observability/grafana/dashboards/seoga.json`](observability/grafana/dashboards/seoga.json)(13패널), [`docs/SRE.md` §3](docs/SRE.md).

### ② SLO — "장애를 '몇 분'으로 계량하고 배포를 통제하는가"

- **SLO 4종:** 가용성 99.9%/30일, 검색 p95 < 300ms, 에러율 < 1%, 인덱스 신선도 < 24h.
- **에러 버짓:** 99.9% → 월 **43분 12초**. fast burn(1h 14.4x)/slow burn(6h 6x) 2단계 알림과 **배포 동결 규칙**을 문서화.
- **알림 7종:** `SeogaApiDown`, `SeogaNotReady`, `SeogaErrorBudgetBurnFast`, `SeogaErrorBudgetBurnSlow`, `SeogaSearchLatencyP95High`, `SeogaIndexStale`, `SeogaIndexEmpty`. 모든 알림 annotation에 `runbook:` 경로가 들어 있어 온콜이 바로 런북으로 이동한다.
- **근거:** [`observability/prometheus/alerts.yml`](observability/prometheus/alerts.yml), [`docs/SRE.md` §4–§5](docs/SRE.md).

### ③ CI/CD — "머지 전에 무엇이 검증되는가"

| job | 검증 내용 |
|---|---|
| `test` | Python 3.12 + `requirements.server.txt` 설치 → seed 38권 인덱스를 **hashing 임베딩**으로 생성(모델 가중치 다운로드 없음) → 검색 파이프라인 단언 |
| `build` | `docker build` → **Trivy** `HIGH,CRITICAL` 발견 시 실패(`ignore-unfixed: true`) |
| `compose-smoke` | `docker compose up -d --build api prometheus` → `/healthz`, `/readyz`, `/metrics`(`seoga_index_documents 500`), `/api/search` 검증 → 로그 수집 후 `down -v` |

- `permissions: contents: read`, `concurrency`(같은 ref 중복 실행 취소), job별 timeout.
- 알림봇(별도 저장소) 테스트는 저장소 경계상 제외 — 이 판단도 CI에 주석으로 남겼다.
- **근거:** [`.github/workflows/ci.yml`](.github/workflows/ci.yml), [`Makefile`](Makefile).

### ④ 컨테이너·배포 — "재현 가능한 아티팩트를 만드는가"

- **멀티스테이지:** builder에서 의존성 설치 + 임베딩 모델 고정 + `python -m server.sync`로 인덱스 생성 → runtime에는 결과물만 복사.
- **immutable artifact:** 런타임에 재색인 경로가 없다. 재색인 stale 사고를 구조적으로 제거(§③ 참조).
- **보안 기본값:** `read_only: true`, `tmpfs /tmp`(SQLite WAL), `cap_drop: ALL`, `no-new-privileges`, 비root(uid 10001), tini PID 1.
- **엔트리포인트:** 이미지에 구운 `data/seoga.db` → `/tmp/data/seoga.db` 복사 후 API 기동([`scripts/docker-entrypoint.sh`](scripts/docker-entrypoint.sh)). 읽기 전용 루트에서도 SQLite WAL이 동작하는 이유를 문서에 설명.
- **근거:** [`Dockerfile`](Dockerfile), [`docker-compose.yml`](docker-compose.yml).

### ⑤ 부하테스트·용량 — "SLO를 실제로 재는가, 한계를 아는가"

- **k6 시나리오:** ramping-vus 1→10→25→0, 검색 질의 10종, think time 0.1–0.4s. thresholds: `http_req_failed < 1%`, `route:search` p95 < 300ms·p99 < 800ms, `checks > 99%`. 임계값 실패 시 k6가 비-0 종료코드로 CI/게임데이에서 판정 가능.
- **기준선(실측):** 로컬 4,865권 인덱스에서 **하이브리드 p50 2.88ms / p95 7.79ms**, 인덱스 구축 9.5초, exact KNN 합성 50k 48.6ms([`README.md`](README.md), `data/bench_report.json`은 로컬 산출물).
- **한계 인지:** 단일 SQLite writer, exact KNN 선형 증가 → 100만 규모는 IVF/HNSW(pgvector, Qdrant) 전환 전략. 컨테이너(500권) HTTP 부하 결과는 **p95 4.10ms / 실패율 0.00% / 56.9 RPS**로 [`docs/SRE.md` §9.3·§12](docs/SRE.md)에 정리했다.
- **근거:** [`loadtest/search.js`](loadtest/search.js), [`docs/SRE.md`](docs/SRE.md).

### ⑥ 장애 대응 — "사고를 다시 안 나게 닫는가"

- **런북 4종**(알림 7종 → 런북 경로 매핑): [`api-down`](docs/runbooks/api-down.md), [`slow-search`](docs/runbooks/slow-search.md), [`index-stale`](docs/runbooks/index-stale.md), [`chaos-drill`](docs/runbooks/chaos-drill.md).
- **실제 사고 포스트모템:** 2026-10-27, 재색인 후에도 실행 중이던 API가 38권 시점 메타데이터를 `ok: true`로 노출. 타임라인(증거 기반), 근본 원인, 액션 아이템(완료/대기 구분)을 기록 → [`2026-10-27-index-stale.md`](docs/postmortem/2026-10-27-index-stale.md).
- **재발 방지(구현 완료):** `/readyz` live-count 판정, 문서 수/신선도 게이지, `SeogaNotReady`/`SeogaIndexStale`/`SeogaIndexEmpty` 알림, 재색인 런북, immutable 이미지.
- **게임데이:** `make chaos`(또는 [`scripts/game_day.ps1`](scripts/game_day.ps1))로 지연/오류 주입 → Prometheus 알림 발화 확인 → 리셋 → 기록. 관측 엔드포인트 4종은 카오스에서 제외되어 장애 중에도 대시보드가 살아있다. **실측: 주입 2분 24초 뒤 알림 FIRING, 리셋 후 5초 내 200 복구**([chaos-drill.md](docs/runbooks/chaos-drill.md) §7).
- **근거:** [`docs/runbooks/`](docs/runbooks/), [`docs/postmortem/`](docs/postmortem/), [`scripts/game_day.ps1`](scripts/game_day.ps1).

**증거 화면 — 카오스 드릴 중 캡처 (저장소 커밋됨)**

![Prometheus 알림 FIRING](docs/assets/sre-alerts-firing.png)

> `SeogaErrorBudgetBurnFast` · `SeogaSearchLatencyP95High` 가 FIRING, `BurnSlow` 는 PENDING.
> 같은 시각 Grafana 대시보드: [에러버짓 192x · 5xx 45% · p95 5초](docs/assets/sre-grafana.png) · [스크레이프 타깃 up](docs/assets/sre-targets.png).

---

### ⑦ IaC·무중단 배포 — "인프라를 코드로 만들고, 배포를 되돌릴 수 있는가"

- **Terraform ([`terraform/`](terraform/)):** Cloud Run v2 서비스, Artifact Registry(최근 10개 유지), 런타임 SA, **GitHub OIDC Workload Identity Federation**, 배포 SA/최소 권한 IAM. `fmt -check` + `init -backend=false` + `validate` 를 PR 게이트로, main 에서는 GCS state 로 plan/apply(승인 Environment).
- **키 없는 배포:** 장기 서비스 계정 키 파일이 없다. GitHub Actions 가 OIDC 토큰을 배포 SA 로 교환하고, WIF provider 의 `attribute_condition` 으로 **이 저장소만** 허용.
- **카나리 배포 ([`scripts/deploy_canary.sh`](scripts/deploy_canary.sh)):** 새 리비전을 `--no-traffic --tag=canary` 로 배포 → 카나리 URL 스모크 → `--to-latest` 승격 → 운영 스모크. 실패 시 `if: failure()` 가 직전 리비전으로 **자동 롤백**.
- **Terraform ↔ CD 충돌 방지:** `ignore_changes = [image, traffic]`. 이걸 안 하면 `terraform apply` 가 CD/롤백이 바꾼 이미지·트래픽을 되돌려 장애를 만든다. 역할 분담을 문서화했다.
- **스모크 게이트 ([`scripts/smoke.sh`](scripts/smoke.sh)):** `/healthz`·`/readyz`(docs==vectors)·`/api/search`·`/metrics(seoga_ready=1)` 를 URL 하나로 검사 — 로컬 compose 검증에도 같은 스크립트를 쓴다.
- **근거:** [`terraform/`](terraform/), [`deploy.yml`](.github/workflows/deploy.yml), [`docs/runbooks/deploy-rollback.md`](docs/runbooks/deploy-rollback.md), 무료 티어 비용 메모(월 $0, 콜드스타트 8~10초).

---

## 3. 이력서에 바로 쓰는 bullet 6개

> 숫자는 저장소에서 검증 가능한 값만 넣었고, 모든 측정은 `make load` / `make chaos`로 재현할 수 있다.

1. 로컬 4,865권 인덱스로 개발한 한국어 도서 검색 API를 컨테이너화(이미지 인덱스 500권 샘플)하고, k6(최대 25 VU, 50초)로 검색 p95 **4.10ms**·에러율 **0.00%**(2,844건)를 확인 — SLO 300ms 대비 **약 73배** 여유.
2. Prometheus 메트릭 12계열(노출 시리즈 15종)·Grafana 대시보드 13패널·알림 7규칙을 **전부 provisioning 코드**로 관리해, `make up` 한 번으로 동일한 관측 스택을 재현.
3. 99.9% 가용성 SLO 기준 월 **43분 12초** 에러 버짓과 1h **14.4x** / 6h **6x** 멀티번레이트 알림·배포 동결 규칙을 수립하고, 알림 7종 각각에 런북 경로를 매핑.
4. 멀티스테이지 컨테이너에 임베딩 모델과 검색 인덱스를 **빌드 타임에 고정**하고 read-only rootfs + tmpfs WAL + 비root로 기동해, 런타임 재색인 의존과 stale 인덱스 사고를 구조적으로 제거.
5. 재색인 후 stale 인덱스가 "정상"으로 노출된 사고를 포스트모템으로 정리하고, `/readyz` live-count 검증 + 문서 수 메트릭 + 알림으로 재발 방지 — 사고 재발 방지 항목 **9개 중 6개 완료(당일)**.
6. Terraform 으로 Cloud Run·Artifact Registry·IAM 을 코드화하고 **GitHub OIDC(무키) 배포 + 카나리 0% → 스모크 → 승격 → 실패 시 자동 롤백** 파이프라인을 구성. Terraform 과 CD 의 관리 경계(`ignore_changes`)를 분리해 긴급 롤백이 인프라 코드와 충돌하지 않게 설계.

---

## 4. 면접 5분 데모 시나리오

전제: `make up`은 미리 실행해 둔다(이미지 빌드 시간 제외). 화면 2개 — 터미널 + Grafana.

| 시간 | 무엇을 | 어떻게 | 말할 것 |
|---|---|---|---|
| 0:00–0:30 | 오프닝 | `make ps` | "상시 3개 서비스(api/prometheus/grafana)와 k6(profile load)를 compose로 코드화했고, 인덱스는 이미지에 구워집니다." |
| 0:30–1:30 | 관측성 | Grafana `http://localhost:3001/d/seoga-sre` + `curl /readyz` | "상단 stat 5개가 ready·문서 수·신선도·burn·공지. readyz는 DB live count라 재색인 후 stale을 정상으로 보고하지 않습니다." |
| 1:30–2:30 | SLO·알림 | `observability/prometheus/alerts.yml` + Prometheus `/alerts` | "99.9% SLO = 월 43분 12초. fast 14.4x/1h, slow 6x/6h. 알림 annotation에 런북 경로가 들어 있습니다." |
| 2:30–3:20 | 부하테스트 | `make load` | "k6가 p95<300ms, 실패율<1%를 threshold로 강제합니다. 컨테이너 500권 기준 p95 4.1ms·실패율 0%로 통과했습니다." |
| 3:20–4:20 | 게임데이 | `make chaos` → `/alerts` 확인 → `make reset-chaos` (스크립트 대안: `powershell -ExecutionPolicy Bypass -File .\scripts\game_day.ps1 -Scenario all`) | "지연 400ms/오류 30%를 주입하면 2–3분 내 latency·burn 알림이 뜹니다. 관측 4경로는 주입에서 제외돼 대시보드는 살아있습니다." |
| 4:20–5:00 | 포스트모템·확장 | `docs/postmortem/2026-10-27-index-stale.md` + `Dockerfile` | "재색인 후 38권 stale을 '정상'으로 보고한 실제 사고를, readyz·문서 수 알림·이미지 빌드 인덱스로 닫았습니다. 다음 병목은 단일 SQLite writer와 exact KNN입니다." |
| 5:00–6:00 (여유 시) | IaC·배포 | `.github/workflows/deploy.yml` + `docs/runbooks/deploy-rollback.md` | "Cloud Run 을 Terraform 으로 관리하고, 배포는 키 없는 OIDC 로 카나리 0%에 올려 스모크 후 승격합니다. 실패하면 자동 롤백. 이미지·트래픽은 `ignore_changes` 로 Terraform 관리에서 빼서 긴급 롤백과 충돌하지 않습니다." |
| (선택) 라이브 데모 | `.\scripts\share_demo.ps1` | "로컬 스택을 Cloudflare Quick Tunnel 로 공개 URL에 노출합니다 — 도메인·계정 없이 무료(실측 200). 인증이 없으니 데모 직후 종료합니다." |

**데모에서 하지 말 것:** 수치를 말로만 주장하기(문서 링크를 연다), `make up` 전에 `make smoke`부터 돌리기(기동 대기 실패), 카오스 리셋 잊기.

---

## 5. 왜 이게 포트폴리오로 강한가 (3줄)

1. **관측성·알림·런북·포스트모템이 하나의 폐루프로 연결**되어 있다 — 대부분의 개인 포트폴리오는 "기능 구현"에서 끝나고 온콜 문서·에러 버짓·사후 대응은 없다.
2. **실제로 겪은 사고 1건**을 증거(타임라인 파일)와 재발 방지(코드 변경)로 닫아, "장애를 겪으면 무엇을 바꾸는가"를 말이 아니라 산출물로 보여준다.
3. **숫자를 지어내지 않았다** — 측정 전에는 표를 비워두고, 측정 후 재현 명령과 함께 채웠다. 모든 수치는 `make load`/`make chaos`로 재현 가능하다.

---

## 6. 더 읽을 문서 (5분 이후)

| 순서 | 문서 | 읽는 목적 |
|---|---|---|
| 1 | [`docs/SRE.md`](docs/SRE.md) | 아키텍처, SLI/SLO, 알림 설계, CI, 부하테스트, 한계 (핵심 문서) |
| 2 | [`docs/runbooks/`](docs/runbooks/) | 온콜이 실제로 하는 절차 4종 |
| 3 | [`docs/postmortem/2026-10-27-index-stale.md`](docs/postmortem/2026-10-27-index-stale.md) | 실제 사고와 재발 방지 |
| 4 | [`README.md`](README.md) | 제품/검색 스택/데이터의 원래 설명 |

**검증 안내:** 문서 속 링크는 저장소에 존재하는 파일만 가리킨다. 전체 측정값은 [`docs/SRE.md` §12](docs/SRE.md) 표에, 이력서용 요약은 이 문서 §3 bullet에 있다.
