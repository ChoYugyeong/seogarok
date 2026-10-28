# 서가록(seogarok) 운영 진입점
#
# 이 파일은 compose 스택을 "한 줄 명령"으로 다루기 위한 얇은 래퍼다.
# make가 없는 Windows에서도 읽을 수 있도록, 각 타깃의 PowerShell 등가 명령을 주석으로 병기한다.
#
#   타깃            실제 동작                                             서비스/엔드포인트
#   ------------------------------------------------------------------------------------------------
#   make up         docker compose up -d --build                          api:8100, prometheus:9090, grafana:3001
#   make down       docker compose down (볼륨 유지)                       -
#   make logs       docker compose logs -f --tail=100                    전체 서비스
#   make ps         docker compose ps                                    전체 서비스
#   make smoke      기동 대기 후 /healthz /readyz /metrics /api/search     api:8100
#   make load       docker compose --profile load run --rm k6 ...         k6 -> api:8100
#   make chaos      POST /api/_chaos (latency 400ms, error 0.3)           api:8100
#   make reset-chaos POST /api/_chaos (latency 0, error 0)                api:8100
#   make test       seed 인덱스 + 오프라인 검색 단언 (Docker 불필요)        -
#   make dash       Grafana 대시보드 열기                                  localhost:3001/d/seogarok-sre
#
#   ※ 컨테이너 인덱스는 data/catalog.jsonl(예스24 Open API 수집분) 기준이며, 없으면 seed(38권)로 폴백한다
#     (전체 4,865권은 로컬에서 python -m server.sync 로 생성). smoke는 컨테이너 기준이다.
#   ※ Grafana 호스트 포트는 3001이다(3000은 다른 앱이 쓰는 환경이 있어 compose에서 3001:3000 매핑).
#   ※ make가 없으면 아래 PowerShell 열을 그대로 실행한다.
#       make up          -> docker compose up -d --build
#       make ps          -> docker compose ps
#       make logs        -> docker compose logs -f --tail=100
#       make down        -> docker compose down
#       make smoke       -> $u='http://127.0.0.1:8100'; curl.exe -fsS "$u/healthz"; curl.exe -fsS "$u/readyz"; ...
#       make load        -> docker compose --profile load run --rm k6 run /scripts/search.js
#       make chaos       -> curl.exe -s -X POST http://127.0.0.1:8100/api/_chaos -H "Content-Type: application/json" -d '{"latency_ms":400,"error_rate":0.3}'
#                           (또는: powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\game_day.ps1 -Scenario all)
#       make reset-chaos -> curl.exe -s -X POST http://127.0.0.1:8100/api/_chaos -H "Content-Type: application/json" -d '{"latency_ms":0,"error_rate":0}'
#       make test        -> python -m server.sync --catalog data/seed_catalog.jsonl --notices data/notices.jsonl --db data/ci.db --embed hashing
#       make dash        -> Start-Process 'http://localhost:3001/d/seogarok-sre'

.DEFAULT_GOAL := help

PYTHON        ?= python
API_PORT      ?= 8100
PROM_PORT     ?= 9090
GRAFANA_PORT  ?= 3001
API_URL       ?= http://127.0.0.1:$(API_PORT)

# 게임데이 기본 주입값 (scripts/game_day.ps1 -Scenario all 과 동일)
CHAOS_LATENCY_MS ?= 400
CHAOS_ERROR_RATE ?= 0.3

# 오프라인 테스트 산출물 (data/ 는 .gitignore 대상)
TEST_DB        ?= data/ci.db
SEED_CATALOG   ?= data/seed_catalog.jsonl

.PHONY: help up down logs ps smoke load chaos reset-chaos dash test \
        tf-validate tf-plan deploy-status deploy-rollback

## help: 사용 가능한 타깃 목록 (기본 타깃 — 실수로 배포되지 않게 함)
help:
	@echo "서가록(seogarok) 운영 타깃:"
	@echo "  make up           # docker compose up -d --build  (api:8100, prometheus:9090, grafana:3001)"
	@echo "  make ps           # docker compose ps"
	@echo "  make logs         # docker compose logs -f --tail=100"
	@echo "  make smoke        # /healthz /readyz /metrics /api/search 검증 (컨테이너 수집분 기준)"
	@echo "  make load         # k6 부하테스트 (profile load)"
	@echo "  make chaos        # POST /api/_chaos  latency=$(CHAOS_LATENCY_MS)ms error_rate=$(CHAOS_ERROR_RATE)"
	@echo "  make reset-chaos  # POST /api/_chaos  latency=0 error_rate=0"
	@echo "  make dash         # Grafana 대시보드 열기 http://localhost:$(GRAFANA_PORT)/d/seogarok-sre"
	@echo "  make test         # seed 38권 + hashing 임베딩으로 오프라인 검색 테스트 (Docker 불필요)"
	@echo "  make down         # docker compose down (볼륨 유지)"
	@echo ""
	@echo "  [IaC/배포] Cloud Run"
	@echo "  make tf-validate  # terraform fmt + validate (자격증명 불필요)"
	@echo "  make tf-plan      # plan (GCP 인증 + TF_STATE_BUCKET 필요)"
	@echo "  make deploy-status   # Cloud Run 리비전/트래픽"
	@echo "  make deploy-rollback # 직전 리비전으로 롤백"
	@echo ""
	@echo "  Windows에서 make가 없으면 각 타깃 위 주석의 PowerShell 명령을 사용한다."

## up: 스택 기동 (이미지 재빌드 포함)
up:
	docker compose up -d --build

## down: 스택 종료 (named volume은 유지; Prometheus 이력 보존)
down:
	docker compose down
	@echo "[down] 볼륨까지 지우려면: docker compose down -v"

## logs: 전체 서비스 로그 follow (단일 서비스는 docker compose logs -f api)
logs:
	docker compose logs -f --tail=100

## ps: compose 서비스 상태
ps:
	docker compose ps

## smoke: 기동 대기 후 liveness/readiness/metrics/검색을 순서대로 검증
smoke:
	@echo "[smoke] $(API_URL) 준비 대기 (최대 60초) ..."
	@i=0; \
	until curl -fsS "$(API_URL)/readyz" >/dev/null 2>&1; do \
		i=$$((i+1)); \
		if [ $$i -ge 30 ]; then echo "[smoke] FAIL: readyz가 60초 내 200이 되지 않음 (make ps / make logs 확인)"; exit 1; fi; \
		sleep 2; \
	done; \
	echo "[smoke] OK  /readyz 200"
	@curl -fsS "$(API_URL)/healthz" | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d.get('ok') is True, d; print('[smoke] OK  /healthz version=%s uptime=%ss' % (d.get('version'), d.get('uptime_s')))"
	@curl -fsS "$(API_URL)/readyz" | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d.get('ready') is True, d; assert d.get('documents') == d.get('vectors'), d; print('[smoke] OK  /readyz documents=%s vectors=%s' % (d['documents'], d['vectors']))"
	@curl -fsS "$(API_URL)/metrics" | grep -q "^seogarok_http_requests_total" && echo "[smoke] OK  /metrics seogarok_http_requests_total"
	@curl -fsS "$(API_URL)/metrics" | grep -q "^seogarok_ready 1" && echo "[smoke] OK  /metrics seogarok_ready 1"
	@curl -fsS "$(API_URL)/metrics" | grep -Eq "^seogarok_index_documents [1-9][0-9]*$" && echo "[smoke] OK  /metrics seogarok_index_documents > 0"
	@curl -fsS -G --data-urlencode "q=소설" --data-urlencode "mode=hybrid" --data-urlencode "limit=3" "$(API_URL)/api/search" | $(PYTHON) -c "import json,sys; d=json.load(sys.stdin); assert d.get('mode') == 'hybrid', d; assert 'results' in d, d; print('[smoke] OK  /api/search count=%s took_ms=%s' % (d.get('count'), d.get('took_ms')))"
	@echo "[smoke] PASS"

## load: k6 부하테스트 (compose profile load; 종료 후 컨테이너 자동 제거)
load:
	docker compose --profile load run --rm k6 run /scripts/search.js

## chaos: 지연+오류 주입 (게임데이). SEOG_CHAOS=1 일 때만 동작
chaos:
	@curl -fsS -X POST "$(API_URL)/api/_chaos" \
		-H "Content-Type: application/json" \
		-d '{"latency_ms":$(CHAOS_LATENCY_MS),"error_rate":$(CHAOS_ERROR_RATE)}'
	@echo ""
	@echo "[chaos] 주입 완료 — Grafana http://localhost:$(GRAFANA_PORT)/d/seogarok-sre, Prometheus http://localhost:$(PROM_PORT)/alerts 확인"
	@echo "[chaos] 복구: make reset-chaos  (또는 .\\scripts\\game_day.ps1 -Scenario reset)"

## reset-chaos: 주입 해제 (잊지 말고 반드시 실행)
reset-chaos:
	@curl -fsS -X POST "$(API_URL)/api/_chaos" \
		-H "Content-Type: application/json" \
		-d '{"latency_ms":0,"error_rate":0}'
	@echo ""
	@echo "[chaos] 리셋 완료 — /api/_chaos 에서 0인지 확인"

## dash: Grafana 대시보드/Prometheus alerts 페이지 열기 (가능한 경우 브라우저 실행)
dash:
	@echo "[dash] Grafana    http://localhost:$(GRAFANA_PORT)/d/seogarok-sre  (admin/admin, 익명 Viewer 허용)"
	@echo "[dash] Prometheus http://localhost:$(PROM_PORT)/alerts"
	@(command -v powershell >/dev/null 2>&1 && powershell -NoProfile -Command "Start-Process 'http://localhost:$(GRAFANA_PORT)/d/seogarok-sre'" >/dev/null 2>&1) || \
	 (command -v xdg-open >/dev/null 2>&1 && xdg-open "http://localhost:$(GRAFANA_PORT)/d/seogarok-sre" >/dev/null 2>&1) || true

## test: 오프라인 검색 테스트 (Docker/모델 가중치 다운로드 없음; hashing 임베딩)
test:
	@echo "[test] seed 인덱스 생성 (38권, --embed hashing)"
	$(PYTHON) -m server.sync --catalog $(SEED_CATALOG) --db $(TEST_DB) --embed hashing
	@echo "[test] 검색 파이프라인 단언 (키워드+벡터 융합)"
	$(PYTHON) -c "from server.db import connect, meta, VectorStore; from server.embed import get_embedder; from server.search import search, fetch_books; c=connect('$(TEST_DB)'); m=meta(c); assert int(m['book_count'])==38, ('book_count', m.get('book_count')); e=get_embedder('hashing'); s=VectorStore(c, e.dim); ids,dbg=search(c,s,e,'\ucc44\uc2dd\uc8fc\uc758\uc790',mode='hybrid',limit=5); rows=fetch_books(c,ids); assert ids and rows, 'search returned no rows'; print('[test] PASS book_count=%s strategy=%s hits=%d' % (m['book_count'], dbg.extra.get('strategy'), len(ids)))"
	@echo "[test] PASS"

# ============================================================================
# IaC / 배포 (Cloud Run)
#   make tf-validate    : Terraform fmt + validate (자격증명 불필요 — PR 게이트와 동일)
#   make tf-plan        : Terraform plan (GCP 인증 + TF_STATE_BUCKET 필요)
#   make deploy-status  : Cloud Run 리비전/트래픽 현황
#   make deploy-rollback: 직전 리비전으로 롤백 (SERVICE/REGION env)
#
# PowerShell 등가:
#   make tf-validate     -> cd terraform; terraform fmt -check -recursive; terraform init -backend=false; terraform validate
#   make deploy-status   -> $env:SERVICE='seoga-api'; $env:REGION='asia-northeast3'; bash scripts/deploy_canary.sh status
#   make deploy-rollback -> $env:SERVICE='seoga-api'; $env:REGION='asia-northeast3'; bash scripts/deploy_canary.sh rollback
# ============================================================================

TF_DIR      ?= terraform
TF_BUCKET   ?= $(TF_STATE_BUCKET)
SERVICE     ?= seoga-api
REGION      ?= asia-northeast3

## tf-validate: Terraform fmt + init(no backend) + validate — 자격증명 없이 실행 가능
tf-validate:
	terraform -chdir=$(TF_DIR) fmt -check -recursive
	terraform -chdir=$(TF_DIR) init -backend=false -input=false
	terraform -chdir=$(TF_DIR) validate

## tf-plan: Terraform plan (GCP 로그인 + TF_STATE_BUCKET 필요)
tf-plan:
	@test -n "$(TF_BUCKET)" || { echo "[tf-plan] TF_STATE_BUCKET 환경변수가 필요합니다 (예: export TF_STATE_BUCKET=my-tf-state)"; exit 1; }
	terraform -chdir=$(TF_DIR) init -input=false \
		-backend-config="bucket=$(TF_BUCKET)" -backend-config="prefix=seoga/state"
	terraform -chdir=$(TF_DIR) plan -input=false

## deploy-status: Cloud Run 리비전/트래픽 현황 (gcloud 인증 필요)
deploy-status:
	@SERVICE=$(SERVICE) REGION=$(REGION) bash scripts/deploy_canary.sh status

## deploy-rollback: 직전 리비전으로 100% 롤백 (gcloud 인증 필요)
deploy-rollback:
	@SERVICE=$(SERVICE) REGION=$(REGION) bash scripts/deploy_canary.sh rollback
