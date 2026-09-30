"""Landing (anonymous) / dashboard (members) + robots·sitemap + shared placeholder renderer."""
from flask import Blueprint, Response, g, render_template, request, url_for

from ..models import banner as banner_model
from ..models import content as content_model
from ..models import post as post_model

bp = Blueprint("main", __name__)

PHASE_LABEL = {2: "P2 인증·마이페이지", 3: "P3 캠페인", 4: "P4 어드민·커뮤니티·도구", 5: "P5 운영"}


def render_placeholder(title, phase=None, desc=None):
    """'준비 중' page used by every route not implemented in the current phase."""
    return render_template("placeholder.html", title=title, phase_label=PHASE_LABEL.get(phase), desc=desc)


@bp.route("/")
def dashboard():
    """비로그인은 홍보용 랜딩, 회원은 대시보드 (2026-09-30 JDH "홍보용 페이지로도 쓸 수 있게")."""
    if not g.get("user"):
        return landing()
    return _dashboard()


@bp.route("/dashboard")
def dashboard_page():
    """대시보드 직접 진입 — 비로그인도 볼 수 있다 (랜딩의 '둘러보기')."""
    return _dashboard()


def _dashboard():
    grid_banners = banner_model.list_active_banners(8, "grid")
    slide_banners = banner_model.list_active_banners(6, "slide")
    notices = content_model.dashboard_notices(5)
    anon_posts = post_model.latest_anon_posts(10)
    from ..blueprints.campaign import traffic_list
    from ..constants import TRAFFIC_CHANNELS
    traffic_top = {ch: traffic_list(ch)[:5] for ch, _ in TRAFFIC_CHANNELS}
    return render_template("main/dashboard.html", grid_banners=grid_banners, slide_banners=slide_banners,
                           notices=notices, anon_posts=anon_posts, channels=TRAFFIC_CHANNELS, traffic_top=traffic_top)


@bp.route("/intro")
def landing():
    """홍보용 랜딩 — 앱 셸 없이 단독 화면. 숫자(매체 수·최저 단가·정책값)는 DB·상수에서 읽는다."""
    from ..constants import BANK_DUE_DAYS, CHANNEL_LABEL, MEDIA_MIN_DAILY, ORDER_CUTOFF, TRAFFIC_CHANNELS
    from ..models import media as media_model
    from ..services import credit_service
    channels = []
    for ch, label in TRAFFIC_CHANNELS:
        medias = media_model.list_by_channel(ch)
        prices = [m["unit_price"] for m in medias if m.get("unit_price")]
        channels.append({"key": ch, "label": label, "count": len(medias),
                         "min_price": min(prices) if prices else None,
                         "tracked": ch in ("store", "place")})
    return render_template("landing.html", channels=channels, channel_label=CHANNEL_LABEL,
                           total_media=sum(c["count"] for c in channels),
                           min_charge=credit_service.MIN_CHARGE, bank_due_days=BANK_DUE_DAYS,
                           order_cutoff=ORDER_CUTOFF, min_daily=MEDIA_MIN_DAILY)


@bp.route("/robots.txt")
def robots():
    origin = _origin()
    body = "\n".join([
        "User-agent: *",
        "Disallow: /admin", "Disallow: /my", "Disallow: /campaign", "Disallow: /credit",
        "Disallow: /notifications", "Disallow: /api", "Disallow: /auth/admin",
        "Allow: /",
        f"Sitemap: {origin}/sitemap.xml", "",
    ])
    return Response(body, mimetype="text/plain")


@bp.route("/sitemap.xml")
def sitemap():
    origin = _origin()
    pages = [("/", "1.0"), ("/intro", "0.9"), ("/popular", "0.8"), ("/guide", "0.8"), ("/auth/register", "0.7"),
             ("/auth/login", "0.5"), ("/notice", "0.5"), ("/terms", "0.2"), ("/privacy", "0.2")]
    items = "".join(f"<url><loc>{origin}{p}</loc><priority>{pr}</priority></url>" for p, pr in pages)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>'
    return Response(xml, mimetype="application/xml")


def _origin():
    from flask import current_app
    return current_app.config["PUBLIC_URL"] or request.url_root.rstrip("/")
