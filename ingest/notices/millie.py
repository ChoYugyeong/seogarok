"""밀리의서재 — 종료 예정 도서 수집기.

★ 실제 수집 가능(검증 완료).
웹 v4 는 Next.js SPA 지만, 공개 모바일 JSON API 가 비로그인으로 응답한다.
  GET https://live-api.millie.co.kr/v3/today/servicelimit/ebook?limit=100&page=N
  200 application/json, RESP_CD=200, RESP_DATA.total_count=329,
  RESP_DATA.result[].service_limit_date = 서비스 종료일 (YYYY-MM-DD)
  RESP_DATA.result[].book_name/author/book_seq/book_cover_image 등

이 엔드포인트는 공개 JS 번들(_app chunk)의 설정값에서 확인했다.
  phpHost=https://api.millie.co.kr / apiHost=https://live-api.millie.co.kr
  라우트 맵: /v3/today/servicelimit/:category
기존 앱의 공개 "종료 예정 도서" 목록과 동일한 데이터로 판단된다.

robots.txt(https://www.millie.co.kr/robots.txt): User-agent * Allow: /
  (Disallow: /h4/, */viewer/* 만 제한) — live-api 호스트는 robots.txt 404.
"""

from __future__ import annotations

from .base import (
    CONFIDENCES,
    Collector,
    CollectorError,
    DATE_RE,
    Notice,
    make_notice,
)
from .base import HttpClient  # noqa: F401  (typing/재사용)

API_URL = "https://live-api.millie.co.kr/v3/today/servicelimit/ebook"
PER_TITLE_PAGE_URL = "https://www.millie.co.kr/v4/book/{book_id}"


class MillieCollector(Collector):
    platform = "millie"
    source_kind = "notice_page"  # 공개 종료 예정 도서 목록(JSON)
    endpoints = (API_URL,)
    page_size = 100
    max_pages = 20

    def collect(self) -> list[Notice]:
        rows: dict[str, dict] = {}
        total = 0
        page = 1
        pages_fetched = 0
        while page <= self.max_pages:
            url = f"{API_URL}?limit={self.page_size}&page={page}"
            result = self.client.fetch(url)
            pages_fetched += 1
            if not result.ok:
                raise CollectorError(f"millie API HTTP {result.status} ({url})")
            try:
                payload = result.json()
            except ValueError as exc:
                raise CollectorError(f"millie API JSON 파싱 실패: {exc}") from exc
            if payload.get("RESP_CD") not in (200, "200"):
                raise CollectorError(
                    f"millie API RESP_CD={payload.get('RESP_CD')} RESP_MSG={payload.get('RESP_MSG')}"
                )
            data = payload.get("RESP_DATA") or {}
            total = int(data.get("total_count") or 0)
            batch = data.get("result") or []
            if not batch:
                break
            for row in batch:
                seq = str(row.get("book_seq") or row.get("book_id") or "")
                if seq and seq not in rows:
                    rows[seq] = row
            if len(rows) >= total:
                break
            page += 1

        notices: list[Notice] = []
        for seq, row in rows.items():
            title = (row.get("book_name") or "").strip()
            if not title:
                continue
            limit_date = (row.get("service_limit_date") or "").strip()
            ends_at = limit_date if DATE_RE.match(limit_date) else None
            notices.append(
                make_notice(
                    self.platform,
                    title,
                    author=(row.get("author") or "").strip() or None,
                    ends_at=ends_at,
                    status="ending",
                    source_url=f"{API_URL}#book_seq={seq}",
                    source_kind="notice_page",
                    confidence="high" if ends_at else "medium",
                    raw_note=f"service_limit_date={limit_date}; book_seq={seq}",
                )
            )
        notices.sort(key=lambda n: (n.ends_at or "9999-12-31", n.title))
        self.last_note = (
            f"live-api JSON 200 (비로그인) · {pages_fetched}페이지 요청 · "
            f"total_count={total} · 실제 수집 {len(notices)}건"
        )
        if total and len(notices) < total:
            self.last_note += f" (일부 누락: {total - len(notices)}건)"
        return notices
