#!/bin/sh
# immutable 이미지 + 임시 쓰기 레이어.
# 이미지에 구운 인덱스를 /tmp(tmpfs) 로 복사해 읽기 전용 루트에서도 SQLite WAL 동작.
# Cloud Run 은 PORT(기본 8080)를 주입하므로 그 값을 따른다.
set -eu

PORT_TO_USE="${PORT:-8100}"
SRC=/app/data/seoga.db
DST=${SEOG_DB:-/tmp/data/seoga.db}

if [ ! -f "$DST" ]; then
  mkdir -p "$(dirname "$DST")"
  cp "$SRC" "$DST"
  echo "{\"ts\":\"$(date -Iseconds)\",\"level\":\"info\",\"msg\":\"db_seeded_to_tmpfs\",\"dst\":\"$DST\",\"port\":\"$PORT_TO_USE\"}"
fi

exec python -m server.app --host 0.0.0.0 --port "$PORT_TO_USE" "$@"
