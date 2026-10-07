"""SEO 콘텐츠 허브 — /learn/ 기본 페이지 · /blog/ · /rss.xml · sitemap 인덱스 (2026-10-07, docs/SEO_PLAN.md).

주소는 끝 슬래시로 통일한다(Flask 가 슬래시 없는 주소를 영구 리다이렉트). 데이터에 없는 조합은
진짜 404 — 빈 페이지를 200 으로 내면 soft 404 로 잡힌다.
"""
from datetime import date
from xml.sax.saxutils import escape

from flask import Blueprint, Response, abort, current_app, render_template, request

from ..models import media as media_model
from ..services import blog, jsonld, seo_pages

bp = Blueprint("seo", __name__)
BLOG_PER_PAGE = 20


def _origin():
    return current_app.config["PUBLIC_URL"] or request.url_root.rstrip("/")


def _prices():
    """채널별 최저 단가 — 비용 예시·Service 구조화 데이터에 쓴다. 매체가 없으면 0."""
    out = {}
    for ch in ("place", "store", "coupang"):
        ps = [m["unit_price"] for m in media_model.list_by_channel(ch) if m.get("unit_price")]
        out[ch] = min(ps) if ps else 0
    return out


@bp.route("/learn/")
def learn_index():
    h = seo_pages.hub()
    o = _origin()
    items = [(f"{b} 마케팅", f"/learn/{b}-마케팅/") for b in h["biz"]]
    return render_template("learn/index.html", h=h, meta=seo_pages.meta(),
                           meta_title=f"셀프 마케팅 가이드 · 지역·업종별 검색량 {h['count']}개 페이지 — {current_app.config['APP_NAME']}",
                           meta_desc="플레이스·스마트스토어를 직접 운영하려는 사업자를 위한 지역·업종별 네이버 검색량과 셀프 세팅 가이드. 실제 검색량 데이터로 우리 상권부터 확인하세요.",
                           jsonld=[jsonld.breadcrumb(o, [("셀프 마케팅 가이드", None)], "/learn/"),
                                   jsonld.itemlist(o, items[:100])])


@bp.route("/learn/<slug>/")
def learn_page(slug):
    prices = _prices()
    page = seo_pages.build(slug, prices)
    if not page:
        abort(404)
    o, name = _origin(), current_app.config["APP_NAME"]
    lds = [jsonld.breadcrumb(o, page["crumbs"], page["path"])]
    if page["faq"]:
        lds.append(jsonld.faq(page["faq"]))
    lists = [s["itemlist"] for s in page["sections"] if s.get("itemlist")]
    if lists:
        lds.append(jsonld.itemlist(o, [(n, p) for n, p, _ in lists[0]]))
    if page.get("region") and page.get("sido"):
        lds.append(jsonld.place_area(page["region"], page["sido"]))
    if prices.get(page["channel"]):
        lds.append(jsonld.service(o, f"{page['kw']} 셀프 유입 캠페인", page["desc"], page["path"], prices[page["channel"]], name))
    return render_template("learn/page.html", page=page, meta=seo_pages.meta(), prices=prices,
                           meta_title=page["title"], meta_desc=page["desc"], jsonld=lds)


@bp.route("/blog/")
def blog_index():
    all_posts = blog.posts()
    page = max(1, request.args.get("page", 1, type=int))
    rows = all_posts[(page - 1) * BLOG_PER_PAGE: page * BLOG_PER_PAGE]
    if page > 1 and not rows:
        abort(404)
    o = _origin()
    return render_template("learn/blog_index.html", rows=rows, page=page,
                           total_pages=max(1, -(-len(all_posts) // BLOG_PER_PAGE)),
                           meta_title=f"셀프 마케팅 블로그 — {current_app.config['APP_NAME']}",
                           meta_desc="플레이스·스마트스토어·쿠팡을 직접 운영하는 사업자를 위한 실행 가이드. 셀프 세팅 순서, 체크리스트, 비용 계산, 도구 사용법을 정리합니다.",
                           jsonld=[jsonld.breadcrumb(o, [("블로그", None)], "/blog/"),
                                   jsonld.itemlist(o, [(p["title"], p["path"]) for p in rows])])


@bp.route("/blog/<slug>/")
def blog_post(slug):
    p = blog.get(slug)
    if not p:
        abort(404)
    o, name = _origin(), current_app.config["APP_NAME"]
    newer = [x for x in blog.posts() if x["slug"] != slug][:6]
    return render_template("learn/blog_post.html", p=p, more=newer, og_type="article",
                           meta_title=p["title"], meta_desc=p["desc"],
                           jsonld=[jsonld.breadcrumb(o, [("블로그", "/blog/"), (p["title"], None)], p["path"]),
                                   jsonld.article(o, p, name)])


@bp.route("/rss.xml")
def rss():
    o, name = _origin(), current_app.config["APP_NAME"]
    items = "".join(
        f"<item><title>{escape(p['title'])}</title><link>{o}{p['path']}</link><guid>{o}{p['path']}</guid>"
        f"<description>{escape(p['desc'])}</description><pubDate>{p['date'].strftime('%a, %d %b %Y 09:00:00 +0900')}</pubDate></item>"
        for p in blog.posts()[:50])
    xml = (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{escape(name)} 블로그</title>'
           f"<link>{o}/blog/</link><description>셀프 마케팅 실행 가이드</description><language>ko</language>{items}</channel></rss>")
    return Response(xml, mimetype="application/rss+xml")


# ---- sitemap: 인덱스 + 묶음 (5만 개 한도 아래로) -------------------------------------
STATIC_PAGES = [("/", "1.0"), ("/intro", "0.9"), ("/learn/", "0.9"), ("/blog/", "0.8"), ("/popular", "0.8"),
                ("/guide", "0.8"), ("/auth/register", "0.7"), ("/tools/keyword", "0.6"), ("/notice", "0.5"),
                ("/terms", "0.2"), ("/privacy", "0.2")]


def _urlset(rows):
    from urllib.parse import quote
    body = "".join(f"<url><loc>{escape(quote(loc, safe=':/'))}</loc>{f'<lastmod>{lm}</lastmod>' if lm else ''}"
                   f"<priority>{pr}</priority></url>" for loc, lm, pr in rows)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>',
                    mimetype="application/xml")


@bp.route("/sitemap.xml")
def sitemap_index():
    o, today = _origin(), date.today().isoformat()
    maps = "".join(f"<sitemap><loc>{o}/sitemap-{n}.xml</loc><lastmod>{today}</lastmod></sitemap>" for n in ("static", "learn", "blog"))
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{maps}</sitemapindex>',
                    mimetype="application/xml")


@bp.route("/sitemap-<name>.xml")
def sitemap_part(name):
    o = _origin()
    if name == "static":
        return _urlset([(o + p, None, pr) for p, pr in STATIC_PAGES])
    if name == "learn":
        lm = seo_pages.meta().get("collected")
        pr = {"bizhub": "0.8", "topic": "0.8", "regionhub": "0.7", "bizangle": "0.7", "regionbiz": "0.6", "storecat": "0.6"}
        return _urlset([(o + p, lm, pr[k]) for p, k, _ in seo_pages.all_paths()])
    if name == "blog":
        return _urlset([(o + p["path"], max(p["date"], p["updated"]).isoformat(), "0.6") for p in blog.posts()])
    abort(404)
