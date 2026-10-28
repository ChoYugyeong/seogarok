#!/usr/bin/env bash
# Cloud Run 카나리 배포 / 승격 / 롤백.
#   ./scripts/deploy_canary.sh deploy     # 새 리비전 배포 (트래픽 0%, tag=canary)
#   ./scripts/deploy_canary.sh promote    # 카나리 → 100% 트래픽
#   ./scripts/deploy_canary.sh rollback   # 직전 정상 리비전으로 100% 롤백
#   ./scripts/deploy_canary.sh status     # 리비전/트래픽 현황
#
# 필요 env: SERVICE, REGION / deploy 시 IMAGE
set -euo pipefail

SERVICE="${SERVICE:?SERVICE 환경변수가 필요합니다 (예: seoga-api)}"
REGION="${REGION:?REGION 환경변수가 필요합니다 (예: asia-northeast3)}"
IMAGE="${IMAGE:-}"

log() { printf '[deploy] %s\n' "$*"; }

revisions_desc() {
  gcloud run revisions list \
    --service "$SERVICE" --region "$REGION" \
    --sort-by '~metadata.creationTimestamp' \
    --format 'value(metadata.name)'
}

current_revision() { revisions_desc | sed -n '1p'; }
previous_revision() { revisions_desc | sed -n '2p'; }

canary_url() {
  # jq 가 없는 Windows/Git Bash 환경도 지원
  local json
  json=$(gcloud run services describe "$SERVICE" --region "$REGION" --format json)
  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$json" | jq -r '[.status.traffic[]? | select(.tag == "canary")][0].url // empty'
  else
    printf '%s' "$json" | python -c 'import json,sys; d=json.load(sys.stdin); t=[x.get("url") for x in (d.get("status",{}).get("traffic") or []) if x.get("tag")=="canary"]; print(t[0] if t else "")'
  fi
}

service_url() {
  gcloud run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)'
}

do_deploy() {
  [ -n "$IMAGE" ] || { echo "IMAGE 환경변수가 필요합니다" >&2; exit 2; }
  log "새 리비전 배포 (트래픽 없음): $IMAGE"
  gcloud run deploy "$SERVICE" \
    --image "$IMAGE" \
    --region "$REGION" \
    --no-traffic \
    --tag canary \
    --quiet

  local url
  url="$(canary_url)"
  [ -n "$url" ] || { echo "카나리 URL을 찾지 못했습니다" >&2; exit 3; }
  log "카나리 URL: $url"
  # 워크플로에서 쓰도록 파일로도 남긴다
  echo "$url" > "${CANARY_URL_FILE:-/tmp/canary_url.txt}"
}

do_promote() {
  log "카나리 트래픽을 100% 로 승격"
  gcloud run services update-traffic "$SERVICE" --region "$REGION" --to-latest --quiet
  log "서비스 URL: $(service_url)"
}

do_rollback() {
  local prev
  prev="$(previous_revision)"
  if [ -z "$prev" ]; then
    echo "롤백할 이전 리비전이 없습니다 (첫 배포)." >&2
    exit 4
  fi
  log "롤백: $prev 100%"
  gcloud run services update-traffic "$SERVICE" --region "$REGION" \
    --to-revisions "${prev}=100" --quiet
  log "롤백 완료. 현재 리비전: $(current_revision)"
}

do_status() {
  log "서비스: $SERVICE / $REGION"
  gcloud run services describe "$SERVICE" --region "$REGION" \
    --format 'table(status.traffic[].revisionName, status.traffic[].percent, status.traffic[].tag)'
  log "리비전 (최신순)"
  revisions_desc | head -5
}

case "${1:-}" in
  deploy)   do_deploy ;;
  promote)  do_promote ;;
  rollback) do_rollback ;;
  status)   do_status ;;
  *) echo "usage: $0 {deploy|promote|rollback|status}" >&2; exit 1 ;;
esac
