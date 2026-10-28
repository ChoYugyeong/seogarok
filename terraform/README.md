# terraform — seoga API 인프라 (Cloud Run)

**한 줄:** Cloud Run + Artifact Registry + GitHub OIDC(키 없는 배포)를 Terraform 으로 관리한다.
컨테이너 **이미지 태그와 트래픽 비율은 Terraform 이 관리하지 않는다**(CD/롤백 담당, `ignore_changes`).

## 리소스

| 리소스 | 목적 |
|---|---|
| `google_artifact_registry_repository.images` | 이미지 저장소 (최근 10개만 유지) |
| `google_cloud_run_v2_service.api` | API 서비스 — startup/liveness probe `/healthz`, min 0 / max 2, cpu_idle |
| `google_service_account.runtime` | 런타임 SA (logging.logWriter) |
| `google_iam_workload_identity_pool.github` + provider | GitHub OIDC — **이 저장소만** 배포 SA 로 토큰 교환 가능 |
| `google_service_account.deploy` + IAM | run.admin / artifactregistry.writer / iam.serviceAccountUser |
| `google_cloud_run_v2_service_iam_member.public` | 공개 접근(데모, `allow_unauthenticated=false` 로 끌 수 있음) |

## 사용

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # project_id, github_repo 수정

# 1) 자격증명 없이 검증 (CI 의 validate job 과 동일)
terraform init -backend=false
terraform validate

# 2) 실제 plan/apply (state 버킷 필요 — docs/runbooks/deploy-rollback.md §6)
terraform init -backend-config="bucket=$TF_STATE_BUCKET" -backend-config="prefix=seoga/state"
terraform plan
terraform apply

# 3) GitHub Actions Variables 로 붙여넣을 값
terraform output github_actions_vars
```

`terraform.tfvars` 와 `*.tfstate` 는 커밋하지 않는다(`.gitignore`). `.terraform.lock.hcl` 은 커밋한다(재현성).

## 설계 메모

- **왜 image 를 ignore 하나** — CD 가 git SHA 태그로 배포하는데 Terraform 이 이미지 필드를 관리하면
  다음 `apply` 때 옛 이미지로 되돌린다. 그래서 `template[0].containers[0].image` 를 ignore.
  (`image` 변수는 최초 bootstrap 용으로만 쓰이고, 없으면 placeholder 태그를 쓴다.)
- **왜 traffic 을 ignore 하나** — 긴급 롤백(`gcloud run services update-traffic`)이 만든 상태를
  Terraform 이 "원복"하지 못하게 하기 위해서다.
- **min_instances=0** — 무료 티어/비용 우선. cold start 10~20초를 감수.
  체감이 중요하면 `min_instances=1`(월 수천 원 수준).
- **memory 2Gi** — 임베딩 모델 + sqlite-vec + numpy 를 포함한 프로세스가 약 1.8GiB 를 쓴다.
- **SEOG_CHAOS=0** — 운영에서는 카오스 엔드포인트가 404. 게임데이는 로컬 compose 로 수행한다.
