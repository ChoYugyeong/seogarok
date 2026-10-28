#!/usr/bin/env pwsh
# 게임데이(카오스 드릴) 스크립트 — SRE 포트폴리오 데모용
#   .\scripts\game_day.ps1 -Scenario all
#   .\scripts\game_day.ps1 -Scenario reset
param(
  [ValidateSet("latency", "error", "all", "reset", "status")]
  [string]$Scenario = "all",
  [string]$Base = "http://127.0.0.1:8100"
)

function Invoke-Chaos($body) {
  $json = $body | ConvertTo-Json -Compress
  try {
    $r = Invoke-RestMethod -Method Post -Uri "$Base/api/_chaos" -ContentType "application/json" -Body $json -TimeoutSec 5
    Write-Host "[chaos] $json -> $($r | ConvertTo-Json -Compress)" -ForegroundColor Yellow
  } catch {
    Write-Host "[chaos] 실패: $($_.Exception.Message) (SEOG_CHAOS=1 인지 확인)" -ForegroundColor Red
  }
}

switch ($Scenario) {
  "latency" { Invoke-Chaos @{ latency_ms = 400; error_rate = 0 } }
  "error"   { Invoke-Chaos @{ latency_ms = 0;   error_rate = 0.4 } }
  "all" {
    Invoke-Chaos @{ latency_ms = 400; error_rate = 0.3 }
    Write-Host "[game-day] 2~3분 뒤 Prometheus http://localhost:9090/alerts 에서" -ForegroundColor Cyan
    Write-Host "           SeogaSearchLatencyP95High / SeogaErrorBudgetBurnFast 발화를 확인하세요." -ForegroundColor Cyan
  }
  "reset" { Invoke-Chaos @{ latency_ms = 0; error_rate = 0 } }
  "status" {
    try { Invoke-RestMethod -Uri "$Base/api/_chaos" -TimeoutSec 5 | ConvertTo-Json -Compress } catch { "chaos endpoint 비활성" }
  }
}
