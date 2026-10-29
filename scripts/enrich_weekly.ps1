<#
.SYNOPSIS
  서가록 데이터 주간 보강 배치 (로컬/수동 실행).

.DESCRIPTION
  - YES24 API로 누락 설명 보강 (기본 1,200권)
  - YES24 HTML 상세페이지로 추가 보강 (기본 800권, robots 준수)
  - 대체 소스(Google Books/네이버)는 환경변수 키가 있을 때만 자동 시도
  - fallback 스냅샷 재생성 + 커버리지 출력
  - Windows 작업 스케줄러 등록 예:
    schtasks /Create /TN "seogarok-enrich-weekly" /SC WEEKLY /D SUN /ST 04:30 ^
      /TR "pwsh -NoProfile -File C:\Dev\seoga\scripts\enrich_weekly.ps1"
#>
param(
  [int]$ApiLimit = 1200,
  [int]$HtmlLimit = 800,
  [int]$Workers = 6,
  [switch]$SkipHtml,
  [int]$HtmlTimeout = 900,
  [int]$GoogleLimit = 600
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:PYTHONIOENCODING = 'utf-8'
Set-Location (Split-Path $PSScriptRoot -Parent)

# .env 에서 키 로드 (없으면 환경변수 사용)
if (Test-Path .env) {
  Get-Content .env -Encoding utf8 | ForEach-Object {
    if ($_ -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)$') {
      $name = $Matches[1]
      $value = $Matches[2].Trim().Trim('"')
      if (-not [Environment]::GetEnvironmentVariable($name)) {
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
      }
    }
  }
}

if (-not $env:YES24_API_KEY) { throw "YES24_API_KEY 가 없습니다 (.env 또는 환경변수)" }
$env:PYTHONIOENCODING = 'utf-8'

Write-Host "[weekly] 0/4 GCS 캐시 복원 (없으면 신규)"
python scripts\enrich_cache_sync.py pull

Write-Host "[weekly] 1/4 YES24 API 설명 보강 (limit=$ApiLimit, workers=$Workers)"
python -m ingest.books.enrich_descriptions --limit $ApiLimit --workers $Workers

if (-not $SkipHtml) {
  Write-Host "[weekly] 2/4 YES24 HTML 상세 보강 (limit=$HtmlLimit, timeout=${HtmlTimeout}s)"
  python -m ingest.books.enrich_descriptions --html --skip-api --limit $HtmlLimit --html-workers 3 --timeout $HtmlTimeout
} else {
  Write-Host "[weekly] 2/4 HTML 보강 건너뜀"
}

Write-Host "[weekly] 3/4 Google Books 제목 보강 (limit=$GoogleLimit, 키 필요)"
if ($env:GOOGLE_BOOKS_API_KEY) {
  python -m ingest.books.enrich_descriptions --google-title --limit $GoogleLimit --workers 3
} else {
  Write-Host "  GOOGLE_BOOKS_API_KEY 없음 — 건너뜀"
}

Write-Host "[weekly] 4/4 fallback 스냅샷 재생성 + 커버리지"
python scripts/rebuild_fallback.py
python -m ingest.books.desc_coverage

Write-Host "[weekly] GCS 캐시 아카이브 업로드"
python scripts\enrich_cache_sync.py push

Write-Host "[weekly] 완료. 커밋하려면:"
Write-Host "  git add data/catalog_fallback.jsonl.gz && git commit -m 'data: 주간 설명 보강' && git push"
