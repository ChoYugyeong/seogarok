# 런북: API 다운 (`SeogaApiDown`)

> **이 문서가 답하는 질문:** ① API가 죽었을 때 5분 안에 "프로세스 문제 / 준비 실패 / 배포 문제"로 분류하려면? ② 재시작과 롤백 중 무엇을 먼저 해야 하나? ③ 복구를 무엇으로 검증하나?

관련 알림: `SeogaApiDown`(`up{job="seogarok-api"} == 0`, 30s), `SeogaErrorBudgetBurnFast`(5xx 급증, 2m). 관련 문서: [SRE.md](../SRE.md), [slow-search.md](slow-search.md), [index-stale.md](index-stale.md).

---

## 1. 증상 (하나라도 해당하면 이 런북)

- Prometheus `/alerts`에 `SeogaApiDown` firing, Grafana 상단 **API Ready = 0**.
- 브라우저/curl이 `Connection refused` 또는 timeout.
- `docker compose ps`에서 `seogarok-api`가 `Up`이 아니거나 재시작 루프(`Restarting`).
- k6 실행 중이면 `http_req_failed`가 급등.

## 2. 심각도와 영향

| 판단 | 기준 | 행동 |
|---|---|---|
| SEV-1 | API 전체 불가(전 사용자) | 즉시 롤백 검토, 인시던트 선언 |
| SEV-2 | 간헐적 5xx(에러율 > 1%) | 원인 조사 + 필요 시 롤백 |
| SEV-3 | 단일 인스턴스/개발 환경 | 주업무 외 시간 복구 가능 |

가용성 SLO 99.9%(월 43분 12초)를 소모 중이다. 5분 이상 지속되면 [postmortem/TEMPLATE.md](../postmortem/TEMPLATE.md) 작성 대상.

## 3. 첫 5분: 분류와 1차 조치

```powershell
# 1) 컨테이너 상태
docker compose ps

# 2) 최근 로그 (엔트리포인트/파이썬 예외가 대부분 여기 나온다)
docker compose logs --tail=200 api

# 3) 헬스 2종 — 여기서 갈린다
curl.exe -s -o NUL -w "healthz=%{http_code}`n" http://127.0.0.1:8100/healthz
curl.exe -s -o NUL -w "readyz=%{http_code}`n"  http://127.0.0.1:8100/readyz
```

| 관찰 | 해석 | 이동 |
|---|---|---|
| `healthz=200`, `readyz=503` | 프로세스는 살았고 **인덱스가 준비 안 됨** | → [index-stale.md](index-stale.md) |
| 둘 다 실패 + `ps`에 컨테이너 없음 | 프로세스/컨테이너 다운 | 아래 §4 |
| `Up`인데 재시작 반복 | 기동 실패(설정/파일/권한) | 아래 §4 |
| 200이지만 5xx 급증(알림은 burn) | 부분 장애 → 롤백 1순위 | §5 |

## 4. 프로세스가 안 뜰 때 (순서대로)

1. **exit code 확인** — 재시작 루프는 exit code가 원인을 말해준다.
   ```powershell
   docker inspect --format '{{.State.Status}} exit={{.State.ExitCode}}' seogarok-api
   ```
2. **로그에서 흔한 원인 4가지 확인** (`docker compose logs --tail=200 api`):
   - `db_seeded_to_tmpfs` 이후 `Read-only file system` → `read_only`인데 tmpfs `/tmp`가 빠진 경우. compose의 `tmpfs` 설정을 확인하고 **파일을 고친 뒤** 재기동.
   - `Permission denied` → 이미지가 `USER app`(uid 10001)으로 뜨는데 파일 소유권이 깨진 경우. `docker compose up -d --build api`로 이미지부터 재생성.
   - `HF_HUB_OFFLINE` 관련 예외 → 임베딩 모델이 이미지에 없음. 이미지 빌드 단계 로그 확인 후 재빌드.
   - `Address already in use` → 8100 포트 경합.
     ```powershell
     Get-NetTCPConnection -LocalPort 8100 -State Listen | Select-Object LocalAddress,OwningProcess
     # Linux/Git Bash: ss -ltnp 'sport = :8100'
     ```
3. **재기동** (설정 변경이 없을 때):
   ```powershell
   docker compose restart api
   ```
4. **재빌드** (이미지/인덱스/의존성 변경 또는 손상 의심):
   ```powershell
   docker compose up -d --build api
   ```
5. 그래도 안 되면 스택을 완전히 내리고 올린다(볼륨은 유지, Prometheus 이력 보존):
   ```powershell
   docker compose down
   docker compose up -d --build
   ```

## 5. 롤백 (배포 직후 5xx라면 기본 선택)

인덱스가 이미지에 함께 구워지므로 **롤백 = 이미지 태그 교체**다. 데이터 마이그레이션이 없다.

```powershell
# 배포 전에 반드시 해둘 것 (표준 절차)
docker tag seogarok-api:local seogarok-api:rollback

# 문제 발생 시
docker tag seogarok-api:rollback seogarok-api:local
docker compose up -d --no-build api
make smoke
```

`--build`를 붙이면 다시 현재 코드로 빌드되므로 롤백에는 `--no-build`를 쓴다. 롤백 후에도 5xx가 지속되면 원인이 코드가 아닌 외부(호스트 리소스/DB 손상)이므로 §4와 [slow-search.md](slow-search.md)를 함께 본다.

## 6. 복구 검증 (체크리스트)

```powershell
make smoke        # /healthz, /readyz, /metrics, /api/search
```

- [ ] `/healthz` 200, `readyz` 200이며 `documents == vectors` (컨테이너 기준 500, 로컬 전체 인덱스는 4,021)
- [ ] `/metrics`에 `seogarok_ready 1`, `seogarok_http_requests_total` 증가
- [ ] Prometheus에서 `SeogaApiDown` resolve
- [ ] 에러율/지연이 기준선으로 복귀 (Grafana `seoga · SRE Overview`, uid `seogarok-sre`)
- [ ] 필요 시 k6로 `make load` 재확인

## 7. 기록과 후속

1. 로그 스냅샷 보관: `docker compose logs --tail=500 api > api-incident-<YYYYMMDD-HHMM>.log`
2. 5분 이상 지속 또는 SLO 버짓 소모 시 포스트모템 작성([TEMPLATE.md](../postmortem/TEMPLATE.md)).
3. 원인이 "재색인 후 재기동 누락"이었다면 [index-stale.md](index-stale.md)의 절차를 따르고, 런북을 갱신한다.
