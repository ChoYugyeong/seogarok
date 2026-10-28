# 배포 & 롤백 (Cloud Run)

**이 문서가 답하는 질문**
1. 코드가 머지되면 어떤 순서로 운영에 반영되는가?
2. 배포가 깨졌을 때 **몇 초 만에** 이전 버전으로 되돌리는가?
3. Terraform 과 긴급 롤백이 서로 싸우지 않게 어떻게 했는가?

---

## 1. 파이프라인 (`.github/workflows/deploy.yml`)

```
push(main)
  └─ build & push        : Docker build → Artifact Registry (:git-SHA)
       └─ deploy         : 새 리비전 배포 --no-traffic --tag=canary   ← 사용자 트래픽 0%
            └─ smoke     : 카나리 URL에 /healthz·/readyz·/api/search·/metrics
                 └─ promote : --to-latest (100%)
                      └─ smoke : 운영 URL 동일 검사
                           ├─ 성공 → 종료
                           └─ 실패 → auto rollback (직전 정비전 100%)
```

- **키 없는 인증**: GitHub Actions → OIDC → Workload Identity Federation → 배포 SA. 장기 서비스 계정 키 파일을 만들지 않는다.
- **사용자 영향 0인 검증**: 카나리 리비전은 트래픽 태그만 받으므로, 스모크가 실패해도 운영 사용자는 영향받지 않는다.
- 스모크 실패 시 **자동 롤백** 단계(`if: failure()`)가 실행된다.

## 2. 수동 롤백 (장애 중)

### 2-1. 가장 빠른 방법 — gcloud 한 줄 (약 20~40초)

```bash
# 직전 리비전으로 100% 트래픽 이동
PREV=$(gcloud run revisions list --service seogarok-api --region asia-northeast3 \
  --sort-by '~metadata.creationTimestamp' --format 'value(metadata.name)' | sed -n '2p')
gcloud run services update-traffic seogarok-api --region asia-northeast3 \
  --to-revisions "${PREV}=100"
```

배포 스크립트로도 동일하게:

```bash
SERVICE=seogarok-api REGION=asia-northeast3 bash scripts/deploy_canary.sh rollback
```

### 2-2. 워크플로에서 롤백

Actions → **deploy-cloudrun** → Run workflow →
`rollback_to` 에 `previous` 또는 특정 리비전 이름(`seogarok-api-00042-abc`)을 입력.

### 2-3. 롤백 확인

```bash
bash scripts/smoke.sh "$(gcloud run services describe seogarok-api \
  --region asia-northeast3 --format 'value(status.url)')"
gcloud run services describe seogarok-api --region asia-northeast3 \
  --format 'table(status.traffic[].revisionName, status.traffic[].percent)'
```

> **중요 — 서비스 복구 ≠ 알림 해제.** 트래픽을 되돌려 200이 나와도, SLO 알림은 **rate 윈도우(1h·6h)** 때문에
> 수 분~수십 분 더 firing 상태로 남는다. 이는 정상이며, "복구 판정은 알림 resolve가 아니라 200 응답 복귀"로 한다.
> (관련: [chaos-drill.md](chaos-drill.md) §5)

## 3. 장애 판단 → 롤백 결정 (5분 규칙)

| 신호 | 확인 | 판단 |
|---|---|---|
| `/readyz` 503 | `docs == vectors` 인지 | 인덱스 문제면 롤백보다 재배포(이미지 재빌드) |
| 5xx 급증 + 최근 10분 내 배포 있음 | Grafana 에러율 / `seogarok_http_requests_total{status=~"5.."}` | **즉시 롤백** |
| p95 급증 | `seogarok_search_stage_seconds` 로 단계 확인 | 배포 직후면 롤백, 아니면 리소스/카오스 확인 |
| 카나리 스모크 실패 | Actions 로그 | 자동 롤백됨(사용자 영향 없음) |

**롤백 후 해야 할 일**
1. 배포 파이프라인 일시 중지(필요 시) — `concurrency` 로 이미 직렬화됨
2. 원인 리비전의 이미지 digest 기록
3. [postmortem 템플릿](../postmortem/TEMPLATE.md)으로 회고 작성 (**비난 없이**, 타임라인은 증거 기반)
4. 재발 방지 항목을 액션 아이템으로 등록

## 4. Terraform 과 CD 의 충돌 방지

Terraform 이 이미지와 트래픽을 관리하면, CD/롤백이 바꾼 값을 `terraform apply` 가 **되돌려버린다.**
그래서 `google_cloud_run_v2_service` 에 `lifecycle.ignore_changes` 를 걸었다.

```hcl
lifecycle {
  ignore_changes = [
    template[0].containers[0].image,  # 이미지 태그는 CD 가 관리
    traffic,                          # 트래픽 비율은 롤백이 관리
    client, client_version,
  ]
}
```

**역할 분담**

| 대상 | 관리 주체 |
|---|---|
| 서비스/리전/스케일링/환경변수/프로브/IAM | **Terraform** |
| 컨테이너 이미지 태그 | **GitHub Actions** |
| 트래픽 비율(카나리·롤백) | **배포 스크립트 / gcloud** |

## 5. 무료 티어 비용 메모 (Cloud Run)

| 항목 | 무료 한도(월) | 이 서비스 설정 |
|---|---|---|
| 요청 | 200만 | 데모 수준 |
| vCPU-초 | 18만 | cpu=1, min_instances=0 (유휴 시 0) |
| GiB-초 | 36만 | memory 2Gi → **요청 처리 시간만 과금** |
| Artifact Registry | 0.5GB 무료 | 이미지 1.36GB → 초과분 소액(월 수백 원) |

- **min_instances=0** 이므로 트래픽이 없으면 비용이 0에 수렴한다.
- 단, cold start 가 **10~20초**(이미지 1.36GB + 모델 로드) 발생한다.
  데모에서 체감이 중요하면 `min_instances=1`(월 수천 원 수준)로 올린다 — 대신 무료 한도 소모.
- 결제 계정 연결은 필요하지만, 무료 한도 내에서는 청구 0원.

## 6. 사전 준비 (1회)

```bash
# 1) API 활성화
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  iamcredentials.googleapis.com sts.googleapis.com

# 2) Terraform 적용 (state 버킷 먼저)
gcloud storage buckets create "gs://${TF_STATE_BUCKET}" --location=asia-northeast3
cd terraform
cp terraform.tfvars.example terraform.tfvars   # project_id, github_repo 채우기
terraform init -backend-config="bucket=${TF_STATE_BUCKET}" -backend-config="prefix=seoga/state"
terraform plan
terraform apply
terraform output github_actions_vars            # GitHub Variables 로 등록
```

GitHub 저장소 → Settings → Secrets and variables → **Variables** 에 등록:

| 이름 | 값 |
|---|---|
| `GCP_WIF_PROVIDER` | `projects/.../locations/global/workloadIdentityPools/github/providers/github-oidc` |
| `GCP_DEPLOY_SA` | `seogarok-api-deploy@PROJECT.iam.gserviceaccount.com` |
| `GCP_PROJECT` | 프로젝트 ID |
| `GCP_REGION` | `asia-northeast3` |
| `CLOUD_RUN_SERVICE` | `seogarok-api` |
| `IMAGE_REPO` | `asia-northeast3-docker.pkg.dev/PROJECT/seogarok/seogarok-api` |
| `TF_STATE_BUCKET` | state 버킷 이름 |

Environment `production`, `production-infra` 를 만들고 **Required reviewers** 를 걸면 apply/배포에 승인 게이트가 생긴다.

## 7. 비용 가드레일 & 정리 (teardown)

**원칙: 이 워크로드는 월 $0 이 목표다.** 무료 한도 안에서만 돌리고, 한도를 넘길 구조를 미리 막아둔다.

### 7-1. 예산 알림 (권장, 1회 설정)

```bash
gcloud billing budgets create \
  --billing-account="$(gcloud billing accounts list --format='value(name)' | head -1)" \
  --display-name="seoga-cap" \
  --budget-amount=5USD \
  --threshold-rule=percent=0.5 \
  --threshold-rule=percent=1.0
```

5달러 예산의 50%/100%에서 메일 알림. 실수로 트래픽이 폭주해도 조기에 안다.

### 7-2. 비용을 0으로 유지하는 스위치

| 목적 | 설정 | 효과 |
|---|---|---|
| 유휴 시 0원 | `min_instances = 0` (기본) | 인스턴스 0 → 과금 0 |
| 폭주 방지 | `max_instances = 2` (기본) | 상한 고정 |
| 이미지 비용 | Artifact Registry `cleanup_policy`(최근 10개 유지) | 자동 정리 |
| 요청 단가 | `cpu_idle = true` | 요청 없을 때 CPU 회수 |

### 7-3. 실측 비용 감각

| 항목 | 무료 한도(월) | 이 서비스 |
|---|---|---|
| 요청 | 200만 | 데모 수천 건 |
| vCPU-초 | 18만 | 유휴 0, 데모 수 분 |
| GiB-초 | 36만 | memory 2Gi × 실행 시간만 |
| Artifact Registry | 0.5GB | 이미지 1.36GB → **초과 0.86GB ≈ 월 $0.09** |
| 이그레스 | 1GB(북미) | 데모 수준 무시 가능 |

→ **사실상 0원**. 유일한 실비가 이미지 저장소 9센트.

### 7-4. 완전 정리

```bash
cd terraform
terraform destroy          # Cloud Run / Artifact Registry / SA / WIF 전부 삭제

# state 버킷은 Terraform 이 관리하지 않으므로 수동 삭제
gcloud storage rm -r "gs://${TF_STATE_BUCKET}"
```

> `ignore_changes` 는 **apply 시 차이를 무시**하는 옵션이고, `destroy` 는 리소스 자체를 지운다.
> 즉 정리할 때 이미지/트래픽 ignore 설정이 방해하지 않는다.

## 8. 관련 문서

- SLO/알림: [../SRE.md](../SRE.md)
- 배포 후 관측: [Grafana](http://localhost:3001/d/seogarok-sre) (로컬), Prometheus `/alerts`
- 사고 회고: [../postmortem/TEMPLATE.md](../postmortem/TEMPLATE.md)
- 인덱스 갱신(재배포): [index-stale.md](index-stale.md)
- 커스텀 도메인: [domain-cloudflare.md](domain-cloudflare.md)

## 9. 실전 기록 (2026-10-28 첫 배포)

| 항목 | 내용 |
|---|---|
| 라이브 URL | https://seogarok.com |
| 프로젝트 | `seoga-prod` (asia-northeast3) |
| 검증 | `scripts/smoke.sh` **5/5 PASS**, `/readyz` 4,865/4,865 |

배포 중 실제로 만난 문제 3건과 수정:

1. **OOM (2Gi → 4Gi)** — 임베딩 모델 포함 프로세스가 2Gi에서 죽음. `memory` 기본값을 `4Gi`로.
2. **`/healthz` 가 Cloud Run 전면(GFE) 예약 경로** → 외부 요청은 404. **`/livez` 별칭**을 추가하고
   startup/liveness probe 와 smoke 스크립트를 `/livez` 로 변경. (로컬은 둘 다 동작)
3. **비용** — `min_instances=1` + 4Gi 는 월 $25+. **`min_instances=0`(scale-to-zero)** 로 낮춰
   요청 시간만 과금(데모 수준 월 $0~1). 대신 콜드스타트 8~12초.

로컬 apply 는 ADC 없이도 가능:
`terraform apply -var access_token=$(gcloud auth print-access-token)` (CI 는 WIF 사용).