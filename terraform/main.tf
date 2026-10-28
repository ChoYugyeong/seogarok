# -----------------------------------------------
# Artifact Registry (이미지 저장소)
# -----------------------------------------------
resource "google_artifact_registry_repository" "images" {
  location      = var.artifact_region
  repository_id = "seogarok"
  description   = "seoga-api container images"
  format        = "DOCKER"
  labels        = local.labels

  # 오래된 이미지는 정리 정책으로 비용/쿼터 관리
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }
}

# -----------------------------------------------
# 런타임 서비스 계정 (Cloud Run 이 사용)
# -----------------------------------------------
resource "google_service_account" "runtime" {
  account_id   = "${var.service_name}-runtime"
  display_name = "seoga-api runtime"
}

# -----------------------------------------------
# Cloud Run v2 서비스
# -----------------------------------------------
resource "google_cloud_run_v2_service" "api" {
  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  labels   = local.labels

  template {
    service_account = google_service_account.runtime.email
    timeout         = "60s"

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = var.image != "" ? var.image : "${var.region}-docker.pkg.dev/${var.project_id}/seoga/${var.service_name}:bootstrap"

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
        cpu_idle = true # 요청 없을 때 CPU 회수 (비용 절감)
      }

      env {
        name  = "SEOG_CHAOS"
        value = "0" # 운영에서는 카오스 비활성 → /api/_chaos 는 404
      }
      env {
        name  = "SEOG_EMBED"
        value = "model2vec"
      }
      env {
        # 운영 모드: 실수집 가용성만 표시하고 나머지는 "미확인" (허위 표시 금지)
        name  = "SEOG_AVAIL"
        value = "real"
      }
      env {
        name  = "PYTHONUNBUFFERED"
        value = "1"
      }
      env {
        # ③ 온디맨드 조회 (카탈로그 미수록 책) — 비어 있으면 기능 비활성
        name  = "YES24_API_KEY"
        value = var.yes24_api_key
      }
      env {
        # ① 제보 원본 영속화 버킷
        name  = "REPORTS_BUCKET"
        value = google_storage_bucket.reports.name
      }

      # 이미지에 인덱스를 구워두므로 기동만 확인하면 된다
      startup_probe {
        http_get {
          path = "/livez"
        }
        # 서울 AR → 도쿄 리전 이미지(1.36GB) 당겨오는 시간을 고려한 여유 설정
        initial_delay_seconds = 20
        timeout_seconds       = 5
        period_seconds        = 10
        failure_threshold     = 30
      }

      liveness_probe {
        http_get {
          path = "/livez"
        }
        period_seconds    = 30
        timeout_seconds   = 3
        failure_threshold = 3
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  lifecycle {
    # 이 두 가지는 Terraform 이 아니라 CI/CD 가 관리한다.
    #  - image: GitHub Actions 가 SHA 태그로 배포
    #  - traffic: 긴급 롤백 시 gcloud 로 트래픽을 이전 리비전으로 되돌림
    # 여기서 ignore 하지 않으면 terraform apply 가 롤백을 "원복"해버린다.
    ignore_changes = [
      template[0].containers[0].image,
      traffic,
      client,
      client_version,
    ]
  }

  # 실패한 리비전을 정리/재생성할 수 있게 한다(개인 프로젝트).
  # 운영에서 실수 삭제가 걱정되면 true 로 두고, 재생성 시 `terraform state rm` 후 apply.
  deletion_protection = false
}

# 공개 접근 (데모). 운영에서는 false 로 두고 LB/IAP 인증을 붙인다.
resource "google_cloud_run_v2_service_iam_member" "public" {
  count    = var.allow_unauthenticated ? 1 : 0
  name     = google_cloud_run_v2_service.api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# 로그는 기본적으로 Cloud Logging 으로 수집된다 (stdout JSON 1줄/요청)
resource "google_project_iam_member" "runtime_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

# -----------------------------------------------
# GitHub Actions OIDC (키 없는 배포)
#  - 장기 서비스 계정 키를 만들지 않는다.
#  - 이 저장소의 워크플로만 배포 SA 로 토큰을 교환할 수 있다.
# -----------------------------------------------
resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
  description               = "OIDC pool for GitHub Actions (keyless deploys)"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  attribute_condition = "assertion.repository == \"${var.github_repo}\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "deploy" {
  account_id   = "${var.service_name}-deploy"
  display_name = "seoga-api deploy (GitHub Actions)"
}

resource "google_service_account_iam_member" "deploy_wif" {
  service_account_id = google_service_account.deploy.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}

# 배포 SA 권한: Cloud Run 배포 + 이미지 push
resource "google_project_iam_member" "deploy_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_project_iam_member" "deploy_ar_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_project_iam_member" "deploy_sa_user" {
  project = var.project_id
  role    = "roles/iam.serviceAccountUser"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}
# -----------------------------------------------
# 커스텀 도메인 (선택)
#  DNS 소유 확인이 선행되어야 한다: `gcloud domains verify <domain>`
#  그 다음 var.custom_domain 설정 → apply → 출력된 DNS 레코드 등록
# -----------------------------------------------
resource "google_cloud_run_domain_mapping" "custom" {
  count    = var.custom_domain != "" ? 1 : 0
  name     = var.custom_domain
  location = var.region

  metadata {
    namespace = var.project_id
  }

  spec {
    route_name = google_cloud_run_v2_service.api.name
  }
}

# -----------------------------------------------
# www 서브도메인 (선택) — 루트 도메인과 별도 매핑
#  DNS: CNAME www -> ghs.googlehosted.com (DNS only)
# -----------------------------------------------
resource "google_cloud_run_domain_mapping" "www" {
  count    = var.www_domain != "" ? 1 : 0
  name     = var.www_domain
  location = var.region

  metadata {
    namespace = var.project_id
  }

  spec {
    route_name = google_cloud_run_v2_service.api.name
  }
}

# -----------------------------------------------
# 제보 영속화 버킷 (컨테이너 FS 는 인메모리라 재시작 시 소실)
# -----------------------------------------------
resource "google_storage_bucket" "reports" {
  name                        = var.reports_bucket
  location                    = var.artifact_region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  lifecycle_rule {
    condition {
      age = 730
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_storage_bucket_iam_member" "runtime_reports" {
  bucket = google_storage_bucket.reports.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.runtime.email}"
}
