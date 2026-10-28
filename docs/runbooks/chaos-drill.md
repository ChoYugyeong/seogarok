# 런북: 카오스 게임데이 (`chaos-drill`)

> **이 문서가 답하는 질문:** ① 장애를 안전하게 주입해서 알림·대시보드·런북이 실제로 동작하는지 어떻게 검증하나? ② 주입 후 어떤 순서로 "알림 발화 → 복구 → 기록"을 남기나? ③ 어떤 상황이면 드릴을 중단하고 실제 인시던트로 전환하나?

관련 알림: `SeogaSearchLatencyP95High`, `SeogaErrorBudgetBurnFast`(그리고 리셋 누락 시 `SeogaNotReady`). 관련 문서: [SRE.md](../SRE.md) §4·§5, [api-down.md](api-down.md), [slow-search.md](slow-search.md), [postmortem/TEMPLATE.md](../postmortem/TEMPLATE.md).

---

## 1. 목적과 범위

- **목적:** 알림 규칙·대시보드·런북이 실제 장애에서 동작하는지 사람이 확인한다. 특히 "알림이 뜨는 시간"과 "런북대로 복구되는 시간"을 측정한다.
- **범위:** 로컬/데모 compose 스택만. `api` 컨테이너에는 `SEOG_CHAOS=1`이 기본 주입되어 있다(테스트용). **운영 프로필에서는 `SEOG_CHAOS=0`으로 내려 `/api/_chaos`가 404가 되어야 한다** — 배포 후 이 404를 확인하는 것도 드릴 항목이다.
- **주입 대상:** `/metrics`, `/healthz`, `/readyz`, `/api/_chaos` 4개 경로는 제외된다(관측·복구 경로는 장애에 휘둘리지 않아야 한다). `/api/health`와 검색 API는 주입 대상이다.

## 2. 사전 조건 (5분)

```powershell
make up           # api:8100, prometheus:9090, grafana:3001
make smoke        # /healthz, /readyz, /metrics, /api/search 모두 통과해야 시작
curl.exe -s http://127.0.0.1:8100/api/_chaos     # {"enabled":true,"latency_ms":0,"error_rate":0}
```

> **Windows 실행 팁:** `scripts/game_day.ps1`은 PowerShell 스크립트다(UTF-8 BOM 저장, Windows PowerShell 5.1/7 모두 동작). 실행 정책이 Restricted면 `-ExecutionPolicy Bypass -File`로 실행하거나, 아래 §3의 `curl.exe` 명령을 그대로 사용한다. (동작은 동일: `POST /api/_chaos`)

Grafana `http://localhost:3001/d/seogarok-sre`를 열어 baseline을 기록한다:
- API Ready = 1, Index documents = 500(컨테이너 샘플), Index age, Error budget burn (1h), p50/p95 latency.
- Prometheus `http://localhost:9090/alerts`에서 현재 firing 알림이 **0건**인지 확인.

## 3. 주입 (1분)

```powershell
# 1) 표준 (make가 있는 환경)
make chaos

# 2) curl.exe 등가 명령 (make/스크립트 없이 어디서나; Windows·Linux 공통)
curl.exe -s -X POST http://127.0.0.1:8100/api/_chaos -H "Content-Type: application/json" -d '{"latency_ms":400,"error_rate":0.3}'

# 3) 스크립트 (UTF-8 BOM / Windows PowerShell 5.1·7 모두 동작; ExecutionPolicy 차단 시 Bypass)
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\game_day.ps1 -Scenario all
# 개별 시나리오: -Scenario latency (지연만) / -Scenario error (오류만)
```

주입 직후 `GET /api/_chaos`로 실제 적용값을 확인하고, `docker compose logs --tail=20 api`에서 `chaos_set` warn 로그를 확인한다. 같은 사실을 메트릭(`400ms` 지연 → p95 상승)과 로그 두 곳에서 볼 수 있어야 한다.

## 4. 관찰 — 기대 알림과 시간 (2~3분 대기)

| 기대 알림 | 조건 | for | 예상 발화 |
|---|---|---|---|
| `SeogaSearchLatencyP95High` | `/api/search` 5분 p95 > 300ms | 2m | 주입 후 ~2–3분 (실측 **2분 24초**, §7) |
| `SeogaErrorBudgetBurnFast` | 1h 5xx 비율 > 1.44% (burn 14.4x) | 2m | 주입 후 ~2–3분 (실측 **2분 24초**, §7) |
| (부가) `SeogaNotReady` | ready==0 | 1m | 리셋 누락/실제 장애 시에만 |

확인 위치: Prometheus `/alerts`, Grafana의 **Error ratio (5xx)**, **Latency p50/p95/p99**, **Error budget burn (1h)**.
측정 항목: **주입 시각 → 알림 firing 시각**(지연), **리셋 시각 → 서비스 정상 응답 복귀**(복구). 값은 §7 표에 누적 기록한다. `SeogaErrorBudgetBurnSlow`(1h/6h 윈도우)는 리셋 후에도 rate 윈도우 때문에 resolve가 늦을 수 있으므로, **서비스 복구 판정은 "200 응답 복귀"로 하고 알림 resolve는 별도로 본다.**

런북 동작 확인(선택이지만 강력 권장): 알림을 받은 것처럼 [slow-search.md](slow-search.md) §2–§3을 따라가며 "3분 안에 원인 후보가 좁혀지는가"를 실제로 검증한다. 런북의 명령이 오래됐다면 그 자리에서 고친다.

## 5. 복구 (1분 이내)

```powershell
# 어느 쪽이든 동일
make reset-chaos
curl.exe -s -X POST http://127.0.0.1:8100/api/_chaos -H "Content-Type: application/json" -d '{"latency_ms":0,"error_rate":0}'
# 또는 (Windows PowerShell 5.1/7 공통, 스크립트는 UTF-8 BOM)
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\game_day.ps1 -Scenario reset
```

검증:
- `GET /api/_chaos` → `latency_ms:0, error_rate:0`
- 서비스 정상 응답 복귀: `/api/search` 200, 에러율 0 근접, p95 < 300ms (실측: 리셋 후 **5초 내 200 복구**)
- 알림 resolve: rate 윈도우(1h/6h) 때문에 서비스 복구보다 늦을 수 있음 — resolve 시각은 별도로 관찰
- `make smoke` 통과

**리셋은 실패해도 반드시 수행한다.** 드릴을 중간에 중단하더라도 `-Scenario reset`으로 주입 상태를 원복하지 않으면 이후 모든 측정이 오염된다.

## 6. 중단 조건 (실제 인시던트로 전환)

- 주입과 무관한 5xx/재시작 루프가 발생 → 즉시 리셋 후 [api-down.md](api-down.md)로 전환.
- `/readyz`가 503(카오스는 readiness 경로를 건드리지 않으므로 **실제 문제**다) → [index-stale.md](index-stale.md).
- 호스트 CPU/디스크가 위험 수위 → 드릴 중단, 리셋, 원인 조사.
- 이 경우 드릴 기록에 "중단 사유"를 남기고 포스트모템 대상인지 판단한다.

## 7. 기록 (드릴 결과)

드릴 후 아래 표에 누적 기록한다(측정하지 않은 값은 `미측정`으로 명시하고 추정치를 쓰지 않는다).

| 일시(KST) | 시나리오 | 주입값 | 기대 알림 | 발화(주입→firing) | 복구(리셋→정상 응답) | 발견한 갭 | 담당 |
|---|---|---|---|---|---|---|---|
| 2026-10-28 00:00:33 | all | latency 400ms, error_rate 0.45 | `SeogaSearchLatencyP95High`, `SeogaErrorBudgetBurnFast` | **2분 24초** (00:02:57 첫 firing) | **5초 내 200 복구** (알림 resolve는 rate 윈도우로 지연, 정밀 측정 생략) | 1h/6h 윈도우 알림은 리셋 후에도 resolve가 늦다 → "알림 resolve ≠ 서비스 복구"를 런북 §5에 명시 | 리드 / sre-writer |

- 드릴 당시 관측: `LatencyP95High`·`BurnFast` **FIRING**, `BurnSlow` **PENDING**, Grafana 에러버짓 연소 **192x**, 5xx **~45%**, 검색 p95 **~5초**.
- 증거(저장소 커밋): [Grafana 대시보드](../assets/sre-grafana.png) · [Prometheus `/alerts` FIRING](../assets/sre-alerts-firing.png) · [타깃 상태](../assets/sre-targets.png)
- 함께 남기는 로그: `chaos_set` 응답, `make smoke` 출력, `docker compose ps`(healthy), 리셋 후 `/api/search` 200.

## 8. 드릴 완료 기준 (Definition of Done)

- [ ] 기대 알림이 예상 시간 안에 firing 된다(서비스 복구 판정은 알림 resolve가 아니라 200 응답 복귀로 한다).
- [ ] 런북만 보고 원인 분류(지연/오류/준비 실패)와 복구까지 도달했다.
- [ ] 리셋 후 SLO 지표가 baseline으로 돌아왔다.
- [ ] 발견한 갭이 문서/알림/대시보드에 반영되거나 티켓으로 남았다.
- [ ] 운영 프로필에서 `POST /api/_chaos` → 404(비활성)를 확인했다.
