"""교보eBook sam — 공지사항 게시판은 공개(SSR)지만 '작품별 종료 예정 목록'은 없음.

검증 기록(2026-10-27, seoga-research-bot/0.1):
  * https://sam.kyobobook.co.kr/robots.txt                         -> HTTP 200 (User-agent * Allow: /)
  * https://sam.kyobobook.co.kr/                                   -> HTTP 200 SSR (sam 홈, 상품 목록 SSR)
  * https://ebook.kyobobook.co.kr/dig/cff/notice                   -> HTTP 200 SSR 공지사항 게시판
  * https://ebook.kyobobook.co.kr/dig/cff/notice/100865            -> HTTP 200
        실제 공지: "[sam] sam스페셜(동아사이언스) 서비스 일시 중지 안내 (~1/2)"
        -> 서비스/상품 단위 공지이며, 작품별 종료일 목록이 아니다.
  * https://ebook-product.kyobobook.co.kr/dig/epd/sam/E000005221953 -> HTTP 200 SSR
        샘플 작품 상세(구의 증명)에 종료 예정일 필드 없음.
  * 공지 게시판은 "공지사항 / 이벤트 / 당첨자발표" 탭 구조이며
    현재 노출분에 "종료 예정 도서" 목록 공지는 확인되지 않음.

결론: 공개·비로그인으로 "특정 작품의 sam 종료일"을 찾을 수 있는 공개 목록이 없다.
fixture + 제휴 API 어댑터 골격만 제공한다.
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from .base import Collector, CollectorError, Notice, fixture_notices, load_demo_catalog

NOTICE_URL = "https://ebook.kyobobook.co.kr/dig/cff/notice"
SAMPLE_PRODUCT_URL = "https://ebook-product.kyobobook.co.kr/dig/epd/sam/E000005221953"

#: "종료 예정 도서 목록" 공지를 찾을 때 쓰는 패턴(향후 게시판에 생기면 잡는다)
ENDING_LIST_RE = re.compile(r"(종료|중지)\s*(예정)?\s*(도서|작품|타이틀)", re.I)


class SamCollector(Collector):
    platform = "sam"
    source_kind = "fixture"
    endpoints = (NOTICE_URL, SAMPLE_PRODUCT_URL)

    def collect(self) -> list[Notice]:
        notes: list[str] = []
        posts = []
        try:
            result = self.client.fetch(NOTICE_URL)
            if result.ok:
                posts = self._parse_posts(result.text)
                notes.append(f"공지사항 게시판 SSR HTTP 200 (게시글 {len(posts)}개 파싱)")
                hits = [p for p in posts if ENDING_LIST_RE.search(p["title"])]
                if hits:
                    notes.append(f"종료 예정 도서 목록 공지 후보 {len(hits)}건 — 파서 미구현(수동 확인 필요)")
                else:
                    notes.append("현재 노출 공지 중 '종료 예정 도서' 목록 공지 없음")
            else:
                notes.append(f"공지사항 게시판 HTTP {result.status}")
        except Exception as exc:  # noqa: BLE001 - 수집기 하나 실패가 전체를 막지 않는다
            notes.append(f"공지사항 조회 실패: {exc.__class__.__name__}")

        notes.append("작품별 종료일 공개 목록 없음 → fixture만 제공")
        self.last_note = " / ".join(notes)
        return fixture_notices(self.platform, load_demo_catalog(), limit=3)

    @staticmethod
    def _parse_posts(html: str) -> list[dict[str, str]]:
        soup = BeautifulSoup(html, "lxml")
        posts: list[dict[str, str]] = []
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            path = re.sub(r"^https?://[^/]+", "", href)
            match = re.match(r"^(/dig/cff/notice/\d+)", path)
            if not match:
                continue
            title = re.sub(r"\s+", " ", anchor.get_text(" ")).strip()
            if not title or len(title) < 4:
                continue
            url = "https://ebook.kyobobook.co.kr" + match.group(1)
            if not any(post["url"] == url for post in posts):
                posts.append({"title": title, "url": url})
        return posts

    def collect_from_partner_api(self, api_client: Any) -> list[Notice]:
        """제휴 API 어댑터 골격.

        교보 측 제공 시나리오:
          GET {api}/sam/closing-titles?page=...     (sam 구독 종료 예정 작품)
          GET {api}/sam/products/{id}               (작품 상세: samServiceEndDate)
        매핑: ends_at = row["samServiceEndDate"], status="ending",
              source_kind="notice_page"|"per_title_page", confidence="high".

        NOTE: 로그인 세션 재사용/비공개 API 스크래핑은 하지 않는다.
        """
        raise CollectorError(
            "sam: 제휴 API 클라이언트가 주입되지 않았습니다. "
            "공개 웹에는 작품별 종료일 목록이 없습니다."
        )
