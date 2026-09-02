"""Flask application factory, sidebar MENU constant, context processors."""
from datetime import date, datetime

from flask import Flask, g, request

from .config import Config

# Sidebar menu. Keep in sync with sidebar.html / bottom_tab.html whenever a route is added.
# item = {label, icon (lucide name), href, external?, children?: [{label, href}], key?}
MENU = {
    "user": [
        {
            "title": "기본",
            "items": [
                {"label": "공지사항", "icon": "megaphone", "href": "/notice"},
                {"label": "카카오 바로상담", "icon": "message-circle", "href": Config.KAKAO_CHAT_URL, "external": True},
            ],
        },
        {
            "title": "유입관리",
            "items": [
                {
                    "label": "쇼핑·스토어", "icon": "shopping-bag", "key": "store",
                    "children": [
                        {"label": "캠페인 생성", "href": "/campaign/store/new"},
                        {"label": "캠페인 관리", "href": "/campaign/store"},
                        {"label": "쇼핑 작업량 권장 체크", "href": "/campaign/store/slots"},
                    ],
                },
                {
                    "label": "쿠팡", "icon": "package", "key": "coupang",
                    "children": [
                        {"label": "캠페인 생성", "href": "/campaign/coupang/new"},
                        {"label": "캠페인 관리", "href": "/campaign/coupang"},
                    ],
                },
                {
                    "label": "플레이스", "icon": "map-pin", "key": "place",
                    "children": [
                        {"label": "캠페인 생성", "href": "/campaign/place/new"},
                        {"label": "캠페인 관리", "href": "/campaign/place"},
                    ],
                },
                {"label": "인기 트래픽", "icon": "trending-up", "href": "/popular"},
            ],
        },
        {
            "title": "마케팅도구",
            "items": [
                {"label": "키워드 조회", "icon": "search", "href": "/tools/keyword"},
                {"label": "연관키워드 조회", "icon": "link", "href": "/tools/related"},
            ],
        },
        {
            "title": "커뮤니티",
            "items": [
                {"label": "익명 게시판", "icon": "venetian-mask", "href": "/community/anon"},
                {"label": "질문답변", "icon": "circle-help", "href": "/community/qna"},
                {"label": "마케팅 정보", "icon": "trending-up", "href": "/community/info"},
            ],
        },
    ],
    "admin": [
        {
            "title": "운영",
            "items": [
                {"label": "운영 현황", "icon": "trending-up", "href": "/admin"},
                {"label": "주문 관리", "icon": "map-pin", "href": "/admin/orders"},
                {"label": "결제 내역", "icon": "credit-card", "href": "/admin/payments"},
            ],
        },
        {
            "title": "설정",
            "items": [
                {"label": "매체사 관리", "icon": "package", "href": "/admin/media"},
                {"label": "인기 트래픽 설정", "icon": "trending-up", "href": "/admin/popular"},
                {"label": "공지 · 정보글", "icon": "pen-line", "href": "/admin/content"},
                {"label": "배너 관리", "icon": "image", "href": "/admin/banners"},
            ],
        },
        {
            "title": "회원 · 커뮤니티",
            "items": [
                {"label": "회원 목록", "icon": "circle-help", "href": "/admin/users"},
                {"label": "대행의뢰 · 제안", "icon": "message-circle", "href": "/admin/agency"},
                {"label": "신고 · 블라인드", "icon": "venetian-mask", "href": "/admin/reports"},
            ],
        },
    ],
}

# Routes that are not in the sidebar but still need a breadcrumb label.
EXTRA_CRUMBS = {
    "/": (None, "대시보드"),
    "/my": (None, "마이페이지"),
    "/guide": (None, "이용가이드"),
    "/settings": (None, "설정"),
    "/auth/login": (None, "로그인 · 회원가입"),
    "/auth/register": (None, "회원가입"),
    "/auth/kakao": (None, "로그인"),
    "/terms": (None, "이용약관"),
    "/privacy": (None, "개인정보처리방침"),
    "/auth/kakao/callback": (None, "로그인"),
    "/auth/logout": (None, "로그아웃"),
    "/notifications": (None, "알림"),
    "/my/posts": ("마이페이지", "내가 쓴 글"),
}


def _flatten_menu():
    """Return list of (href, parent_label, label) for every internal link."""
    out = []
    for mode in ("user", "admin"):
        for sec in MENU[mode]:
            for item in sec["items"]:
                if item.get("external"):
                    continue
                if "children" in item:
                    for ch in item["children"]:
                        out.append((ch["href"], item["label"], ch["label"]))
                else:
                    parent = "관리자" if mode == "admin" else sec["title"]
                    out.append((item["href"], parent, item["label"]))
    for href, (parent, label) in EXTRA_CRUMBS.items():
        out.append((href, parent, label))
    return out


_LINKS = _flatten_menu()


def resolve_active(path):
    """Longest-prefix match so /campaign/store and /campaign/store/new are distinct."""
    best = None
    for href, parent, label in _LINKS:
        if path == href or (href != "/" and path.startswith(href + "/")):
            if best is None or len(href) > len(best[0]):
                best = (href, parent, label)
    return best


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    from . import db
    from .services import notify_service
    db.init_app(app)

    from .blueprints import main, auth, notice, campaign, tools, community, my, admin
    for bp in (main.bp, auth.bp, notice.bp, campaign.bp, campaign.api, campaign.pop, tools.bp, community.bp, community.notif_bp, my.bp, admin.bp):
        app.register_blueprint(bp)

    app.before_request(auth.load_current_user)

    @app.context_processor
    def inject_layout():
        path = request.path
        is_admin_path = path == "/admin" or path.startswith("/admin/")
        active = resolve_active(path)
        user = g.get("user")
        try:
            from .models import settings as settings_model
            sv = settings_model.get_all()
        except Exception:
            sv = {}
        strip = {"on": sv.get("strip_on") == "1", "text": sv.get("strip_text") or "",
                 "link": sv.get("strip_link") or "", "bg": sv.get("strip_bg") or "#2563EB"}
        return {
            "APP_NAME": app.config["APP_NAME"], "strip": strip,
            "KAKAO_CHAT_URL": app.config["KAKAO_CHAT_URL"],
            "MENU": MENU,
            "current_user": user,
            "unread_count": notify_service.unread_count(user["id"]) if user else 0,
            "needs_onboarding": auth.needs_onboarding(user),
            "is_admin_path": is_admin_path,
            "active_href": active[0] if active else None,
            "crumb_parent": active[1] if active else None,
            "crumb_label": active[2] if active else "대시보드",
        }

    @app.template_filter("fmt_date")
    def fmt_date(v, fmt="%m.%d"):
        if not v:
            return ""
        if isinstance(v, (datetime, date)):
            return v.strftime(fmt)
        return str(v)

    @app.template_filter("won")
    def won(v):
        try:
            return f"{int(v):,}원"
        except (TypeError, ValueError):
            return v

    @app.template_filter("fmt_num")
    def fmt_num(v):
        try:
            return f"{int(v):,}"
        except (TypeError, ValueError):
            return v

    return app
