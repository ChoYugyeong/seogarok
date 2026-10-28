# -*- coding: utf-8 -*-
"""yes24_html.py — 예스24 공개 카테고리/베스트 목록 + 상품 상세페이지 파서 (리서치 모드).

robots.txt 근거 (2026-10-27 실측, `https://www.yes24.com/robots.txt`):
    User-agent: *
    Disallow: /*.pdf$  /templates/  /member/  /common/  /goods/  /Partner/ ...
    (전면 `Disallow: /` 아님 → 우리 UA `seoga-research-bot/0.1`은 목록/상세 경로 수집 가능)

우리가 쓰는 경로만 사용한다:
  - 목록:   /product/category/bestseller?categoryNumber=...&pageNumber=..&pageSize=120
  - 상세:   /Product/Goods/<goodsNo>
  - robots: /robots.txt
`/api/`, `/searchCenter/`, `/24/category/bestsellerExcel`, `/24/Category/CategoryNavBarNew/`,
`/product/category/display/018...` 등 Disallow 경로는 요청하지 않는다(fetch_base가 사전 차단).

목록 HTML은 서버사이드 렌더링(SSR)이며 `div.itemUnit` 1개가 책 1권이다.
  - 제목        a.gd_name (href=/product/goods/<goodsNo>)
  - 저자/역자   span.info_auth
  - 출판사      span.info_pub
  - 출간월      span.info_date  ("2026년 10월")
  - 판매가      div.info_price strong.txt_num em.yes_b  ("16,650")
  - 정가        div.info_price span.txt_num.dash em.yes_m ("18,500")
  - 별점        span.rating_grade em.yes_b ("9.1" / 10점)
  - 표지        div.item_img img[data-original]  (image.yes24.com/goods/<id>/L)
상세 HTML(SSR):
  - ISBN13      #infoset_specific 표의 "ISBN13" 행
  - 발행일      같은 표 "발행일" 행 ("2026년 10월 21일") → pubdate 정밀화
  - 쪽수        "쪽수, 무게, 크기" 행
  - 책소개      #infoset_introduce div.infoWrap_txt
  - 카테고리    #infoset_goodsCate 첫 dl의 링크 체인 ("국내도서>소설/시/희곡>일본소설")
"""
from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup

SOURCE = "yes24_html"
HOST = "https://www.yes24.com"
LIST_URL_TMPL = HOST + "/product/category/bestseller?categoryNumber={cid}&pageNumber={page}&pageSize={size}"
DETAIL_URL_TMPL = HOST + "/Product/Goods/{goods_no}"
ROBOTS_URL = HOST + "/robots.txt"

# 상위 장르 카테고리 코드 (모바일 카테고리 페이지 /product/category/display/001 에서 실측 추출)
GENRE_CATEGORIES: dict[str, str] = {
    "001": "종합",
    "001001046": "소설/시/희곡",
    "001001047": "에세이",
    "001001019": "인문",
    "001001002": "자연과학",
    "001001026": "자기계발",
    "001001025": "경제 경영",
    "001001010": "역사",
    "001001007": "예술",
    "001001009": "여행",
    "001001005": "청소년",
    "001001016": "어린이",
    "001001027": "유아",
    "001001022": "사회 정치",
    "001001020": "인물",
    "001001021": "종교",
    "001001011": "건강 취미",
    "001001001": "가정 살림",
    "001001003": "IT 모바일",
    "001001004": "국어 외국어 사전",
    "001001008": "만화/라이트노벨",
    "001001014": "대학교재",
    "001001015": "수험서 자격증",
    "001001024": "잡지",
}
# 크롤 순서: 종합 베스트를 먼저(상위 랭크가 먼저 들어가도록) → 장르별.
DEFAULT_CATEGORY_ORDER = [
    "001", "001001046", "001001047", "001001019", "001001002", "001001026",
    "001001025", "001001010", "001001007", "001001009", "001001005", "001001016",
    "001001027", "001001022", "001001020", "001001021", "001001011", "001001001",
    "001001003", "001001004", "001001008", "001001014", "001001015", "001001024",
]

DEFAULT_PAGE_SIZE = 120
NON_BOOK_TITLE_PREFIXES = ("[전자책]", "[eBook]", "[중고]", "[음반]", "[DVD]", "[블루레이]", "[전집]")

# 실수 방지용 하드 차단 목록: robots Disallow 경로 + 상품 API 경로. 이 URL은 절대 요청하지 않는다.
FORBIDDEN_PATH_SUBSTRINGS = (
    "/api/",                              # 상품/카테고리 API (교보문고 등에서 Disallow, 예스24에서도 사용 안 함)
    "/searchCenter/",                     # robots Disallow
    "/24/category/bestsellerExcel",       # robots Disallow (엑셀 덤프)
    "/24/Category/CategoryNavBarNew/",    # robots Disallow (카테고리 AJAX)
    "/Product/Base/",                     # robots Disallow
    "/product/category/display/018",      # robots Disallow (중고/성인)
    "/24/UsedShop/",                      # robots Disallow
    "/Event/",                            # robots Disallow
)


def is_forbidden(url: str) -> bool:
    low = (url or "").lower()
    return any(p.lower() in low for p in FORBIDDEN_PATH_SUBSTRINGS)


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


def _kr_date_to_iso(text: Optional[str]) -> Optional[str]:
    """'2026년 10월' / '2026년 10월 21일' / '2026.10.21' → 'YYYY-MM-DD'(일 없으면 01)."""
    if not text:
        return None
    m = re.search(r"(\d{4})\s*[년.\-/]\s*(\d{1,2})\s*(?:[월.\-/]\s*(\d{1,2}))?", text)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3) or 1)
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return "%04d-%02d-%02d" % (y, mo, d)


def _abs_url(href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    href = href.strip()
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return HOST + href
    return href


def _norm_key(title: str, author: str) -> str:
    t = re.sub(r"[\s\[\]()<>{}·,.\-'\"~!?]+", "", title or "").lower()
    a = re.sub(r"[\s/·,]+", "", author or "").lower()
    return t + "|" + a


def _author_text(author_el) -> str:
    """span.info_auth 텍스트 추출 — 숨김 영역(moreAuthArea: '정보 더 보기/감추기' + 전체 저자 목록) 제거."""
    if author_el is None:
        return ""
    try:
        frag = BeautifulSoup(str(author_el), "lxml")
        el = frag.select_one("span.info_auth") or frag.select_one("span.goods_auth") or frag
        for hidden in el.select("span.moreAuthArea, .moreAuthBtn, .moreAuthLi"):
            hidden.decompose()
        raw = _clean(el.get_text(" ", strip=True))
    except Exception:
        raw = _clean(author_el.get_text(" ", strip=True))
    raw = re.sub(r"\s*외\s*\d+\s*명\s*$", "", raw)   # '저 외 8명' → '저'
    raw = re.sub(r"\s*,\s*", ", ", raw)               # 'a , b' → 'a, b'
    return _clean(raw)


# --------------------------------------------------------------------------- #
# list page
# --------------------------------------------------------------------------- #
def parse_list_page(html: str, category_code: str = "001", category_label: Optional[str] = None,
                    collected_at: Optional[str] = None) -> list[dict]:
    """목록 HTML → 정규화된 책 dict 리스트. 구조가 바뀌면 예외 없이 [] 반환(경고는 호출부)."""
    if not html:
        return []
    label = category_label or GENRE_CATEGORIES.get(category_code, category_code)
    category = "국내도서>" + label
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return []
    boxes = soup.select("div.itemUnit")
    if not boxes:
        return []
    items: list[dict] = []
    for box in boxes:
        try:
            item = _parse_item_box(box, category, collected_at)
        except Exception:  # 개별 아이템 파싱 실패는 건너뛴다
            continue
        if item is not None:
            items.append(item)
    return items


def _parse_item_box(box, category: str, collected_at: Optional[str]) -> Optional[dict]:
    name_a = box.select_one("a.gd_name")
    if name_a is None:
        return None
    title = _clean(name_a.get_text(" ", strip=True))
    href = name_a.get("href") or ""
    m = re.search(r"/goods/(\d+)", href)
    if not title or not m:
        return None
    goods_no = m.group(1)
    if title.startswith(NON_BOOK_TITLE_PREFIXES):
        return None

    author_el = box.select_one("span.info_auth") or box.select_one("span.goods_auth")
    author = _author_text(author_el) if author_el is not None else ""
    pub_el = box.select_one("span.info_pub") or box.select_one("span.goods_pub")
    publisher = _clean(pub_el.get_text(" ", strip=True)) if pub_el else ""
    date_el = box.select_one("span.info_date")
    pubdate = _kr_date_to_iso(date_el.get_text(" ", strip=True)) if date_el else None

    price = price_list = None
    price_box = box.select_one("div.info_price") or box.select_one("p.goods_price")
    if price_box is not None:
        # 판매가: strong.txt_num em.yes_b  /  정가: span.txt_num.dash em.yes_m
        sale_el = price_box.select_one("em.yes_b")
        if sale_el is not None:
            price = _won_to_int(sale_el.get_text(" ", strip=True))
        list_el = price_box.select_one("em.yes_m")
        if list_el is not None:
            price_list = _won_to_int(list_el.get_text(" ", strip=True))
        if price is None:
            price = _won_to_int(price_box.get_text(" ", strip=True))
        if price_list is None:
            m_list = re.findall(r"([\d,]+)\s*원", _clean(price_box.get_text(" ", strip=True)))
            if len(m_list) >= 2:
                price_list = _won_to_int(m_list[1])
            elif m_list:
                price_list = _won_to_int(m_list[0])

    rating = None
    grade = box.select_one("span.rating_grade em.yes_b")
    if grade is not None:
        try:
            rating = float(_clean(grade.get_text(strip=True)))
        except ValueError:
            rating = None

    cover_url = None
    img = box.select_one("div.item_img img") or box.select_one("img[data-original]") or box.select_one("img")
    if img is not None:
        cand = img.get("data-original") or img.get("src") or ""
        if cand and "Noimg" not in cand and "blank.gif" not in cand:
            cover_url = _abs_url(cand)

    return {
        "id": "yes24:" + goods_no,
        "source": SOURCE,
        "title": title,
        "subtitle": None,
        "author": author or None,
        "publisher": publisher or None,
        "pubdate": pubdate,
        "isbn13": None,
        "item_code": goods_no,
        "price": price,
        "price_list": price_list,
        "rating": rating,
        "cover_url": cover_url,
        "link": DETAIL_URL_TMPL.format(goods_no=goods_no),
        "category": category,
        "description": None,
        "collected_at": collected_at,
    }


# --------------------------------------------------------------------------- #
# detail page
# --------------------------------------------------------------------------- #
def parse_detail_page(html: str) -> dict:
    """상세 HTML → {isbn13, description, category_path, pubdate, pages}. 실패해도 {}."""
    out: dict = {}
    if not html:
        return out
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return out

    # 품목정보 테이블
    spec = soup.select_one("#infoset_specific")
    if spec is not None:
        for tr in spec.select("tr"):
            th = tr.select_one("th")
            td = tr.select_one("td")
            if th is None or td is None:
                continue
            key = _clean(th.get_text(" ", strip=True))
            val = _clean(td.get_text(" ", strip=True))
            if key.startswith("ISBN13"):
                m = re.search(r"(97[89]\d{10})", val)
                if m:
                    out["isbn13"] = m.group(1)
            elif key.startswith("발행일"):
                iso = _kr_date_to_iso(val)
                if iso:
                    out["pubdate"] = iso
            elif key.startswith("쪽수"):
                m = re.search(r"(\d+)\s*쪽", val)
                if m:
                    out["pages"] = int(m.group(1))

    # 책소개
    intro = soup.select_one("#infoset_introduce")
    if intro is not None:
        body = intro.select_one("div.infoWrap_txtInner") or intro.select_one("div.infoWrap_txt")
        desc = _clean(body.get_text(" ", strip=True)) if body is not None else ""
        if not desc:
            md = intro.select_one("div.infoWrap_mdBox")
            desc = _clean(md.get_text(" ", strip=True)) if md is not None else ""
        if desc:
            out["description"] = desc[:4000]

    # 카테고리 분류 체인 (첫 번째 dl = 카테고리 분류)
    cate = soup.select_one("#infoset_goodsCate")
    if cate is not None:
        dl = cate.select_one("dl")
        chain: list[str] = []
        if dl is not None:
            for a in dl.select("a"):
                t = _clean(a.get_text(strip=True))
                if not t:
                    continue
                if t in chain:  # '국내도서' 가 체인 중간에 반복되는 경우 중단
                    break
                chain.append(t)
        # 2단계 미만이면 카테고리 세분류로 쓰지 않는다
        if len(chain) >= 3:
            out["category_path"] = ">".join(chain[:4])
    return out


def is_valid_list_html(html: str) -> bool:
    """목록 페이지로 보이는지(구조 변경 감지)."""
    if not html:
        return False
    return ("itemUnit" in html) and ("yes24" in html.lower())


def page_url(category_code: str, page: int, page_size: int = DEFAULT_PAGE_SIZE) -> str:
    return LIST_URL_TMPL.format(cid=category_code, page=page, size=page_size)


def detail_url(goods_no: str) -> str:
    return DETAIL_URL_TMPL.format(goods_no=goods_no)
