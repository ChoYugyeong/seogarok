# -*- coding: utf-8 -*-
"""aladin_html.py — 알라딘 공개 목록/상세 HTML 파서 (현재 **비활성**).

## robots.txt 판정 (2026-10-27 실측, https://www.aladin.co.kr/robots.txt, HTTP 200, 5098 bytes)

    User-agent: OAI-SearchBot ... (Tier1: Allow: /, Crawl-delay: 3)
    User-agent: Gemini-Deep-Research / Googlebot ... (Tier2: Allow: /, Crawl-delay: 5)
    User-agent: GPTBot / ClaudeBot / ... (Tier3: Disallow: /)
    User-agent: AhrefsBot / SemrushBot / ... (Tier4: Disallow: /)
    User-agent: Bytespider / CCBot / Scrapy / ... (Tier5: Disallow: /)
    User-agent: *
    Disallow: /

우리 UA `seoga-research-bot/0.1 (+demo; contact: local)`는 어느 명명 그룹에도 매칭되지 않아
**fallback `*` 그룹의 `Disallow: /` 가 적용된다. 따라서 알라딘 수집은 금지**이며,
이 모듈의 네트워크 크롤(`crawl`)은 `--allow-disallowed` 명시 승인 없이는 즉시 거부한다.

파서(parse_list_page / parse_detail_page)는 이미 확보된 캐시 HTML(`_qa/probe/aladin_best.html`)로
검증되어 있으며, 사용자가 알라딘 제휴/TTBKey를 확보해 정당한 수집 권한을 얻은 뒤 재사용할 수 있도록
보존한다. (run.py `--source aladin --allow-disallowed` 경로에서만 사용)
"""
from __future__ import annotations

import json
import re
from typing import Optional

from bs4 import BeautifulSoup

SOURCE = "aladin_html"
BASE = "https://www.aladin.co.kr"
ROBOTS_URL = BASE + "/robots.txt"
LIST_URL = BASE + "/shop/common/wbest.aspx?BestType=Bestseller&BranchType=1&CID={cid}"
DETAIL_URL = BASE + "/shop/wproduct.aspx?ItemId={item_id}"

# robots.txt fallback 그룹 판정 결과(위 문서 참조). --allow-disallowed 없이는 크롤 거부.
ROBOTS_VERDICT = {
    "robots_url": ROBOTS_URL,
    "user_agent": "seoga-research-bot/0.1 (+demo; contact: local)",
    "matched_group": ["*"],
    "matched_rules": [("disallow", "/")],
    "allowed": False,
    "evidence": "2026-10-27 실측 HTTP 200/5098bytes; fallback `User-agent: *` -> `Disallow: /`",
}

PAGINATION_HINT = "페이지 내 링크에서 `&page=N&cnt=1000&SortOrder=1` 확인(미검증)"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _clean(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _won_to_int(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"([\d,]+)", text)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _kr_month_to_iso(text: Optional[str]) -> Optional[str]:
    m = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월", text or "")
    if not m:
        return None
    y, mo = int(m.group(1)), int(m.group(2))
    if not 1 <= mo <= 12:
        return None
    return "%04d-%02d-01" % (y, mo)


# --------------------------------------------------------------------------- #
# list page
# --------------------------------------------------------------------------- #
def parse_list_page(html: str, list_category: Optional[str] = None,
                    list_cid: Optional[str] = None) -> list[dict]:
    """알라딘 베스트 목록 HTML → 책 dict 리스트. 구조 변경 시 [](호출부에서 경고)."""
    if not html:
        return []
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return []
    boxes = soup.select("div.ss_book_box")
    if not boxes:
        boxes = soup.select('div[itemId]')
    if not boxes:
        return []
    category = "국내도서>" + (list_category or "종합")
    items: list[dict] = []
    for box in boxes:
        try:
            item = _parse_box(box, category)
        except Exception:
            continue
        if item is not None:
            items.append(item)
    return items


def _parse_box(box, category: str) -> Optional[dict]:
    item_id = box.get("itemId")
    title_a = box.select_one("a.bo3")
    if title_a is None:
        for a in box.select('a[href*="wproduct.aspx?ItemId="]'):
            t = _clean(a.get_text(" ", strip=True))
            if t:
                title_a = a
                break
    if title_a is None:
        return None
    title = _clean(title_a.get_text(" ", strip=True))
    href = title_a.get("href") or ""
    m = re.search(r"ItemId=(\d+)", href)
    if m:
        item_id = item_id or m.group(1)
    if not item_id or not title:
        return None
    link = DETAIL_URL.format(item_id=item_id)

    # item_code: K-code (알라딘 상품코드)
    raw = str(box)
    item_code = None
    for pat in (r'isbn="(K\d+)"', r"chkCart\.(K\d+)", r"#(K\d+)_CommentReview"):
        mm = re.search(pat, raw)
        if mm:
            item_code = mm.group(1)
            break

    # 저자/출판사/출간월: (지은이)/(옮긴이) 안내 li
    author = publisher = pubdate = None
    info_li = None
    for li in box.select("li"):
        txt = _clean(li.get_text(" ", strip=True))
        if any(k in txt for k in ("지은이", "옮긴이", "엮은이", "글·그림", "지음")):
            info_li = li
            break
    if info_li is not None:
        for a in info_li.select('a[href*="PublisherSearch"]'):
            publisher = _clean(a.get_text(strip=True))
            break
        if publisher is None:
            for a in info_li.select("a"):
                if "AuthorSearch" in (a.get("href") or ""):
                    continue
                t = _clean(a.get_text(strip=True))
                if t:
                    publisher = t
                    break
        pubdate = _kr_month_to_iso(info_li.get_text(" ", strip=True))
        parts = re.split(r"\|", _clean(info_li.get_text(" ", strip=True)))
        if parts:
            author = _clean(re.sub(r"\((?:지은이|옮긴이|엮은이|글|그림|감수|번역|지음)\)", "", parts[0]))
            author = author.rstrip(",·").strip() or None

    price = price_list = None
    sale_el = box.select_one("span.ss_p2 em")
    if sale_el is not None:
        price = _won_to_int(sale_el.get_text(strip=True))
    price_li = None
    for li in box.select("li"):
        txt = _clean(li.get_text(" ", strip=True))
        if "→" in txt and "원" in txt:
            price_li = txt
            break
    if price_li:
        m_list = re.match(r"\s*([\d,]+)\s*원", price_li)
        if m_list:
            price_list = _won_to_int(m_list.group(1))
        if price is None:
            m_sale = re.search(r"→\s*([\d,]+)\s*원", price_li)
            if m_sale:
                price = _won_to_int(m_sale.group(1))

    rating = None
    star = box.select_one("span.star_score")
    if star is not None:
        try:
            rating = float(_clean(star.get_text(strip=True)))
        except ValueError:
            rating = None

    cover_url = None
    img = box.select_one("img.front_cover") or box.select_one("img")
    if img is not None:
        src = (img.get("src") or "").strip()
        if src and "Noimg" not in src:
            if src.startswith("//"):
                src = "https:" + src
            cover_url = src

    return {
        "id": "aladin:" + str(item_id),
        "source": SOURCE,
        "title": title,
        "subtitle": None,
        "author": author,
        "publisher": publisher,
        "pubdate": pubdate,
        "isbn13": None,
        "item_code": item_code,
        "price": price,
        "price_list": price_list,
        "rating": rating,
        "cover_url": cover_url,
        "link": link,
        "category": category,
        "description": None,
        "collected_at": None,
    }


def extract_category_links(html: str) -> list[dict]:
    """좌측 카테고리 트리에서 (CID, 이름) 추출."""
    out: list[dict] = []
    if not html:
        return out
    seen = set()
    for m in re.finditer(
            r'href="/shop/common/wbest\.aspx\?[^"]*CID=(\d+)[^"]*"[^>]*>(?:<span[^>]*>)?([^<]{1,40})',
            html):
        cid, name = m.group(1), _clean(m.group(2))
        if name and (cid, name) not in seen:
            seen.add((cid, name))
            out.append({"cid": cid, "name": name})
    return out


def extract_page_links(html: str) -> dict:
    """페이지 내 페이지네이션 링크에서 page 번호 → URL."""
    pages: dict[int, str] = {}
    for m in re.finditer(r'href="([^"]*[?&]page=(\d+)[^"]*)"', html or ""):
        url, n = m.group(1), int(m.group(2))
        pages.setdefault(n, url if url.startswith("http") else BASE + url)
    return pages


# --------------------------------------------------------------------------- #
# detail page (샘플 미확보 → 방어적·미검증 구현. 확보 시 재검증 필요)
# --------------------------------------------------------------------------- #
def parse_detail_page(html: str) -> dict:
    """알라딘 상품 상세 → {isbn13, description}. 상세페이지 샘플이 없어 **미검증**."""
    out: dict = {}
    if not html:
        return out
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return out
    for pattern, key in (
        (r"ISBN13[^0-9]{0,40}(97[89]\d{10})", "isbn13"),
        (r'"isbn13"\s*:\s*"?(97[89]\d{10})', "isbn13"),
    ):
        m = re.search(pattern, html, re.I)
        if m:
            out[key] = m.group(1)
            break
    for sel in ("div#div_ProductInfo", "div.Ere_bo_title", "div#div_ProductItem"):
        pass
    div = soup.select_one("div#div_ProductInfo") or soup.select_one("div.Ere_bo_title")
    if div is not None:
        text = _clean(div.get_text(" ", strip=True))
        if text:
            out["description"] = text[:4000]
    return out


def crawl(args, report):
    """알라딘 수집 — robots Disallow 이므로 --allow-disallowed 명시 승인 없이는 거부."""
    if not getattr(args, "allow_disallowed", False):
        report.log("[aladin] robots Disallow: / -> 수집 거부 (--allow-disallowed 미지정)")
        report.log("[aladin] robots evidence: %s" % json.dumps(ROBOTS_VERDICT, ensure_ascii=False))
        return None, None, None
    report.log("[aladin] 경고: robots Disallow 소스에 대한 수집이 사용자 승인으로 실행됩니다. "
               "알라딘 파서는 캐시 샘플로만 검증된 상태입니다(상세페이지 미검증).")
    return None, None, None
