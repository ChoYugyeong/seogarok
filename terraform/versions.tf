terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # state backend 는 로컬/CI 에 따라 달라지므로 이 파일에 고정하지 않는다.
  #  - 로컬: backend 없이 local state (terraform.tfstate, gitignore)
  #  - CI  : .github/workflows/terraform.yml 이 backend.tf 를 생성해 GCS 사용
  # 버킷 생성 방법: docs/runbooks/deploy-rollback.md §6
}

provider "google" {
  project = var.project_id
  region  = var.region

  # ADC 없이 로컬에서 1회성 apply 할 때만 사용 (gcloud auth print-access-token).
  # CI 에서는 Workload Identity Federation 으로 인증하므로 비워 둔다.
  access_token = var.access_token != "" ? var.access_token : null
}

locals {
  labels = {
    app     = "seoga"
    managed = "terraform"
    env     = var.env
  }
}
