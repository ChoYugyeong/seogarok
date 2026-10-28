"""서가록(seogarok) 백엔드 — 설정."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = Path(os.getenv("SEOG_DB", DATA_DIR / "seoga.db"))
CATALOG_PATH = Path(os.getenv("SEOG_CATALOG", DATA_DIR / "catalog.jsonl"))
NOTICES_PATH = Path(os.getenv("SEOG_NOTICES", DATA_DIR / "notices.jsonl"))
STATIC_DIR = ROOT

# 임베딩
EMBED_MODEL = os.getenv("SEOG_EMBED_MODEL", "minishlab/potion-multilingual-128M")
EMBED_BACKEND = os.getenv("SEOG_EMBED", "auto")  # auto | model2vec | hashing
EMBED_DIM = int(os.getenv("SEOG_EMBED_DIM", "256"))

# 알라딘 공식 OpenAPI (키가 있으면 공식 API 어댑터 사용)
ALADIN_TTBKEY = os.getenv("ALADIN_TTBKEY", "").strip()

# research: 공개 페이지/공개 정보 수집 모드(데모), production: 제휴 API만
MODE = os.getenv("SEOG_MODE", "research")

HOST = os.getenv("SEOG_HOST", "127.0.0.1")
PORT = int(os.getenv("SEOG_PORT", "8100"))
