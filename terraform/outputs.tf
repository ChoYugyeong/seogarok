output "service_url" {
  description = "Cloud Run 서비스 URL"
  value       = google_cloud_run_v2_service.api.uri
}

output "image_repository" {
  description = "이미지를 push 할 Artifact Registry 경로"
  value       = "${var.artifact_region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "service_name" {
  value = google_cloud_run_v2_service.api.name
}

output "region" {
  value = var.region
}

output "runtime_service_account" {
  value = google_service_account.runtime.email
}

# --- GitHub Actions 설정에 넣을 값들 (Settings → Variables) ---
output "github_actions_vars" {
  description = "GitHub 저장소 Variables 로 등록할 값"
  value = {
    GCP_WIF_PROVIDER  = google_iam_workload_identity_pool_provider.github.name
    GCP_DEPLOY_SA     = google_service_account.deploy.email
    GCP_PROJECT       = var.project_id
    GCP_REGION        = var.region
    CLOUD_RUN_SERVICE = google_cloud_run_v2_service.api.name
    IMAGE_REPO        = "${var.artifact_region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}/${var.service_name}"
  }
}
output "custom_domain_records" {
  description = "커스텀 도메인 연결 시 등록할 DNS 레코드"
  value = var.custom_domain == "" ? [] : [
    for r in google_cloud_run_domain_mapping.custom[0].status[0].resource_records :
    { name = r.name, type = r.type, rrdata = r.rrdata }
  ]
}

output "www_domain_records" {
  description = "www 서브도메인 연결 시 등록할 DNS 레코드"
  value = var.www_domain == "" ? [] : [
    for r in google_cloud_run_domain_mapping.www[0].status[0].resource_records :
    { name = r.name, type = r.type, rrdata = r.rrdata }
  ]
}

output "reports_bucket" {
  description = "가용성 제보 원본 GCS 버킷"
  value       = google_storage_bucket.reports.name
}
