"""Dashboard + shared placeholder renderer."""
from flask import Blueprint, render_template

from ..models import banner as banner_model
from ..models import content as content_model
from ..models import post as post_model

bp = Blueprint("main", __name__)

PHASE_LABEL = {2: "P2 인증·마이페이지", 3: "P3 캠페인", 4: "P4 어드민·커뮤니티·도구", 5: "P5 운영"}


def render_placeholder(title, phase=None, desc=None):
    """'준비 중' page used by every route not implemented in the current phase."""
    return render_template("placeholder.html", title=title, phase_label=PHASE_LABEL.get(phase), desc=desc)


@bp.route("/design/sidebar")
def design_sidebar():
    """Temporary color-scheme comparison page for the customer (2026-09-02)."""
    colors = [("255,182,193", "#FFB6C1", ""), ("255,192,203", "#FFC0CB", ""),
              ("32,178,170", "#20B2AA", ""), ("144,238,144", "#90EE90", ""),
              ("30,41,59", "#1E293B", "추천 · 딥 네이비"), ("31,111,84", "#1F6F54", "추천 · 딥 에메랄드"),
              ("46,139,87", "#2E8B57", "추천 · 시그린"), ("176,141,87", "#B08D57", "추천 · 골드 브론즈"),
              ("181,126,220", "#B57EDC", "추천 · 라벤더"), ("214,90,126", "#D65A7E", "추천 · 로즈")]
    return render_template("main/theme_preview.html", colors=colors)


@bp.route("/")
def dashboard():
    grid_banners = banner_model.list_active_banners(8, "grid")
    slide_banners = banner_model.list_active_banners(6, "slide")
    notices = content_model.dashboard_notices(5)
    anon_posts = post_model.latest_anon_posts(5)
    return render_template("main/dashboard.html", grid_banners=grid_banners, slide_banners=slide_banners,
                           notices=notices, anon_posts=anon_posts)
