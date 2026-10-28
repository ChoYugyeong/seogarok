#!/usr/bin/env bash
# 배포 후 스모크 테스트. CI/CD 와 로컬에서 공통 사용.
#   ./scripts/smoke.sh https://seoga-api-xxxx.a.run.app
set -euo pipefail

BASE_URL="${1:?usage: smoke.sh <base-url>}"
BASE_URL="${BASE_URL%/}"
TRIES="${SMOKE_TRIES:-20}"
SLEEP="${SMOKE_SLEEP:-3}"

pass=0
fail=0

ok()   { pass=$((pass + 1)); printf '  [PASS] %s\n' "$1"; }
bad()  { fail=$((fail + 1)); printf '  [FAIL] %s\n' "$1"; }

fetch() {
  # 마지막 인자: curl 옵션 외의 경로
  local path="$1"
  curl -sS -m 15 -w '\n%{http_code}' "${BASE_URL}${path}" || true
}

echo "[smoke] base=$BASE_URL"

# 1) 기동 대기: /healthz 가 200 이 될 때까지
code=""
for i in $(seq 1 "$TRIES"); do
  code=$(fetch /livez | tail -n1)
  [ "$code" = "200" ] && break
  sleep "$SLEEP"
done
if [ "$code" = "200" ]; then ok "/livez 200 (${i}회 시도)"; else bad "/livez 200 (마지막=$code)"; fi

# 2) /readyz: DB live count + docs==vectors
body=$(fetch /readyz)
code=$(printf '%s' "$body" | tail -n1)
payload=$(printf '%s' "$body" | sed '$d')
if [ "$code" = "200" ] && printf '%s' "$payload" | grep -q '"ready": *true'; then
  ok "/readyz ready=true ($payload)"
else
  bad "/readyz ready=true (code=$code body=$payload)"
fi

# 3) 검색: 한글 질의가 결과를 반환
q=$(python3 -c 'import urllib.parse;print(urllib.parse.quote("한강"))' 2>/dev/null || printf '%%ED%95%9C%EA%B0%95')
body=$(fetch "/api/search?q=${q}&limit=3")
code=$(printf '%s' "$body" | tail -n1)
payload=$(printf '%s' "$body" | sed '$d')
if [ "$code" = "200" ] && printf '%s' "$payload" | grep -q '"count"'; then
  ok "/api/search 200 ($(printf '%s' "$payload" | head -c 120)…)"
else
  bad "/api/search 200 (code=$code)"
fi

# 4) /metrics: 인덱스 게이지가 0 이 아니고 ready=1
body=$(fetch /metrics)
code=$(printf '%s' "$body" | tail -n1)
payload=$(printf '%s' "$body" | sed '$d')
if [ "$code" = "200" ] && printf '%s' "$payload" | grep -q '^seoga_ready 1$'; then
  ok "/metrics seoga_ready=1"
else
  bad "/metrics seoga_ready=1 (code=$code)"
fi
if printf '%s' "$payload" | grep -qE '^seoga_index_documents ([1-9][0-9]*)$'; then
  ok "/metrics seoga_index_documents>0"
else
  bad "/metrics seoga_index_documents>0"
fi

echo "[smoke] pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
