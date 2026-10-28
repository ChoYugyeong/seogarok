variable "project_id" {
  description = "GCP 프로젝트 ID"
  type        = string
}

variable "access_token" {
  description = "로컬 1회성 apply 용 gcloud 액세스 토큰 (비우면 ADC/WIF 사용)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "artifact_region" {
  description = "컨테이너 이미지 저장소(Artifact Registry) 리전. Cloud Run 리전과 분리 가능"
  type        = string
  default     = "asia-northeast3"
}

variable "region" {
  description = "Cloud Run 리전 (도쿄: 커스텀 도메인 매핑 지원. 서울은 미지원)"
  type        = string
  default     = "asia-northeast1" # 도쿄
}

variable "env" {
  description = "환경 이름 (라벨/리소스 접미사)"
  type        = string
  default     = "prod"
}

variable "service_name" {
  description = "Cloud Run 서비스 이름"
  type        = string
  default     = "seogarok-api"
}

variable "image" {
  description = "배포할 컨테이너 이미지 (예: asia-northeast3-docker.pkg.dev/PROJECT/seoga/seoga-api:SHA)"
  type        = string
  default     = ""
}

variable "github_repo" {
  description = "GitHub 저장소 (owner/repo). OIDC 로 이 저장소만 배포 SA 를 쓸 수 있게 한다"
  type        = string
}

variable "min_instances" {
  description = "최소 인스턴스. 0 = scale-to-zero(비용 ~0, 콜드스타트 8~12초). 1 = 상시 대기(월 $25+)"
  type        = number
  default     = 0
}

variable "max_instances" {
  description = "최대 인스턴스 (비용 폭주 방지 상한)"
  type        = number
  default     = 2
}

variable "cpu" {
  description = "컨테이너 vCPU"
  type        = string
  default     = "1"
}

variable "memory" {
  description = "컨테이너 메모리. 2Gi 는 OOM(실측), 4Gi 필요"
  type        = string
  default     = "4Gi"
}

variable "concurrency" {
  description = "인스턴스당 동시 요청 수 (임베더 단일 락 고려해 낮게)"
  type        = number
  default     = 8
}

variable "allow_unauthenticated" {
  description = "공개 접근 허용 (데모). 운영에서는 false 로 두고 IAP/LB 인증 권장"
  type        = bool
  default     = true
}
variable "www_domain" {
  description = "추가 서브도메인 (예: www.seogarok.com). 비우면 생성하지 않음"
  type        = string
  default     = ""
}

variable "custom_domain" {
  description = "커스텀 도메인 (예: seoga.example.com). 비우면 생성하지 않음"
  type        = string
  default     = ""
}