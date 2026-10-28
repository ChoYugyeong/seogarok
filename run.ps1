# 서가(seoga) 실행 스크립트
#   .\run.ps1            : 인덱스가 없으면 만들고 서버 기동
#   .\run.ps1 -Reindex   : 카탈로그/공지를 다시 읽어 인덱스 재구축
#   .\run.ps1 -Bench     : 검색 벤치마크만 실행
param(
  [switch]$Reindex,
  [switch]$Bench,
  [int]$Port = 8100
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"

if ($Bench) {
  python -m benchmarks.bench_search
  exit $LASTEXITCODE
}

$catalog = "data/catalog.jsonl"
$hasCatalog = Test-Path $catalog
$hasDb = Test-Path "data/seoga.db"

if ($Reindex -or -not $hasDb) {
  if (-not $hasCatalog) {
    Write-Host "[run] $catalog 없음 -> seed(data/seed_catalog.jsonl)로 인덱스 생성" -ForegroundColor Yellow
  }
  python -m server.sync
  if ($LASTEXITCODE -ne 0) { throw "sync 실패" }
}

Write-Host "[run] http://127.0.0.1:$Port" -ForegroundColor Green
python -m server.app --port $Port
