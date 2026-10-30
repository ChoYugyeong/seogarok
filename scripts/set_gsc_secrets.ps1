<#
.SYNOPSIS
  .env의 GSC_* 값을 GitHub Secret으로 등록 (값 출력 없음).
#>
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

$envFile = Join-Path (Get-Location) '.env'
if (-not (Test-Path $envFile)) { throw ".env 없음" }
$map = @{}
Get-Content $envFile -Encoding utf8 | ForEach-Object {
  if ($_ -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)$') { $map[$Matches[1]] = $Matches[2].Trim().Trim('"') }
}
foreach ($k in @('GSC_CLIENT_ID','GSC_CLIENT_SECRET','GSC_REFRESH_TOKEN')) {
  if (-not $map.ContainsKey($k) -or -not $map[$k]) { Write-Host "[skip] $k 없음"; continue }
  $map[$k] | gh secret set $k 2>&1 | Out-Null
  if ($LASTEXITCODE -eq 0) { Write-Host "[ok] $k" } else { Write-Host "[FAIL] $k" }
}
Write-Host "확인: gh secret list"
