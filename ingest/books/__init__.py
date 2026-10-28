# -*- coding: utf-8 -*-
"""ingest.books — 서가록(seogarok) 실도서 카탈로그 수집 패키지.

- fetch_base.py : robots.txt 판정 / 인코딩 판별 / 1.2s 레이트리밋 / 원본 HTML 캐시
- yes24_html.py : 예스24 공개 목록·상세 SSR 파서 (robots Allow → 기본 소스)
- aladin_html.py: 알라딘 파서 (robots Disallow → `--allow-disallowed` 없이는 비활성)
- run.py        : CLI (`python -m ingest.books.run --out data/catalog.jsonl --target 2000`)
- verify.py     : catalog.jsonl 검증 리포트(UTF-8) 생성
"""

__all__ = ["fetch_base", "yes24_html", "aladin_html"]
