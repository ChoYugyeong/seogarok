"""윌라(구 월라) — 수집 불가(보안 정책 차단). fixture + 제휴 API 어댑터 골격.

검증 기록(2026-10-27, seoga-research-bot/0.1):
  * 실제 도메인: willa.co.kr 아님 → www.welaaa.com (검색으로 확인)
  * https://willa.co.kr/robots.txt, https://www.willa.co.kr/  -> DNS NXDOMAIN
  * https://www.welaaa.com/robots.txt, /, /ebook, /support/notice/286
        -> 전부 HTTP 403, 자체 "Access Denied by Security Engine" 페이지
           (본문: "보안 정책에 따라 해당 요청 처리가 거부되었습니다")
  * https://api.welaaa.com/ , https://wapi.welaaa.com/  -> DNS A 레코드는 존재하나
        HTTPS 연결 타임아웃(외부 공개 API 아님)
  * https://m.welaaa.com/  -> 연결 타임아웃

웹/앱 모두 SPA 이고 WAF 가 비브라우저 요청을 차단한다. 우회하지 않는다.
"""

from __future__ import annotations

from typing import Any

from .base import Collector, CollectorError, Notice, fixture_notices, load_demo_catalog

EVIDENCE = {
    "willa.co.kr": "DNS NXDOMAIN (윌라 도메인 아님)",
    "www.welaaa.com/robots.txt": "HTTP 403 (Access Denied by Security Engine)",
    "www.welaaa.com/": "HTTP 403 (Access Denied by Security Engine)",
    "api.welaaa.com": "DNS A 존재, HTTPS connect timeout",
    "m.welaaa.com": "HTTPS connect timeout",
}


class WillaCollector(Collector):
    platform = "willa"
    source_kind = "fixture"
    blocked = True
    endpoints = ("https://www.welaaa.com/", "https://www.welaaa.com/ebook")

    def collect(self) -> list[Notice]:
        self.last_note = (
            "차단: www.welaaa.com 전 경로 HTTP 403 (Security Engine WAF), "
            "비공개 API 연결 타임아웃. 실수집 0건 / fixture만 제공."
        )
        return fixture_notices(self.platform, load_demo_catalog(), limit=3)

    def collect_from_partner_api(self, api_client: Any) -> list[Notice]:
        """제휴 API 어댑터 골격.

        윌라 제휴/제공 API 시나리오:
          GET {api}/v1/closing-titles?limit=...   (종료 예정 작품 목록)
          GET {api}/v1/titles/{id}                (작품 상세: endDate, isbn 등)
        매핑: ends_at = row["endDate"], status="ending",
              source_kind="notice_page"(목록 API) 또는 "per_title_page",
              confidence="high", raw_note=응답 필드 발췌.

        NOTE: WAF 우회/헤드리스 브라우저 위장 수집은 하지 않는다.
        """
        raise CollectorError(
            "willa: 제휴 API 클라이언트가 주입되지 않았습니다. "
            "공개 웹은 WAF 로 차단되어 자동 수집을 지원하지 않습니다."
        )
