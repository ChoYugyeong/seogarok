"""SEO 랜딩(/book/{id}) + 책 사이트맵.

서버 표준 라이브러리만 사용. DB 책 18k권을 검색 유입용 정적 페이지로 노출한다.
"""
from __future__ import annotations

import os

import html
import time
from urllib.parse import quote

BASE = "https://seogarok.com"
SUB_LABEL = {"millie": "밀리", "ridiselect": "리디셀렉트", "sam": "교보 sam", "willa": "윌라"}


def esc(v) -> str:
    return html.escape(str(v if v is not None else ""), quote=True)


def _fallback_desc(book: dict) -> str:
    """설명이 없는 책용 고유 요약(속성 기반)."""
    bits = [
        f"『{book.get('title') or ''}』은(는) {book.get('author') or '저자 미상'}의 책으로",
        f"{book.get('publisher') or ''}에서 {(book.get('pubdate') or '')[:4]}년에 출간되었습니다."
        if book.get("publisher")
        else "출간 정보가 제한적입니다.",
    ]
    cat = " ".join((book.get("category") or "").replace(">", " ").split())
    if cat:
        bits.append(f"분야는 {cat}입니다.")
    if book.get("pages"):
        bits.append(f"분량은 {book['pages']}쪽입니다.")
    price = book.get("price")
    if price:
        bits.append(f"예스24 판매가는 {int(price):,}원입니다.")
    if book.get("isbn13"):
        bits.append(f"ISBN은 {book['isbn13']}입니다.")
    return " ".join(bits)


def _desc(book: dict) -> str:
    text = (book.get("description") or "").strip()
    if text:
        return " ".join(text.split())[:280]
    return _fallback_desc(book)


def book_jsonld(book: dict, av: dict, base: str = BASE) -> str:
    import json

    canon = f"{base}/book/{quote(str(book['id']), safe='')}"
    author = (book.get("author") or "").split("/")[0].replace(" 저", "").strip()
    data = {
        "@context": "https://schema.org",
        "@type": "Book",
        "name": book.get("title"),
        "author": {"@type": "Person", "name": author or "저자 미상"},
        "url": canon,
        "publisher": book.get("publisher") or None,
        "datePublished": (book.get("pubdate") or "")[:10] or None,
        "isbn": book.get("isbn13") or None,
        "image": book.get("cover_url") or None,
        "description": _desc(book),
        "inLanguage": "ko",
        "numberOfPages": book.get("pages") or None,
        "publisher": {
            "@type": "Organization",
            "name": book.get("publisher") or "서가록",
        },
        "mainEntityOfPage": canon,
    }
    price = book.get("price")
    if price:
        data["offers"] = {
            "@type": "Offer",
            "price": int(price),
            "priceCurrency": "KRW",
            "availability": "https://schema.org/InStock",
            "url": book.get("link") or canon,
        }
    crumbs = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "서가록", "item": f"{base}/"},
            {"@type": "ListItem", "position": 2, "name": book.get("title"), "item": canon},
        ],
    }
    return (
        '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + "</script>\n"
        '<script type="application/ld+json">' + json.dumps(crumbs, ensure_ascii=False) + "</script>"
    )


def av_rows(av: dict) -> str:
    rows = []
    for key, label in SUB_LABEL.items():
        v = (av or {}).get(key) or {}
        state = v.get("s")
        if state == "ending":
            d = v.get("d")
            text = f"{d}일 뒤 종료 예정" if isinstance(d, int) and d >= 0 else "종료 예정"
            rows.append(f'<li class="end"><b>{esc(label)}</b><span>{esc(text)}</span></li>')
        elif state == "available":
            rows.append(f'<li><b>{esc(label)}</b><span>구독으로 읽기 가능</span></li>')
    if not rows:
        rows.append('<li class="muted"><b>구독 가용성</b><span>확인된 정보 없음 · 제보로 확인 중</span></li>')
    return "".join(rows)




def _ads_head() -> str:
    """AdSense: 게시자 ID가 설정된 경우에만 동의 게이트 스크립트를 넣는다."""
    client = (os.getenv("ADSENSE_CLIENT") or "").strip()
    if not client.startswith("ca-pub-"):
        return ""
    return (
        f'<meta name="seogarok-adsense-client" content="{esc(client)}" />\n'
        f'<meta name="google-adsense-account" content="{esc(client)}" />\n'
        '<script src="/ads.js" defer></script>'
    )


def book_page_html(book: dict, av: dict, notices: list[dict], related: list[dict] | None = None, base: str = BASE) -> str:
    bid = str(book["id"])
    canon = f"{base}/book/{quote(bid, safe='')}"
    title = f"{book.get('title')} — {book.get('author') or '저자 미상'} · 서가록"
    desc = _desc(book)
    cover = book.get("cover_url") or ""
    price = book.get("price")
    price_txt = f"{int(price):,}원" if price else ""
    facts = [book.get("publisher"), (book.get("pubdate") or "")[:10], f"{book['pages']}쪽" if book.get("pages") else None, f"ISBN {book['isbn13']}" if book.get("isbn13") else None]
    fact_html = " · ".join(esc(f) for f in facts if f)
    notice_txt = ""
    if notices:
        parts = [f"{SUB_LABEL.get(n.get('platform'), n.get('platform'))} {(n.get('ends_at') or '')[:10]} 종료" for n in notices[:3]]
        notice_txt = f'<p class="notice">종료 공지 · {esc(" / ".join(parts))}</p>'
    app_url = f"/#book={quote(bid, safe='')}"
    # 설명·공지·평점 등 고유 정보가 전혀 없는 페이지만 색인 제외 (thin content 보호)
    _raw_desc = (book.get("description") or "").strip()
    _has_signal = bool(_raw_desc) or bool(notices) or bool(book.get("rating")) or bool(book.get("pages"))
    robots_meta = "" if _has_signal else '<meta name="robots" content="noindex,follow" />' 
    avail_bits = []
    for _k, _label in SUB_LABEL.items():
        _v = (av or {}).get(_k) or {}
        if _v.get("s") == "ending":
            _d = _v.get("d")
            avail_bits.append(f"{_label} {'D-' + str(_d) if isinstance(_d, int) and _d >= 0 else ''} 종료 예정".replace("  ", " "))
        elif _v.get("s") == "available":
            avail_bits.append(f"{_label} 구독 가능")
    if avail_bits:
        answer_line = f"{book.get('title')}은(는) " + ", ".join(avail_bits) + f" ({time.strftime('%Y-%m-%d')} 확인)"
    else:
        answer_line = f"{book.get('title')}의 구독 가용성은 확인된 정보가 없습니다. 제보로 확인 중입니다."
    related = related or []
    related_html = ""
    if related:
        cards = "".join(
            f'<a class="rel-card" href="/book/{esc(quote(str(r["id"]), safe=""))}">'
            + (f'<img src="{esc(r.get("cover_url") or "")}" alt="" loading="lazy" />' if r.get("cover_url") else "")
            + f'<b>{esc(r.get("title") or "")}</b><span>{esc(r.get("author") or "")}</span></a>'
            for r in related[:6]
        )
        related_html = f'<section class="related"><h2>이 책과 함께 보는 책</h2><div class="rel-grid">{cards}</div></section>' 
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}" />
<link rel="canonical" href="{esc(canon)}" />
<meta property="og:type" content="book" />
<meta property="og:title" content="{esc(book.get('title') or '')}" />
<meta property="og:description" content="{esc(desc)}" />
<meta property="og:url" content="{esc(canon)}" />
<meta property="og:image" content="{esc(cover)}" />
<meta property="og:site_name" content="서가록" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{esc(book.get('title') or '')}" />
<meta name="twitter:description" content="{esc(desc)}" />
<meta name="twitter:image" content="{esc(cover)}" />
{robots_meta}
<link rel="stylesheet" href="/styles.css" />
{_ads_head()}
<link rel="alternate" type="text/markdown" href="/book/{esc(quote(bid, safe=''))}.md" />
{book_jsonld(book, av, base)}
<style>
.book-page{{max-width:920px;margin:0 auto;padding:32px 20px 72px}}
.book-page .back{{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--text-3);margin-bottom:20px}}
.book-hero{{display:grid;grid-template-columns:200px minmax(0,1fr);gap:28px;align-items:start}}
.book-hero img{{width:100%;border-radius:10px;border:1px solid var(--line);background:var(--surface)}}
.book-hero h1{{font-size:30px;font-weight:800;letter-spacing:-.03em;line-height:1.28;margin-bottom:8px}}
.book-hero .author{{font-size:15px;color:var(--text-2);margin-bottom:6px}}
.book-hero .facts{{font-size:12.5px;color:var(--text-3);margin-bottom:16px}}
.book-hero .price{{font-size:18px;font-weight:800;color:var(--accent);margin-bottom:16px}}
.book-hero .summary{{font-size:15px;line-height:1.7;color:var(--text-2)}}
.av-list{{list-style:none;padding:0;margin:24px 0;display:grid;gap:8px}}
.av-list li{{display:flex;justify-content:space-between;gap:12px;padding:12px 14px;background:var(--surface);border-radius:10px;font-size:14px}}
.av-list li b{{font-weight:700}}
.av-list li span{{color:var(--text-2)}}
.av-list li.end{{background:var(--danger-soft)}}
.av-list li.end b,.av-list li.end span{{color:var(--danger)}}
.av-list li.muted b,.av-list li.muted span{{color:var(--text-3)}}
.notice{{font-size:13px;color:var(--danger);margin:8px 0 0}}
.cta{{display:inline-flex;align-items:center;gap:8px;margin-top:22px;padding:13px 22px;border-radius:12px;background:var(--accent);color:#fff;font-weight:800;font-size:15px}}
.cta:hover{{background:#a02f19}}
.related{{margin-top:32px}}
.related h2{{font-size:19px;font-weight:800;letter-spacing:-.02em;margin:0 0 12px}}
.rel-grid{{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px}}
.rel-card{{display:flex;flex-direction:column;gap:5px;color:inherit}}
.rel-card img{{width:100%;aspect-ratio:3/4.3;object-fit:cover;border-radius:8px;border:1px solid var(--line);background:var(--surface)}}
.rel-card b{{font-size:12.5px;font-weight:700;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.rel-card span{{font-size:11.5px;color:var(--text-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
@media (max-width:640px){{.rel-grid{{grid-template-columns:repeat(3,minmax(0,1fr))}}}}
.answer{{font-size:13.5px;line-height:1.6;background:var(--accent-soft);padding:10px 12px;border-radius:8px;margin:12px 0 0}} .answer b{{color:var(--accent)}}
.book-foot{{margin-top:36px;padding-top:18px;border-top:1px solid var(--line);font-size:12.5px;color:var(--text-3);line-height:1.7}}
@media (max-width:640px){{.book-hero{{grid-template-columns:120px minmax(0,1fr);gap:16px}}.book-hero h1{{font-size:22px}}}}
</style>
</head>
<body>
<main class="book-page">
  <a class="back" href="/">← 서가록 홈</a>
  <div class="book-hero">
    <img src="{esc(cover)}" alt="{esc(book.get('title') or '')} 표지" />
    <div>
      <h1>{esc(book.get('title') or '')}</h1>
      <p class="author">{esc(book.get('author') or '저자 미상')}</p>
      <p class="facts">{fact_html}</p>
      {f'<p class="price">{esc(price_txt)}</p>' if price_txt else ''}
      <p class="summary">{esc(desc)}</p>
      <p class="answer"><b>한 줄 요약</b> · {esc(answer_line)}</p>
      {notice_txt}
      <a class="cta" href="{esc(app_url)}">서가록에서 가용성 보기 →</a>
    </div>
  </div>
  <h2 style="margin:28px 0 4px;font-size:18px;font-weight:800">어디서 읽을 수 있나요</h2>
  <ul class="av-list">{av_rows(av)}</ul>
  {related_html}
  <p class="book-foot">
    서가록은 밀리·리디셀렉트·교보 sam·윌라의 제공 여부와 종료 예정 공지를 매일 확인합니다.
    확인되지 않은 정보는 “미확인”으로 표시하며, 제보를 통해 보강합니다.
    구매 가격은 예스24 기준입니다.
  </p>
</main>
</body>
</html>"""


def sitemap_books_xml(rows: list[dict], base: str = BASE) -> str:
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for r in rows:
        bid = str(r["id"])
        loc = f"{base}/book/{quote(bid, safe='')}"
        parts.append(f"<url><loc>{esc(loc)}</loc><changefreq>weekly</changefreq><priority>0.6</priority></url>")
    parts.append("</urlset>")
    return "\n".join(parts)


def books_index_html(rows: list[dict], page: int, pages: int, base: str = BASE) -> str:
    cards = "".join(
        f'<a class="rel-card" href="/book/{esc(quote(str(r["id"]), safe=""))}">'
        + (f'<img src="{esc(r.get("cover_url") or "")}" alt="" loading="lazy" />' if r.get("cover_url") else "")
        + f'<b>{esc(r.get("title") or "")}</b><span>{esc(r.get("author") or "")}</span></a>'
        for r in rows
    )
    prev_link = f'<a class="pg" href="/books?page={page - 1}">← 이전</a>' if page > 1 else "<span></span>"
    next_link = f'<a class="pg" href="/books?page={page + 1}">다음 →</a>' if page < pages else "<span></span>"
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>서가록 모든 책 {page}쪽 — 구독 가용성 색인</title>
<meta name="description" content="서가록에 색인된 책 목록. 밀리·리디셀렉트·교보 sam·윌라 구독 가용성과 종료 예정일을 확인하세요." />
<link rel="canonical" href="{esc(base)}/books?page={page}" />
<link rel="stylesheet" href="/styles.css" />
{_ads_head()}
<style>
.books-page{{max-width:1080px;margin:0 auto;padding:30px 20px 64px}}
.books-page h1{{font-size:26px;font-weight:800;letter-spacing:-.03em;margin:6px 0}}
.books-page .back{{font-size:13px;color:var(--text-3)}}
.books-page .lead{{font-size:13px;color:var(--text-3);margin-bottom:22px}}
.pg{{display:inline-flex;align-items:center;min-height:36px;padding:0 14px;border-radius:10px;background:var(--surface);color:var(--text-2);font-size:13.5px}}
.pager{{display:flex;justify-content:space-between;margin:22px 0}}
</style>
</head>
<body>
<main class="books-page">
  <a class="back" href="/">← 서가록 홈</a>
  <h1>모든 책</h1>
  <p class="lead">색인된 책 {pages}쪽 중 {page}쪽 · 구독 가용성은 각 책 페이지에서 확인하세요.</p>
  <div class="rel-grid">{cards}</div>
  <div class="pager">{prev_link}{next_link}</div>
</main>
</body>
</html>"""
