#!/usr/bin/env pwsh
# 로컬 데모 스택을 Cloudflare Quick Tunnel 로 잠깐 외부에 공개한다.
#   .\scripts\share_demo.ps1                 # 앱(8100) 공개
#   .\scripts\share_demo.ps1 -Grafana        # Grafana(3001) 공개
#   .\scripts\share_demo.ps1 -Stop           # 터널 종료
#
# 전제: Docker Desktop 실행 중 + 로컬 스택이 떠 있어야 함(docker compose up -d).
# 주의: Quick Tunnel 은 인증이 없다. 데모 직후 반드시 -Stop 할 것.
#       (compose 기본값 SEOG_CHAOS=1 이면 /api/_chaos 가 공개되므로 시간을 짧게)
param(
  [int]$Port = 8100,
  [int]$GrafanaPort = 3001,
  [switch]$Grafana,
  [switch]$Stop,
  [string]$Name = "seoga-demo-tunnel"
)

# 네이티브 도구(docker)의 stderr 가 종료 오류로 승격되지 않게 한다 (PS 5.1 호환)
$ErrorActionPreference = "Continue"
$target = if ($Grafana) { $GrafanaPort } else { $Port }

function Remove-Tunnel {
  docker rm -f $Name *> $null
}

if ($Stop) {
  Remove-Tunnel
  Write-Host "[share] 터널 종료" -ForegroundColor Yellow
  exit 0
}

Remove-Tunnel

Write-Host "[share] http://host.docker.internal:$target 를 공개 URL 로 노출 중..." -ForegroundColor Cyan
docker run -d --name $Name --rm cloudflare/cloudflared:latest `
  tunnel --no-autoupdate --url "http://host.docker.internal:$target" *> $null
if ($LASTEXITCODE -ne 0) {
  Write-Host "[share] cloudflared 컨테이너 기동 실패 (Docker Desktop 실행 여부 확인)" -ForegroundColor Red
  exit 1
}

$url = $null
for ($i = 1; $i -le 25; $i++) {
  Start-Sleep -Seconds 1
  $log = (docker logs $Name 2>&1 | Out-String)
  $m = [regex]::Match($log, 'https://[a-z0-9-]+\.trycloudflare\.com')
  if ($m.Success) { $url = $m.Value; break }
}

if (-not $url) {
  Write-Host "[share] URL 을 얻지 못했습니다. 마지막 로그:" -ForegroundColor Red
  docker logs $Name 2>&1 | Select-Object -Last 12
  Remove-Tunnel
  exit 1
}

Write-Host ""
Write-Host "  공개 URL: $url" -ForegroundColor Green
if (-not $Grafana) {
  Write-Host "  헬스: $url/healthz"
  Write-Host "  검색: $url/api/search?q=한강"
} else {
  Write-Host "  Grafana: $url/d/seoga-sre"
}
Write-Host ""
Write-Host "  종료: .\scripts\share_demo.ps1 -Stop" -ForegroundColor Yellow
Write-Host "  (Quick Tunnel 은 인증이 없습니다. 데모가 끝나면 즉시 종료하세요.)" -ForegroundColor DarkYellow
