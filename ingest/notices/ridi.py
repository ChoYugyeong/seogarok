"""RIDI 셀렉트 — 수집 불가(차단). fixture + 제휴 API 어댑터 골격.

검증 기록(2026-10-27, seoga-research-bot/0.1):
  * https://ridibooks.com/robots.txt                         -> HTTP 403, Cloudflare "Just a moment..."
  * https://ridibooks.com/                                   -> HTTP 403, Cloudflare 챌린지
  * https://book-api.ridibooks.com/books/330000001           -> HTTP 403, Cloudflare 챌린지
  * https://search-api.ridibooks.com/search?q=한강            -> HTTP 403, Cloudflare 챌린지
  * https://ridiselect.ridibooks.com/                        -> DNS NXDOMAIN (잘못된 호스트)
  * https://select.ridibooks.com/closing-reserved-book       -> HTTP 403, Cloudflare 챌린지
      (고객센터 문서가 안내하는 실제 "셀렉트 홈 > 종료 예정 도서" URL)
  * https://ridihelp.ridibooks.com/support/solutions/articles/154000204604 -> HTTP 200 (SSR)
      문서 제목: "[셀렉트] 서비스 종료 / 중지 작품 이용 기간"
      본문: "종료 예정 작품은 작품홈 내 예정일자 확인 및 기한 내 마이셀렉트에 추가"
            "셀렉트 서비스 종료 예정 작품은 [셀렉트 홈 > 종료 예정 도서] 에서 확인"

즉 RIDI 는 (a) 봇 차단(Cloudflare) + (b) 셀렉트 목록 자체가 구독자 대상 화면이라
비로그인 자동 수집은 정당하게 불가능하다. 우회하지 않는다.
제휴/제공 API 가 있다면 `collect_from_partner_api()` 지점에 꽂으면 된다.
"""

from __future__ import annotations

from typing import Any

from .base import Collector, CollectorError, Notice, fixture_notices, load_demo_catalog

HELP_ARTICLE_URL = "https://ridihelp.ridibooks.com/support/solutions/articles/154000204604"
SELECT_CLOSING_URL = "https://select.ridibooks.com/closing-reserved-book"

EVIDENCE = {
    "ridibooks.com/robots.txt": "HTTP 403 Cloudflare 'Just a moment...'",
    "ridibooks.com/": "HTTP 403 Cloudflare 'Just a moment...'",
    "book-api.ridibooks.com/books/330000001": "HTTP 403 Cloudflare 'Just a moment...'",
    "search-api.ridibooks.com/search?q=한강": "HTTP 403 Cloudflare 'Just a moment...'",
    "ridiselect.ridibooks.com": "DNS NXDOMAIN",
    "select.ridibooks.com/closing-reserved-book": "HTTP 403 Cloudflare 'Just a moment...'",
    "ridihelp.../articles/154000204604": "HTTP 200 SSR — 정책 문서(목록 아님), "
    "'[셀렉트 홈 > 종료 예정 도서]' 안내",
}


class RidiSelectCollector(Collector):
    platform = "ridiselect"
    source_kind = "fixture"
    blocked = True
    endpoints = (SELECT_CLOSING_URL, HELP_ARTICLE_URL)

    def collect(self) -> list[Notice]:
        self.last_note = (
            "차단: 전 경로 Cloudflare 챌린지(HTTP 403). "
            "고객센터 문서(HTTP 200)는 정책 안내일 뿐 작품 목록이 아님. "
            "실수집 0건 / fixture만 제공."
        )
        return fixture_notices(self.platform, load_demo_catalog(), limit=3)

    # -- 제휴 API 연결 지점 ------------------------------------------------
    def collect_from_partner_api(self, api_client: Any) -> list[Notice]:
        """제휴 API 어댑터 골격.

        계약/제공 시나리오(택1):
          1) 제휴사가 "종료 예정 도서" JSON 목록을 제공:
             rows = api_client.get("/v1/select/closing-books")
             각 row: {title, author, isbn13, end_date, book_url}
          2) 작품별 종료일 엔드포인트만 제공:
             for book_id in api_client.get("/v1/select/books", filters={"closing": True}):
                 detail = api_client.get(f"/v1/books/{book_id}")
                 end_date = detail["select_rental_end_date"]

        반환 스키마는 반드시 아래로 매핑한다.
          Notice(platform="ridiselect", title=..., author=..., isbn13=...,
                 ends_at="YYYY-MM-DD", status="ending",
                 source_url=작품 URL, source_kind="per_title_page"|"notice_page",
                 confidence="high", raw_note="제휴 API 응답 필드명/발췌")

        NOTE: 로그인/구독자 쿠키 재사용, Cloudflare 우회, 스크래핑을 하지 않는다.
        """
        raise CollectorError(
            "ridiselect: 제휴 API 클라이언트가 주입되지 않았습니다. "
            "공개 웹은 Cloudflare 로 차단되어 자동 수집을 지원하지 않습니다."
        )

    def probe_blocked(self) -> dict[str, Any]:
        """현재 차단 상태 재확인(선택적, run.py --verify-blocked)."""
        result = self.client.fetch(SELECT_CLOSING_URL, check_robots=False)
        return {
            "url": SELECT_CLOSING_URL,
            "status": result.status,
            "content_type": result.content_type,
            "first_line": result.text.strip().splitlines()[0][:120] if result.text.strip() else "",
        }
