# 포스트모템: 재색인 후 stale 인덱스가 "정상"으로 노출됨 (2026-10-27)

> **이 문서가 답하는 질문:** ① 인덱스를 새로 만들었는데 서버가 옛 인덱스를 정상이라고 보고하면 어떻게 발견하고 고치나? ② 왜 `/readyz`·문서 수 메트릭이 사후에 추가됐나? ③ 같은 사고가 컨테이너 배포에서도 가능한가?

- 발생: 2026-10-27 **22:45:22 KST** (최종 재색인 완료 시점. 실행 중이던 프로세스는 이전 인덱스 메타를 유지)
- 탐지: 재색인 완료 후 수동 확인 — `/api/health`가 여전히 `books=38`, `notices=0`을 반환
- 복구: API 프로세스 재기동 → 새 인덱스(4,021권) 로드 확인
- 심각도: **SEV-3** (내부 개발 환경, 외부 사용자 영향 없음, 데이터 손실 없음)
- 상태: 재발 방지 구현 완료, 잔여 오픈 항목 있음(§8)

---

## 1. TL;DR

1. 카탈로그를 38권(seed)에서 4,021권으로 재색인했지만, **실행 중이던 API 프로세스가 부팅 시점에 캐시한 메타데이터(38권/0건)를 계속 `ok: true`로 노출**했다. 검색 데이터는 재색인됐지만, API가 스스로 보고하는 인덱스 상태는 옛 값이었다.
2. 직접 원인은 `AppState`가 기동 시 `book_count`/`notice_count`/`synced_at`을 1회 로드해 캐시하고, 재색인은 DB만 갱신하고 프로세스를 갱신하지 않은 것. 여기에 "재색인 후 재기동"이 절차에 없었고, 인덱스 신선도를 자동으로 탐지하는 지표/알림이 없었다.
3. 같은 날 `/readyz`(DB live count로 `documents == vectors` 검증)와 문서 수/신선도 게이지, 3개 알림, 재색인 런북, 이미지 빌드 시 인덱스 생성(immutable artifact)을 도입해 같은 실패 모드를 구조적으로 제거했다.

## 2. 영향

| 구분 | 내용 |
|---|---|
| 사용자 영향 | 없음(외부 사용자 없는 개발/연구 환경). 단, UI/헬스가 "38권 정상"으로 표시되어 **운영자 판단을 오염**시켰다. |
| 데이터 영향 | 없음. 재색인은 성공했고 최종 DB meta는 `book_count=4021`, `notice_count=338`, `synced_at=22:45:22`. |
| SLO 영향 | 당시 인덱스 신선도 SLI가 **측정 불가**(메트릭 부재) → 이 사고의 핵심 갭. 가용성 SLO(5xx)에는 영향 없음. |
| 탐지 지연 | 자동 탐지 없음. 수동 대조로 발견. 정확한 탐지 시각은 기록에 없음(미상). |

## 3. 타임라인 (KST)

| 시각 | 이벤트 | 근거 |
|---|---|---|
| 22:24:55 | seed 카탈로그(38권) 기준으로 로컬 작업 시작 | `data/seed_catalog.jsonl` 수정 시각, 38행 |
| 22:25:50 | API 스모크 스크립트 작성 | `_qa/api_smoke.py` |
| 22:28:12 | **38권 인덱스로 sync 완료**, API가 이 시점에 부팅 | `_qa/api_smoke.json`의 `synced_at=2026-10-27T22:28:12+0900` |
| 22:28:26 | `/api/health` → `books=38`, `notices=0` (정상) | `_qa/api_smoke.json` |
| 22:37:47 | 카탈로그 4,021행 확인 | `_qa/catalog_summary.json` (`total: 4021`) |
| 22:38:27 | 4,021권 인덱스로 벤치마크 완료 (`books=4021 vectors=4021`) | `_qa/bench_out3.txt`, `data/bench_report.json` |
| 22:44:12 | 최종 카탈로그 파일 갱신 | `data/catalog.jsonl` 수정 시각 |
| 22:45:22 | **최종 재색인 완료** (`book_count=4021`, `notice_count=338`, `synced_at=22:45:22`) | `data/seoga.db` meta |
| 22:45 이후 | 위 시점에 떠 있던 API 프로세스는 계속 `books=38`, `notices=0`, `synced_at=22:28:12`를 반환. 재기동 전까지 지속 | `/api/health` 관측(수동) |
| (미상) | 수동 대조로 불일치 발견 → API 재기동 → `/api/health`가 4,021로 갱신 | 재기동 시각 기록 없음 |

> 시각은 로컬 파일 수정 시각과 당시 QA 산출물에서 복원했다. 서버 재기동/탐지 시각은 기록이 없어 **추정하지 않는다** — 이것 자체가 §8 A7의 액션 아이템이다.

## 4. 탐지

- **당시:** `/api/health.books`(38)와 `data/catalog.jsonl` 행 수(4,021)를 사람이 대조해서 발견.
- **당시 자동 탐지 수단:** 없음.
  - `/readyz` 없음 → "인덱스가 실제로 준비됐는가"를 물을 수 있는 엔드포인트가 없었다.
  - 문서 수/신선도 메트릭 없음 → Grafana/Prometheus에서 stale을 볼 수 없었다.
  - `/api/health`는 캐시된 메타를 `ok: true`로 반환 → **stale 상태를 정상으로 보고**했다.
- **지금:** `/readyz`가 DB live count로 `documents == vectors`를 검증하고, `seogarok_index_documents`/`seogarok_index_vectors`/`seogarok_index_age_seconds` 게이지와 `SeogaNotReady`/`SeogaIndexStale`/`SeogaIndexEmpty` 알림이 탐지한다.

## 5. 근본 원인

**직접 원인 — 프로세스 수명과 인덱스 수명의 결합**

`AppState`는 기동 시 `meta` 테이블을 한 번 읽어 `book_count`, `notice_count`, `synced_at`, `embed_backend`를 인스턴스 속성으로 보관한다. `/api/health`는 이 캐시를 그대로 반환하면서 `"ok": true`를 함께 내려준다. 재색인은 **DB만** 바꾸고 프로세스 상태는 바꾸지 않으므로, 재기동 전까지 헬스는 옛 인덱스를 정상이라고 주장한다.

**기여 원인**

1. 재색인 후 재기동이 운영 절차에 없었다(수동 실행).
2. `python -m server.sync`가 카탈로그 부재 시 seed(38권)로 자동 폴백한다. 로그에는 남지만, 결과가 "성공"이므로 38권 인덱스도 정상으로 보인다.
3. 인덱스 신선도/문서 수를 자동 검증하는 지표·알림이 없었다.
4. `/readyz`가 없어 "프로세스 생존"과 "인덱스 준비"를 구분할 수단이 `health` 하나뿐이었다.

**구조적 관점**

- 검색 경로는 요청마다 같은 SQLite 파일을 다시 조회하므로 재색인 후 신규 데이터가 조회될 수 있었다. 그러나 이는 **보장된 동작이 아니라** 프로세스 상태와 DB 상태가 우연히 분리되어 있던 결과다. "검색 결과는 새 데이터, 헬스는 옛 데이터"라는 불일치 자체가 위험 신호였다.
- 컨테이너(immutable) 경로는 이미지 빌드 시점에 인덱스를 구워 런타임 재색인이 없으므로 이 실패 모드가 구조적으로 불가능하다. 당시 사고는 **호스트 직접 실행 경로**에서 발생했다.

## 6. 복구

1. 실행 중이던 API 프로세스 재기동.
2. `/api/health`가 `books=4021`, `notices=338`, `synced_at=22:45:22`을 보고하는지 확인.
3. `/api/search`가 전체 카탈로그 기준 결과를 반환하는지 확인(벤치마크와 동일 질의 사용).
4. 이후 재발 방지 항목(§8) 구현.

롤백은 필요 없었다(데이터 손실 없음). 재기동 외에 데이터 복구 작업도 없었다.

## 7. 잘한 점 / 부족한 점

**잘한 점**
- 재색인 자체는 성공했고(4,021권, 벤치마크로 검증) 데이터 손실이 없었다.
- 38권→4,021권 전환을 벤치마크/QA 산출물로 남겨, 사후에 타임라인을 복원할 수 있었다.

**부족한 점**
- 자동 탐지가 없었다. "정상" 신호가 틀렸을 때 사람이 의심해야만 발견된다.
- 재색인·재기동이 하나의 절차로 묶여 있지 않았다.
- 재기동/탐지 시각을 기록하는 표준이 없어 사고 구간을 정확히 특정하지 못했다.

## 8. 재발 방지 액션 아이템

| ID | 액션 | 유형 | 담당 | 상태 |
|---|---|---|---|---|
| A1 | `/readyz` 신설 — 메타 캐시가 아니라 **DB live count**로 `documents > 0 && documents == vectors` 판정 | 코드 | 리드 | 완료(2026-10-27) |
| A2 | `seogarok_index_documents`, `seogarok_index_vectors`, `seogarok_index_age_seconds`, `seogarok_db_size_bytes` 게이지 노출 | 관측 | 리드 | 완료(2026-10-27) |
| A3 | 알림 추가: `SeogaNotReady`, `SeogaIndexStale`, `SeogaIndexEmpty` | 관측 | 리드 | 완료(2026-10-27) |
| A4 | 재색인 절차에 **재기동 + 검증**을 고정한 런북 작성 | 문서 | sre-writer | 완료 — [runbooks/index-stale.md](../runbooks/index-stale.md) |
| A5 | 이미지 빌드 시 인덱스 생성(immutable artifact) → 런타임 재색인 제거 | 배포 | 리드 | 완료 — [Dockerfile](../../Dockerfile), [scripts/docker-entrypoint.sh](../../scripts/docker-entrypoint.sh) |
| A6 | CI compose 스모크에서 `/healthz`·`/readyz`·`/metrics`(문서 수) 검증 | CI | sre-writer | 완료 — [.github/workflows/ci.yml](../../.github/workflows/ci.yml) |
| A7 | 배포·재기동·탐지 시각을 표준 로그/티켓으로 기록 | 절차 | 리드 | 대기 |
| A8 | `/api/health`도 live count 기반으로 통일(또는 캐시 폐기) — 현재는 재기동 필요 | 코드 | 리드 | 대기 |
| A9 | 컨테이너 장기 실행 시 `seogarok_index_age_seconds`가 "빌드 후 경과"를 의미하는 문제 정리(경보 기준 재정의 또는 정기 재배포) | 관측 | 리드 | 대기 — [runbooks/index-stale.md §6](../runbooks/index-stale.md) |

## 9. 교훈

1. **liveness ≠ readiness ≠ freshness.** "살아있다"는 응답이 "최신 인덱스로 서빙 중"을 의미하지 않는다. 세 질문을 분리한 엔드포인트/지표가 필요하다.
2. **상태 엔드포인트는 실제 리소스에서 읽어라.** 캐시된 메타를 `ok`로 포장하면, 시스템이 스스로 거짓말을 한다.
3. **재색인은 "데이터 교체 + 프로세스 교체"의 2단계 연산이다.** 둘을 한 절차(또는 이미지 빌드)로 묶지 않으면 이 사고는 반복된다.

## 10. 증거 (로컬 산출물, 저장소에는 미커밋)

| 파일 | 관측값 | 의미 |
|---|---|---|
| `_qa/api_smoke.json` | `health.books=38`, `synced_at=22:28:12` | API가 38권 seed 인덱스로 부팅된 상태 |
| `_qa/bench_out3.txt` | `[bench] books=4021 vectors=4021` | 22:38 시점 DB는 4,021권으로 재색인됨 |
| `_qa/catalog_summary.json` | `total: 4021` | 카탈로그 4,021행 |
| `data/bench_report.json` | `generated_at=2026-10-27T22:38:27+0900` | 위 벤치마크 산출물 |
| `data/seoga.db` meta | `book_count=4021`, `notice_count=338`, `synced_at=2026-10-27T22:45:22+0900` | 최종 재색인 완료 |
| `data/catalog.jsonl` | 22:44:12 갱신 | 최종 카탈로그 반영 시각 |

> 위 경로 중 `_qa/`, `data/catalog.jsonl`, `data/seoga.db`, `data/bench_report.json`은 `.gitignore` 대상(로컬 산출물)이라 문서 링크 대신 경로로만 인용한다. 저장소에 남는 관련 코드/설정은 [server/api.py](../../server/api.py), [alerts.yml](../../observability/prometheus/alerts.yml), [runbooks/index-stale.md](../runbooks/index-stale.md), [SRE.md](../SRE.md)이다.

## 11. 남은 조사 (미해결)

- 사고 구간 동안의 실제 요청 수/5xx 여부는 **측정되지 않았다**(당시 메트릭 없음). 영향 산정은 "외부 사용자 없음"으로 한정한다.
- `/api/health`가 옛 값을 반환하는 동안 검색 결과가 신규 데이터였는지 여부는 그 시점의 요청 로그가 없어 **재현/검증 불가**. A8로 상태 엔드포인트를 통일할 때 함께 해소한다.
