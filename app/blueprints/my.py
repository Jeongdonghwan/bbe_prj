"""/my — mypage; /guide placeholder; /settings → /my."""
import re

from flask import Blueprint, current_app, flash, g, jsonify, redirect, render_template, request, session, url_for

from ..constants import CHANNEL_LABEL, GRADE_LABEL, STATUS_CLASS, STATUS_LABEL
from ..models import agency as agency_model
from ..models import campaign as campaign_model
from ..models import user as user_model
from .auth import login_required
from .main import render_placeholder

bp = Blueprint("my", __name__)

BIZ_NO_RE = re.compile(r"^\d{3}-?\d{2}-?\d{5}$")


def mask_phone(phone):
    if not phone:
        return "-"
    parts = phone.split("-")
    if len(parts) == 3:
        return f"{parts[0]}-{'*' * len(parts[1])}-{parts[2]}"
    return phone[:3] + "****" + phone[-4:]


def fmt_big(n):
    return f"{n / 1_000_000:.1f}M원" if n >= 1_000_000 else f"{n:,}원"


@bp.route("/my")
@login_required
def index():
    user = g.user
    uid = user["id"]
    page = max(1, request.args.get("page", 1, type=int))
    per_page = current_app.config["PER_PAGE"]
    paid_total = campaign_model.total_paid(uid)
    total = campaign_model.count_payments(uid)
    from ..models import post as post_model
    return render_template(
        "my/index.html", post_counts=post_model.count_by_user(uid), comment_cnt=post_model.count_comments_by_user(uid),
        masked_phone=mask_phone(user["phone"]),
        done_count=campaign_model.count_done(uid),
        paid_total_fmt=fmt_big(paid_total),
        month_paid=campaign_model.month_paid(uid),
        grade_label=GRADE_LABEL.get(user["grade"], "사업자"), my_apply=agency_model.my_apply(uid),
        summary=campaign_model.summary_by_channel(uid), channel_label=CHANNEL_LABEL,
        rows=campaign_model.list_payments(uid, page, per_page), page=page,
        total_pages=max(1, -(-total // per_page)),
        status_label=STATUS_LABEL, status_class=STATUS_CLASS,
    )


@bp.route("/my/biz", methods=["POST"])
@login_required
def biz():
    f = request.form
    name = (f.get("biz_name") or "").strip()[:60]
    no = (f.get("biz_no") or "").strip()
    if no and not BIZ_NO_RE.match(no):
        flash("사업자번호 형식이 올바르지 않습니다. 예) 123-45-67890")
        return redirect(url_for("my.index"))
    if no:
        d = no.replace("-", "")
        no = f"{d[:3]}-{d[3:5]}-{d[5:]}"
    email = (f.get("biz_email") or "").strip()[:120]
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        flash("이메일 주소 형식이 올바르지 않습니다.")
        return redirect(url_for("my.index"))
    user_model.update_biz(g.user["id"], name, no, (f.get("biz_type") or "").strip()[:40],
                          (f.get("biz_item") or "").strip()[:40], email)
    flash("사업자 정보가 저장되었습니다.")
    return redirect(url_for("my.index"))


@bp.route("/my/notify", methods=["POST"])
@login_required
def notify():
    field = request.form.get("field", "")
    value = request.form.get("value") == "1"
    try:
        user_model.update_notify(g.user["id"], field, value)
    except ValueError:
        return jsonify(ok=False), 400
    return jsonify(ok=True, field=field, value=value)


@bp.route("/my/withdraw", methods=["POST"])
@login_required
def withdraw():
    if campaign_model.count_active(g.user["id"]):
        flash("진행 중인 캠페인이 있어 탈퇴할 수 없습니다.")
        return redirect(url_for("my.index"))
    if request.form.get("confirm") != "탈퇴":
        flash("확인 문구가 일치하지 않습니다.")
        return redirect(url_for("my.index"))
    user_model.suspend(g.user["id"])
    session.clear()
    flash("탈퇴 처리되었습니다. 이용해주셔서 감사합니다.")
    return redirect("/")


@bp.route("/my/posts")
@login_required
def posts():
    from ..models import agency as agency_model
    from ..models import post as post_model
    posts = post_model.list_by_user(g.user["id"], 100)
    requests_, _ = agency_model.list_requests(user_id=g.user["id"], page=1, per_page=50)
    return render_template("my/posts.html", posts=posts, requests=requests_, comment_cnt=post_model.count_comments_by_user(g.user["id"]),
                           ag_status=agency_model.STATUS_LABEL, ag_pill=agency_model.STATUS_PILL)


@bp.route("/terms")
def terms():
    from .auth import TERMS
    return render_template("auth/terms.html", title="이용약관", sections=TERMS)


@bp.route("/privacy")
def privacy():
    from .auth import PRIVACY
    return render_template("auth/terms.html", title="개인정보처리방침", sections=PRIVACY)


@bp.route("/guide")
def guide():
    return render_placeholder("이용가이드", 5)


@bp.route("/settings")
def settings():
    return redirect(url_for("my.index"))
