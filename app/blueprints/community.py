"""/community/<board> — info (P1), anon, qna, agency (P4-b) + /notifications."""
import math
import os
import re
import uuid

from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request, session,
                   url_for)

from ..constants import CHANNEL_LABEL
from ..models import agency as agency_model
from ..models import content as content_model
from ..models import post as post_model
from ..models import series_read as series_read_model
from ..services import mask_service, nick_service, notify_service
from .auth import login_required
from .main import render_placeholder  # noqa: F401 (kept for other phases)

bp = Blueprint("community", __name__, url_prefix="/community")

INFO_CATEGORIES = {"guide": "가이드", "data": "데이터", "update": "업데이트"}
READ_CHARS_PER_MIN = 500
SESSION_KEY = "series_reads"
TAG_LABEL = {"place": "플레이스", "store": "스토어", "coupang": "쿠팡", "tool": "도구"}
IMG_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
ANON_TAGS = ["#순위안오름", "#매체추천", "#첫캠페인", "#병원", "#맛집", "#환불", "#키워드"]


def _page():
    return max(1, request.args.get("page", 1, type=int)), current_app.config["PER_PAGE"]


def _rel(dt):
    from datetime import datetime
    s = int((datetime.now() - dt).total_seconds())
    if s < 3600:
        return f"{max(1, s // 60)}분 전"
    if s < 86400:
        return f"{s // 3600}시간 전"
    d = s // 86400
    return "어제" if d == 1 else (f"{d}일 전" if d < 7 else dt.strftime("%m.%d"))


def _save_image(file, folder):
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in IMG_EXT:
        raise ValueError("이미지 파일만 첨부할 수 있습니다.")
    data = file.read()
    if len(data) > 5_000_000:
        raise ValueError("이미지는 5MB 이하여야 합니다.")
    d = os.path.join(current_app.root_path, "static", "uploads", folder)
    os.makedirs(d, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(d, name), "wb") as f:
        f.write(data)
    return f"/static/uploads/{folder}/{name}"


# =============================================================== info (P1) + series reads
def _strip_tags(html):
    return re.sub(r"<[^>]+>", "", html or "")


def _series_with_reads():
    if g.get("user"):
        if session.get(SESSION_KEY):
            series_read_model.merge_session(g.user["id"], session.pop(SESSION_KEY))
        read_ids = series_read_model.read_ids(g.user["id"])
    else:
        read_ids = set(session.get(SESSION_KEY, []))
    rows = content_model.list_series()
    for r in rows:
        r["is_read"] = r["id"] in read_ids
        r["read_min"] = max(1, math.ceil(len(_strip_tags(r["body"])) / READ_CHARS_PER_MIN))
        r.pop("body", None)
    return rows


@bp.route("/info")
def info_index():
    cat = request.args.get("cat") or None
    if cat and cat not in INFO_CATEGORIES:
        cat = None
    q = (request.args.get("q") or "").strip()[:60] or None
    page, per_page = _page()
    items = content_model.list_contents("info", category=cat, page=page, per_page=per_page, q=q)
    for it in items:
        it["preview"] = _strip_tags(it.get("body"))[:180]
    total = content_model.count_contents("info", category=cat, q=q)
    return render_template("community/info_list.html", items=items, page=page, total_pages=max(1, -(-total // per_page)), cat=cat, q=q,
                           categories=INFO_CATEGORIES, series=_series_with_reads())


@bp.route("/info/<int:content_id>")
def info_detail(content_id):
    item = content_model.get_content(content_id, ["info", "series"])
    if not item:
        abort(404)
    content_model.increment_views(content_id)
    if item["board"] == "series":
        if g.get("user"):
            series_read_model.mark(g.user["id"], content_id)
        else:
            reads = session.get(SESSION_KEY, [])
            if content_id not in reads:
                reads.append(content_id); session[SESSION_KEY] = reads
    prev_row, next_row = content_model.get_prev_next(item)
    return render_template("community/info_detail.html", item=item, prev_row=prev_row, next_row=next_row,
                           categories=INFO_CATEGORIES, series=_series_with_reads())


# =============================================================== anon board
def _board_list(slug, template, sorts, default_sort, side):
    sort = request.args.get("sort", default_sort)
    if sort not in sorts:
        sort = default_sort
    tag = request.args.get("tag") or None
    if tag not in TAG_LABEL:
        tag = None
    q = (request.args.get("q") or "").strip()[:60] or None
    page, per_page = _page()
    rows, total = post_model.list_board(slug, sort, tag, q, page, per_page)
    for r in rows:
        r["rel"] = _rel(r["created_at"])
        r["hot"] = r["likes"] >= 10
        r["preview"] = (r.get("body") or "")[:180]
    nick = nick_service.preview(slug) if g.get("user") else None
    return render_template(template, rows=rows, page=page, total_pages=max(1, -(-total // per_page)), sort=sort, tag=tag, q=q,
                           tag_label=TAG_LABEL, nick=nick, **side)


@bp.route("/anon")
def anon():
    hot = post_model.hot_24h("anon", 5)
    return _board_list("anon", "community/anon_list.html", ("new", "hot", "answers"), "new", {"hot": hot, "tags": ANON_TAGS})


@bp.route("/anon/write", methods=["POST"])
@login_required
def anon_write():
    return _write_post("anon", "community.anon", "community.anon_detail")


def _write_post(slug, list_endpoint, detail_endpoint):
    title = " ".join((request.form.get("title") or "").split())[:200]
    body = (request.form.get("body") or "").strip()
    tag = request.form.get("channel_tag") or None
    if tag not in TAG_LABEL:
        tag = None
    if len(title) < 2 or len(body) < 5:
        flash("제목 2자, 본문 5자 이상 입력해주세요.")
        return redirect(url_for(list_endpoint))
    try:
        image_url = _save_image(request.files.get("image"), "posts") if slug == "anon" else None
    except ValueError as e:
        flash(str(e)); return redirect(url_for(list_endpoint))
    title, body = mask_service.mask(title), mask_service.mask(body)
    nick = nick_service.consume(slug)
    pid = post_model.create(slug, g.user["id"], nick, title, body, tag, image_url)
    nick_service.register_post(pid, g.user["id"], nick)
    flash(f"등록되었습니다. 이 글에서 당신은 '{nick}'입니다.")
    return redirect(url_for(detail_endpoint, post_id=pid))


def _detail(slug, template, side):
    post_id = request.view_args["post_id"]
    p = post_model.get(post_id)
    if not p or p["board_slug"] != slug:
        abort(404)
    if p["is_blind"] and not (g.get("user") and (g.user["role"] == "admin" or g.user["id"] == p["user_id"])):
        return render_template("community/blind.html", slug=slug), 404
    post_model.add_view(post_id)
    p["rel"] = _rel(p["created_at"])
    comments = post_model.list_comments(post_id)
    tree, by_id = [], {}
    for c in comments:
        c["rel"] = _rel(c["created_at"]); c["replies"] = []; c["is_author"] = c["user_id"] == p["user_id"]
        c["is_admin"] = c["user_role"] == "admin"
        by_id[c["id"]] = c
        if c["parent_id"] and c["parent_id"] in by_id:
            by_id[c["parent_id"]]["replies"].append(c)
        else:
            tree.append(c)
    my_nick = nick_service.pick(post_id, g.user["id"]) if g.get("user") else None
    return render_template(template, p=p, comments=tree, my_nick=my_nick, tag_label=TAG_LABEL,
                           liked=post_model.liked_by(post_id, g.user["id"] if g.get("user") else None), is_owner=bool(g.get("user")) and g.user["id"] == p["user_id"], **side)


@bp.route("/anon/<int:post_id>")
def anon_detail(post_id):
    return _detail("anon", "community/anon_detail.html", {"hot": post_model.hot_24h("anon", 5), "tags": ANON_TAGS})


@bp.route("/<slug>/<int:post_id>/comment", methods=["POST"])
@login_required
def comment(slug, post_id):
    if slug not in ("anon", "qna"):
        abort(404)
    p = post_model.get(post_id)
    if not p or p["board_slug"] != slug or p["is_blind"]:
        abort(404)
    body = (request.form.get("body") or "").strip()
    if len(body) < 2:
        flash("댓글 내용을 입력해주세요.")
        return redirect(url_for(f"community.{slug}_detail", post_id=post_id))
    parent_id = request.form.get("parent_id", type=int) or None
    if parent_id:
        parent = post_model.get_comment(parent_id)
        if not parent or parent["post_id"] != post_id:
            parent_id = None
        elif parent["parent_id"]:
            parent_id = parent["parent_id"]  # one level of nesting
    nick = nick_service.pick(post_id, g.user["id"])
    cid = post_model.add_comment(post_id, g.user["id"], nick, mask_service.mask(body), parent_id)
    link = url_for(f"community.{slug}_detail", post_id=post_id) + f"#c{cid}"
    if p["user_id"] != g.user["id"]:
        kind = "answer" if slug == "qna" else "comment"
        who = "운영팀" if g.user["role"] == "admin" else nick
        notify_service.push(p["user_id"], kind, f"{who}님이 {'답변' if slug == 'qna' else '댓글'}을 남겼습니다: {p['title'][:40]}", link)
    if parent_id:
        parent = post_model.get_comment(parent_id)
        if parent and parent["user_id"] not in (g.user["id"], p["user_id"]):
            notify_service.push(parent["user_id"], "comment", f"{nick}님이 내 댓글에 답글을 남겼습니다", link)
    return redirect(link)


@bp.route("/<slug>/<int:post_id>/like", methods=["POST"])
@login_required
def like(slug, post_id):
    p = post_model.get(post_id)
    if not p or p["board_slug"] != slug:
        abort(404)
    liked, likes = post_model.toggle_like(post_id, g.user["id"])
    return jsonify(ok=True, liked=liked, likes=likes)


@bp.route("/<slug>/report", methods=["POST"])
@login_required
def report(slug):
    tt = request.form.get("target_type")
    tid = request.form.get("target_id", type=int)
    if tt not in ("post", "comment") or not tid:
        abort(400)
    ok, blinded = post_model.report(tt, tid, g.user["id"], request.form.get("reason") or "기타")
    flash("이미 신고한 글입니다." if not ok else ("신고가 접수되어 블라인드 처리되었습니다." if blinded else "신고가 접수되었습니다."))
    back = request.form.get("back") or url_for(f"community.{slug}")
    return redirect(back if back.startswith("/") else url_for(f"community.{slug}"))


# =============================================================== qna
@bp.route("/qna")
def qna():
    unanswered, _ = post_model.list_board("qna", "unanswered", None, None, 1, 5)
    notices = content_model.dashboard_notices(4)
    return _board_list("qna", "community/qna_list.html", ("new", "unanswered", "admin"), "new", {"unanswered": unanswered, "notices": notices})


@bp.route("/qna/write", methods=["POST"])
@login_required
def qna_write():
    return _write_post("qna", "community.qna", "community.qna_detail")


@bp.route("/qna/<int:post_id>")
def qna_detail(post_id):
    unanswered, _ = post_model.list_board("qna", "unanswered", None, None, 1, 5)
    return _detail("qna", "community/qna_detail.html", {"unanswered": unanswered, "notices": content_model.dashboard_notices(4)})


# =============================================================== agency
def _agency_ctx():
    uid = g.user["id"] if g.get("user") else None
    mine = agency_model.list_requests(user_id=uid, page=1, per_page=5)[0] if uid else []
    my_apply = agency_model.my_apply(uid) if uid else None
    return {"budget_label": agency_model.BUDGET_LABEL, "ag_status": agency_model.STATUS_LABEL, "ag_pill": agency_model.STATUS_PILL,
            "ag_channel": agency_model.CHANNEL_LABEL, "mine": mine, "my_apply": my_apply,
            "can_propose": bool(g.get("user")) and (g.user["role"] == "admin" or g.user["is_agency"])}


@bp.route("/agency")
def agency():
    f = request.args.get("f", "all")
    channel = request.args.get("channel") or None
    if channel not in agency_model.CHANNEL_LABEL:
        channel = None
    status = {"open": "open", "matched": "matched"}.get(f)
    uid = g.user["id"] if (f == "mine" and g.get("user")) else None
    q = (request.args.get("q") or "").strip()[:60] or None
    page, per_page = _page()
    rows, total = agency_model.list_requests(status, channel, uid, page, per_page, q=q)
    for r in rows:
        r["rel"] = _rel(r["created_at"])
    nick = nick_service.preview("agency") if g.get("user") else None
    return render_template("community/agency_list.html", rows=rows, page=page, total_pages=max(1, -(-total // per_page)), f=f, channel=channel,
                           q=q, nick=nick, **_agency_ctx())


@bp.route("/agency/new", methods=["POST"])
@login_required
def agency_new():
    fm = request.form
    channel = fm.get("channel") if fm.get("channel") in agency_model.CHANNEL_LABEL else "place"
    budget = fm.get("budget") if fm.get("budget") in agency_model.BUDGET_LABEL else "tbd"
    industry = (fm.get("industry") or "").strip()[:40]
    region = (fm.get("region") or "").strip()[:40] or None
    body = (fm.get("body") or "").strip()
    contact = (fm.get("contact") or "").strip()[:40] or None
    if not industry or len(body) < 10:
        flash("업종과 요청 내용(10자 이상)을 입력해주세요.")
        return redirect(url_for("community.agency"))
    nick = nick_service.consume("agency")
    rid = agency_model.create_request(g.user["id"], nick, channel, industry, budget, region, mask_service.mask(body), contact)
    flash("의뢰를 등록했습니다. 제안이 오면 알림으로 알려드립니다.")
    return redirect(url_for("community.agency_detail", req_id=rid))


@bp.route("/agency/<int:req_id>")
def agency_detail(req_id):
    r = agency_model.get_request(req_id) or abort(404)
    agency_model.add_view(req_id)
    r["rel"] = _rel(r["created_at"])
    uid = g.user["id"] if g.get("user") else None
    is_owner = uid == r["user_id"]
    is_admin = bool(g.get("user")) and g.user["role"] == "admin"
    proposals = agency_model.list_proposals(req_id) if (is_owner or is_admin) else []
    my_prop = agency_model.my_proposal(req_id, uid) if uid else None
    accepted = next((p for p in agency_model.list_proposals(req_id) if p["status"] == "accepted"), None)
    show_contact = r["contact"] and (is_owner or is_admin or (accepted and accepted["proposer_id"] == uid))
    return render_template("community/agency_detail.html", r=r, proposals=proposals, my_prop=my_prop, is_owner=is_owner, is_admin=is_admin,
                           accepted=accepted, show_contact=show_contact, **_agency_ctx())


@bp.route("/agency/<int:req_id>/propose", methods=["POST"])
@login_required
def agency_propose(req_id):
    r = agency_model.get_request(req_id) or abort(404)
    if not (g.user["role"] == "admin" or g.user["is_agency"]):
        abort(403)
    if r["status"] != "open":
        flash("모집 중인 의뢰에만 제안할 수 있습니다.")
        return redirect(url_for("community.agency_detail", req_id=req_id))
    if agency_model.my_proposal(req_id, g.user["id"]):
        flash("이미 제안을 보냈습니다.")
        return redirect(url_for("community.agency_detail", req_id=req_id))
    budget_plan = (request.form.get("budget_plan") or "").strip()[:2000]
    plan = (request.form.get("plan") or "").strip()[:4000]
    duration = (request.form.get("duration") or "").strip()[:40]
    if len(plan) < 10:
        flash("계획을 10자 이상 적어주세요.")
        return redirect(url_for("community.agency_detail", req_id=req_id))
    agency_model.create_proposal(req_id, g.user["id"], budget_plan, plan, duration)
    notify_service.push(r["user_id"], "proposal", f"의뢰 '{r['industry']} · {r['region'] or ''}'에 새 제안이 도착했습니다", url_for("community.agency_detail", req_id=req_id))
    flash("제안을 보냈습니다. 의뢰자가 수락하면 연락처가 공개됩니다.")
    return redirect(url_for("community.agency_detail", req_id=req_id))


@bp.route("/agency/<int:req_id>/accept/<int:pid>", methods=["POST"])
@login_required
def agency_accept(req_id, pid):
    r = agency_model.get_request(req_id) or abort(404)
    p = agency_model.get_proposal(pid)
    if r["user_id"] != g.user["id"] or not p or p["request_id"] != req_id or r["status"] != "open":
        abort(403)
    agency_model.accept_proposal(req_id, pid)
    notify_service.push(p["proposer_id"], "agency", f"제안이 수락되었습니다 · {r['industry']} {r['region'] or ''}", url_for("community.agency_detail", req_id=req_id))
    flash("제안을 수락했습니다. 수락한 대행사에게 연락처가 공개됩니다.")
    return redirect(url_for("community.agency_detail", req_id=req_id))


@bp.route("/agency/<int:req_id>/close", methods=["POST"])
@login_required
def agency_close(req_id):
    r = agency_model.get_request(req_id) or abort(404)
    if r["user_id"] != g.user["id"] and g.user["role"] != "admin":
        abort(403)
    agency_model.set_status(req_id, "closed")
    flash("의뢰를 마감했습니다.")
    return redirect(url_for("community.agency_detail", req_id=req_id))


@bp.route("/agency/apply", methods=["POST"])
@login_required
def agency_apply():
    back = url_for("my.index") if request.form.get("back") == "/my" else url_for("community.agency")
    if g.user["is_agency"]:
        flash("이미 인증된 대행사입니다."); return redirect(back)
    cur = agency_model.my_apply(g.user["id"])
    if cur and cur["status"] == "pending":
        flash("인증 심사 중입니다."); return redirect(back)
    biz_no = (request.form.get("biz_no") or "").strip()
    if not re.match(r"^\d{3}-?\d{2}-?\d{5}$", biz_no):
        flash("사업자번호 형식이 올바르지 않습니다."); return redirect(back)
    try:
        cert = _save_image(request.files.get("cert"), "agency")
    except ValueError as e:
        flash(str(e)); return redirect(back)
    if not cert:
        flash("사업자등록증 이미지를 첨부해주세요."); return redirect(back)
    agency_model.create_apply(g.user["id"], biz_no, cert)
    flash("인증 신청을 접수했습니다. 운영팀 승인 후 제안을 보낼 수 있습니다.")
    return redirect(back)


# =============================================================== notifications
notif_bp = Blueprint("notifications", __name__)


@notif_bp.route("/notifications")
@login_required
def notifications():
    page, per_page = _page()
    rows, total = notify_service.list_user(g.user["id"], page, per_page)
    notify_service.mark_all_read(g.user["id"])
    for r in rows:
        r["rel"] = _rel(r["created_at"])
    return render_template("community/notifications.html", rows=rows, page=page, total_pages=max(1, -(-total // per_page)))
