# 서가 API 컨테이너 이미지
#  - 빌드 단계에서 임베딩 모델을 굽고 인덱스까지 생성한다 (immutable artifact)
#  - 런타임에는 DB를 tmpfs로 복사해 읽기 전용 루트파일시스템에서 동작

# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1

WORKDIR /app
COPY requirements.server.txt .
RUN pip install --prefix=/install -r requirements.server.txt
ENV PYTHONPATH=/install/lib/python3.12/site-packages

# 임베딩 모델을 이미지에 고정 (런타임 네트워크 불필요)
RUN python -c "from model2vec import StaticModel; StaticModel.from_pretrained('minishlab/potion-multilingual-128M')"

COPY server ./server
COPY data ./data
# 운영 데이터(공식 API 수집분)가 있으면 그것을, 없으면 seed(38권)로 폴백한다.
#  - data/catalog.jsonl : python -m ingest.books.yes24_api (공식 Open API, .gitignore)
#  - data/notices.jsonl : python -m ingest.notices.run (밀리 공개 목록, .gitignore)
RUN python -m server.prepare_data
# 빌드 시점에 인덱스 생성 = 배포 아티팩트에 검색 인덱스가 포함됨
RUN python -m server.sync --embed model2vec --catalog data/catalog.jsonl --notices data/notices.jsonl


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/home/app/.cache/huggingface \
    HF_HUB_OFFLINE=1 \
    SEOG_DB=/tmp/data/seoga.db \
    SEOG_CHAOS=1

RUN apt-get update && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app

WORKDIR /app
COPY --from=builder /install /usr/local
COPY --from=builder --chown=app:app /root/.cache/huggingface /home/app/.cache/huggingface
COPY --chown=app:app server ./server
COPY --chown=app:app index.html styles.css app.js ads.js data.js legal.html about.html privacy.html terms.html privacy-contact.html manifest.webmanifest sw.js robots.txt sitemap.xml 404.html ./
COPY --chown=app:app icons ./icons
COPY --chown=app:app assets ./assets
# 빌더 단계에서 만든 인덱스를 가져온다 (빌드 컨텍스트의 DB 파일이 아니라)
COPY --from=builder --chown=app:app /app/data/seoga.db ./data/seoga.db
COPY --chown=app:app scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER app
EXPOSE 8100

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8100/healthz',timeout=2)" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/docker-entrypoint.sh"]
# 포트는 엔트리포인트가 결정한다: Cloud Run 의 $PORT(기본 8080) 또는 SEOG 기본 8100
CMD []
