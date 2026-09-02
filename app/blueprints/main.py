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


@bp.route("/")
def dashboard():
    grid_banners = banner_model.list_active_banners(8, "grid")
    slide_banners = banner_model.list_active_banners(6, "slide")
    notices = content_model.dashboard_notices(5)
    anon_posts = post_model.latest_anon_posts(5)
    return render_template("main/dashboard.html", grid_banners=grid_banners, slide_banners=slide_banners,
                           notices=notices, anon_posts=anon_posts)
