"""예스24 크레마클럽 — 공개 공지사항/상세는 접근 가능하나 '종료 예정 목록'이 없음.

검증 기록(2026-10-27, seoga-research-bot/0.1):
  * https://cremaclub.yes24.com/robots.txt           -> HTTP 200
        Disallow: /MyPage/, /Member/, /Partner/, /Momo/, /Recommend/, /bs/,
                  /Help/, /Error/, /Goods/, /GiftPick/ ... (일반 경로는 허용)
  * https://cremaclub.yes24.com/BookClub/Main        -> HTTP 200 SSR
  * https://cremaclub.yes24.com/BookClub/Notice      -> HTTP 200 SSR 공지사항
        최근 공지 30여 건(2026.01~2026.10) 파싱 결과
        "종료"/"중지"/"종료 예정 도서" 성격의 작품 종료 공지 없음.
  * https://cremaclub.yes24.com/BookClub/Detail/198057351 -> HTTP 200 SSR
        샘플 작품 상세에 종료 예정일 필드 없음.

결론: 크레마클럽은 공개 "종료 예정 도서" 목록을 제공하지 않는 것으로 판단.
fixture 는 data.js 데모 카탈로그에 crema 대응 항목이 없어 0건이며,
제휴 API 어댑터 골격만 남긴다.
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from .base import Collector, CollectorError, Notice

NOTICE_URL = "https://cremaclub.yes24.com/BookClub/Notice"
SAMPLE_DETAIL_URL = "https://cremaclub.yes24.com/BookClub/Detail/198057351"

ENDING_RE = re.compile(r"(종료|중지)\s*(예정)?\s*(도서|작품)", re.I)


class CremaCollector(Collector):
    platform = "crema"
    source_kind = "fixture"
    endpoints = (NOTICE_URL, SAMPLE_DETAIL_URL)

    def collect(self) -> list[Notice]:
        notes: list[str] = []
        try:
            result = self.client.fetch(NOTICE_URL)
            if result.ok:
                posts = self._parse_notice_page(result.text)
                notes.append(f"공지사항 SSR HTTP 200 (공지 {len(posts)}건 파싱)")
                hits = [p for p in posts if ENDING_RE.search(p)]
                if hits:
                    notes.append(f"종료/중지 작품 공지 후보 {len(hits)}건 — 수동 확인 필요")
                else:
                    notes.append("최근 공지에 '종료 예정 도서' 공지 없음")
            else:
                notes.append(f"공지사항 HTTP {result.status}")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"공지사항 조회 실패: {exc.__class__.__name__}")

        notes.append("공개 종료 예정 목록 없음 / data.js 데모에 crema 항목 없어 fixture 0건")
        self.last_note = " / ".join(notes)
        return []

    @staticmethod
    def _parse_notice_page(html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        titles: list[str] = []
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if "BookClub/Notice" not in href and "javascript:void(0)" not in href:
                continue
            text = re.sub(r"\s+", " ", anchor.get_text(" ")).strip()
            if not text:
                continue
            text = re.sub(r"\s*공지사항 보기/감추기\s*$", "", text).strip()
            if len(text) > 8 and text not in titles:
                titles.append(text)
        return titles

    def collect_from_partner_api(self, api_client: Any) -> list[Notice]:
        """제휴 API 어댑터 골격.

        예스24/크레마클럽 제공 시나리오:
          GET {api}/cremaclub/closing-titles       (종료 예정 작품 목록)
          GET {api}/cremaclub/products/{id}        (작품 상세: endDate, isbn13)
        매핑: ends_at = row["endDate"], status="ending",
              source_kind="notice_page"|"per_title_page", confidence="high".

        NOTE: 로그인/구독 세션 재사용, 비공개 API 호출은 하지 않는다.
        """
        raise CollectorError(
            "crema: 제휴 API 클라이언트가 주입되지 않았습니다. "
            "공개 웹에는 종료 예정 목록이 없습니다."
        )
