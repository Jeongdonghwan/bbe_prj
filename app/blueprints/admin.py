"""/admin/* — operator screens. Every write is recorded in admin_log."""
import csv
import io
import re
import secrets
from datetime import date, datetime, timedelta

from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request, send_file,
                   session, url_for)
from werkzeug.security import generate_password_hash

from ..constants import (CHANNEL_LABEL, MEDIA_SECTIONS, PAY_METHOD_LABEL, PAYMENT_STATUS_LABEL, STATUS_CLASS, STATUS_LABEL,
                         status_tabs)
from ..models import admin_log
from ..models import banner as banner_model
from ..models import campaign as campaign_model
from ..models import content as content_model
from ..models import daily_pick as pick_model
from ..models import media as media_model
from ..models import payment as payment_model
from ..models import popular as popular_model
from ..models import report as report_model
from ..models import settings as settings_model
from ..models import user as user_model
from ..services import campaign_service, content_service, forbidden_service, media_service, payment_service
from .auth import admin_required

bp = Blueprint("admin", __name__, url_prefix="/admin")

PAGES = {
    "": "운영 현황", "orders": "주문 관리", "payments": "결제 내역", "credits": "크레딧 관리", "media": "매체사 관리", "popular": "인기 트래픽 설정",
    "content": "공지 · 정보글", "banners": "배너 관리", "users": "회원 목록", "operators": "운영자 관리", "posts": "게시글 관리", "agency": "대행의뢰 · 제안", "reports": "신고 · 블라인드",
}


def _log(action, target_type=None, target_id=None, summary=None):
    admin_log.log(g.user["id"], action, target_type, target_id, summary)


def _back(default):
    ref = request.form.get("back") or request.referrer
    return redirect(ref if ref and "/admin" in ref else default)


def _csv_json(v):
    """Comma separated admin input -> JSON list column."""
    import json as _json
    items = [x.strip() for x in (v or "").split(",") if x.strip()][:8]
    return _json.dumps(items, ensure_ascii=False) if items else None


def _page():
    return max(1, request.args.get("page", 1, type=int)), current_app.config["PER_PAGE"]


def bank_settings():
    s = settings_model.get_all()
    cfg = current_app.config["BANK_INFO"]
    return {"bank": s.get("bank_name") or cfg["bank"], "account": s.get("bank_account") or cfg["account"],
            "holder": s.get("bank_holder") or cfg["holder"], "due_days": int(s.get("bank_due_days") or 3)}


# =============================================================== dashboard
@bp.route("")
@admin_required
def index():
    counts = campaign_model.admin_status_counts()
    bank = payment_model.pending_bank_summary()
    intake = campaign_model.today_intake()
    queue = campaign_model.review_queue(8)
    for c in queue:
        c["warn"] = forbidden_service.check([c["biz_name"], c["product_name"], c["main_keyword"]], c["channel"])
        ref = c["paid_at"] or c["created_at"]
        c["age_min"] = int((datetime.now() - ref).total_seconds() // 60)
    return render_template(
        "admin/dashboard.html",
        q_review=counts.get("review", 0), oldest=campaign_model.oldest_review_minutes(),
        q_bank=bank["n"], bank_total=int(bank["total"]),
        no_rank=campaign_model.running_without_today_rank(), running=counts.get("running", 0),
        reports=report_model.count_reported(), today_n=intake["n"], today_amount=int(intake["amount"]),
        queue=queue, by_media=campaign_model.today_intake_by_media(5), logs=admin_log.recent(10),
        channel_label=CHANNEL_LABEL,
    )


# =============================================================== orders
@bp.route("/orders")
@admin_required
def orders():
    status = request.args.get("status") or None
    if status not in STATUS_LABEL:
        status = None
    channel = request.args.get("channel") or None
    if channel not in CHANNEL_LABEL:
        channel = None
    media_id = request.args.get("media", type=int)
    period = request.args.get("period") or None
    q = (request.args.get("q") or "").strip()[:60] or None
    flt = _export_filters()
    page, per_page = _page()
    rows = campaign_model.admin_list(status, channel, media_id, period, q, page, per_page, **flt)
    for r in rows:
        r["warn"] = forbidden_service.check([r["biz_name"], r["product_name"], r["main_keyword"], *(r["setting_keywords"] or [])], r["channel"])
        r["day_idx"] = campaign_service.day_index(r)
        r["total_days"] = campaign_service.days_between(r["start_date"], r["end_date"])
        r["today"] = campaign_model.today_rank(r["id"]) if r["status"] == "running" else None
    total = campaign_model.admin_count(status, channel, media_id, period, q, **flt)
    counts = campaign_model.admin_status_counts()
    medias = (media_model.list_by_channel(channel, False) if channel else
              media_model.list_by_channel("place", False) + media_model.list_by_channel("store", False) + media_model.list_by_channel("coupang", False))
    return render_template(
        "admin/orders.html", rows=rows, page=page, total_pages=max(1, -(-total // per_page)), counts=counts,
        total_all=sum(counts.values()), status=status, channel=channel, media_id=media_id, period=period, q=q, medias=medias,
        status_order=status_tabs(counts), status_label=STATUS_LABEL, status_class=STATUS_CLASS, channel_label=CHANNEL_LABEL,
        pay_method_label=PAY_METHOD_LABEL, accounts=campaign_model.accounts_with_campaigns(),
        user_id=flt.get("user_id"), date_from=flt.get("date_from"), date_to=flt.get("date_to"),
    )


def _export_filters():
    """계정·등록일 범위 — 목록과 엑셀이 같은 필터를 쓴다."""
    def _d(v):
        try:
            return date.fromisoformat(v) if v else None
        except ValueError:
            return None
    src = request.values
    return {"user_id": src.get("user", type=int) or None,
            "date_from": _d(src.get("from")), "date_to": _d(src.get("to"))}


def _apply_action(c, action, reason=""):
    """Shared by single/bulk actions. Returns (ok, message)."""
    try:
        if action == "approve":
            # 승인 = 곧장 정상(running). 구동은 시작일부터 돌고, 그 날짜는 목록에 그대로 보인다.
            c = campaign_service.transition(c, "running", g.user["id"], f"운영팀 승인 · {c['start_date']:%m.%d} 시작")
            _log("order_approve", "campaign", c["id"], f"{c['order_no']} 승인 → 정상")
        elif action == "reject":
            if not reason.strip():
                return False, "반려 사유는 필수입니다."
            c = campaign_service.reject(c, g.user["id"], reason.strip())
            _log("order_reject", "campaign", c["id"], f"{c['order_no']} 반려 — {reason.strip()} · {c['refund_amount']:,}원 환불")
        elif action == "start":
            c = campaign_service.transition(c, "running", g.user["id"], "구동 시작")
            _log("order_start", "campaign", c["id"], f"{c['order_no']} 구동 시작")
        elif action == "stop":
            c = campaign_service.stop(c, g.user["id"], "운영팀 중단")
            _log("order_stop", "campaign", c["id"], f"{c['order_no']} 중단 · {c['refund_amount']:,}원 환불")
        elif action == "delete":
            return False, "삭제는 행마다 확인이 필요합니다."
        elif action == "done":
            c = campaign_service.transition(c, "done", g.user["id"], f"구동 완료 · 누적 {campaign_model.total_done_qty(c['id']):,}건")
            _log("order_done", "campaign", c["id"], f"{c['order_no']} 완료")
        elif action == "paid":
            c = payment_service.confirm_bank(c, g.user["id"])
            _log("payment_confirm", "campaign", c["id"], f"{c['order_no']} 입금 확인 · {c['paid_amount']:,}원")
        else:
            return False, "알 수 없는 작업"
        return True, f"{c['order_no']} → {STATUS_LABEL[c['status']]}"
    except (campaign_service.CampaignError, payment_service.PaymentError) as e:
        return False, f"{c['order_no']}: {e}"


@bp.route("/orders/<int:campaign_id>/action", methods=["POST"])
@admin_required
def order_action(campaign_id):
    c = campaign_model.get(campaign_id) or abort(404)
    action = request.form.get("action", "")
    if action == "memo":
        campaign_model.set_admin_memo(c["id"], (request.form.get("memo") or "").strip()[:1000])
        _log("order_memo", "campaign", c["id"], f"{c['order_no']} 메모 수정")
        flash("메모를 저장했습니다.")
    elif action == "status":
        target = request.form.get("status")
        mapping = {"approved": "approve", "rejected": "reject", "running": "start", "stopped": "stop", "done": "done", "review": "paid"}
        ok, msg = _apply_action(c, mapping.get(target, ""), request.form.get("reason", ""))
        flash(msg)
    else:
        ok, msg = _apply_action(c, action, request.form.get("reason", ""))
        flash(msg)
    return _back(url_for("admin.orders"))


@bp.route("/orders/<int:campaign_id>/rank", methods=["POST"])
@admin_required
def order_rank(campaign_id):
    c = campaign_model.get(campaign_id) or abort(404)
    try:
        day = date.fromisoformat(request.form.get("date") or date.today().isoformat())
        rank = int(request.form.get("rank"))
        done_qty = int(request.form.get("done_qty") or c["daily_qty"])
        c = campaign_service.record_rank(c, day, rank, done_qty, g.user["id"])
        _log("order_rank", "campaign", c["id"], f"{c['order_no']} 순위 입력 {day:%m.%d} {c['rank_start']}→{rank} · {done_qty}건")
        flash(f"{c['order_no']} 순위 저장: {rank}위")
    except (ValueError, TypeError):
        flash("순위/수량을 숫자로 입력해주세요.")
    except campaign_service.CampaignError as e:
        flash(str(e))
    return _back(url_for("admin.orders"))


@bp.route("/orders/<int:campaign_id>/delete", methods=["POST"])
@admin_required
def order_delete(campaign_id):
    """주문 완전 삭제. 아직 안 돌려준 크레딧이 있으면 먼저 환불하고 지운다."""
    from ..services import credit_service
    c = campaign_model.get(campaign_id) or abort(404)
    outstanding = (c["paid_amount"] or 0) - (c["refund_amount"] or 0)
    refunded = 0
    # 구동이 끝난 건(done/stopped)은 이미 정산된 매출이라 돌려주지 않는다.
    if c["status"] in ("review", "approved", "running") and c["pay_method"] == "credit" and outstanding > 0:
        credit_service.refund(c["user_id"], outstanding, campaign_id, f"주문 삭제 · {c['order_no']}")
        refunded = outstanding
    campaign_model.purge(campaign_id)
    _log("order_delete", "campaign", campaign_id,
         f"{c['order_no']} 삭제 ({STATUS_LABEL.get(c['status'], c['status'])})"
         + (f" · {refunded:,}원 환불" if refunded else ""))
    flash(f"{c['order_no']} 주문을 삭제했습니다." + (f" 잔여 {refunded:,}원을 환불했습니다." if refunded else ""))
    return _back(url_for("admin.orders"))


@bp.route("/orders/bulk", methods=["POST"])
@admin_required
def orders_bulk():
    ids = [int(i) for i in request.form.getlist("ids") if i.isdigit()]
    action = request.form.get("action")
    reason = request.form.get("reason", "")
    ok_n, msgs = 0, []
    for cid in ids:
        c = campaign_model.get(cid)
        if not c:
            continue
        ok, msg = _apply_action(c, action, reason)
        ok_n += ok
        if not ok:
            msgs.append(msg)
    flash(f"{ok_n}건 처리" + (" · 실패: " + "; ".join(msgs) if msgs else ""))
    return _back(url_for("admin.orders"))


@bp.route("/orders/export", methods=["GET", "POST"])
@admin_required
def orders_export():
    """엑셀 3시트(캠페인 / 일별 로그 / 주별 정산). GET 은 목록 필터 그대로, POST 는 체크한 캠페인만."""
    from ..models import credit as credit_model
    from ..services import export_service
    src = request.values
    status = src.get("status") if src.get("status") in STATUS_LABEL else None
    channel = src.get("channel") if src.get("channel") in CHANNEL_LABEL else None
    ids = [int(i) for i in request.form.getlist("ids") if str(i).isdigit()] if request.method == "POST" else None
    flt = _export_filters()
    rows = campaign_model.admin_all(status, channel, src.get("media", type=int), src.get("period") or None,
                                    (src.get("q") or "").strip()[:60] or None, ids=ids, **flt)
    # 일별·주별 시트의 활동 기간: 지정 없으면 최근 31일
    today = date.today()
    d_to = flt["date_to"] or today
    d_from = flt["date_from"] or (d_to - timedelta(days=30))
    cids = [r["id"] for r in rows]
    buf = export_service.build_workbook(rows, campaign_model.daily_records(cids, d_from, d_to),
                                        credit_model.campaign_refunds(cids), d_from, d_to, today)
    scope = f"선택 {len(ids)}건" if ids else (f"계정 {flt['user_id']}" if flt["user_id"] else "전체")
    _log("order_export", None, None, f"엑셀 내보내기 {len(rows)}건 · {scope} · {d_from:%m.%d}~{d_to:%m.%d}")
    return send_file(buf, as_attachment=True, download_name=f"campaigns_{today:%Y%m%d}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@bp.route("/orders/rank-upload", methods=["POST"])
@admin_required
def orders_rank_upload():
    f = request.files.get("file")
    if not f:
        flash("CSV 파일을 선택해주세요.")
        return redirect(url_for("admin.orders"))
    text = f.read().decode("utf-8-sig", errors="replace")
    ok_n, errs = 0, []
    for i, row in enumerate(csv.reader(io.StringIO(text)), 1):
        if not row or row[0].strip().lower() in ("order_no", ""):
            continue
        try:
            order_no, d, rank, done = [x.strip() for x in row[:4]]
            c = campaign_model.get_by_order_no(order_no)
            if not c:
                errs.append(f"{i}행 주문 없음"); continue
            campaign_service.record_rank(c, date.fromisoformat(d), int(rank), int(done), g.user["id"])
            ok_n += 1
        except (ValueError, IndexError, campaign_service.CampaignError) as e:
            errs.append(f"{i}행 {e}")
    _log("order_rank_upload", None, None, f"순위 CSV 업로드 {ok_n}건" + (f", 오류 {len(errs)}" if errs else ""))
    flash(f"순위 {ok_n}건 반영" + (" · 오류: " + "; ".join(errs[:5]) if errs else ""))
    return redirect(url_for("admin.orders"))


# =============================================================== payments (bank confirm)
@bp.route("/payments")
@admin_required
def payments():
    tab = request.args.get("tab", "pending")
    page, per_page = _page()
    if tab == "pending":
        rows, total = payment_model.list_admin("pending", "bank", page, per_page)
    elif tab == "paid":
        rows, total = payment_model.list_admin("paid", "bank", page, per_page)
    elif tab == "expired":
        rows, total = payment_model.list_admin("expired", "bank", page, per_page)
    else:
        tab = "card"; rows, total = payment_model.list_admin(None, "card", page, per_page)
    now = datetime.now()
    for r in rows:
        r["overdue"] = bool(r["bank_due_at"] and r["status"] == "pending" and r["bank_due_at"] < now)
        r["age_h"] = int((now - r["created_at"]).total_seconds() // 3600)
    pend = payment_model.pending_bank_summary()
    return render_template("admin/payments.html", rows=rows, tab=tab, page=page, total_pages=max(1, -(-total // per_page)),
                           pending_n=pend["n"], pending_total=int(pend["total"]), bank=bank_settings(),
                           pay_status_label=PAYMENT_STATUS_LABEL, status_label=STATUS_LABEL, status_class=STATUS_CLASS, channel_label=CHANNEL_LABEL)


@bp.route("/payments/<int:payment_id>/confirm", methods=["POST"])
@admin_required
def payment_confirm(payment_id):
    p = payment_model.get(payment_id) or abort(404)
    c = campaign_model.get(p["campaign_id"])
    ok, msg = _apply_action(c, "paid")
    flash(msg)
    return redirect(url_for("admin.payments"))


@bp.route("/payments/<int:payment_id>/cancel", methods=["POST"])
@admin_required
def payment_cancel(payment_id):
    p = payment_model.get(payment_id) or abort(404)
    c = campaign_model.get(p["campaign_id"])
    try:
        campaign_service.cancel(c, g.user["id"], "운영팀 취소 · " + (request.form.get("reason") or "미입금"))
        _log("payment_cancel", "campaign", c["id"], f"{c['order_no']} 무통장 취소")
        flash(f"{c['order_no']} 취소")
    except campaign_service.CampaignError as e:
        flash(str(e))
    return redirect(url_for("admin.payments"))


@bp.route("/payments/expire", methods=["POST"])
@admin_required
def payments_expire():
    n = payment_service.expire_unpaid(g.user["id"])
    _log("payment_expire", None, None, f"기한 만료 처리 {n}건")
    flash(f"기한 만료 {n}건 처리")
    return redirect(url_for("admin.payments", tab="expired"))


@bp.route("/payments/settings", methods=["POST"])
@admin_required
def payments_settings():
    items = {"bank_name": request.form.get("bank_name", "").strip()[:30], "bank_account": request.form.get("bank_account", "").strip()[:40],
             "bank_holder": request.form.get("bank_holder", "").strip()[:30],
             "bank_due_days": str(max(1, min(10, request.form.get("bank_due_days", 3, type=int))))}
    settings_model.set_many(items)
    _log("settings_bank", None, None, f"입금 계좌 설정 변경 {items['bank_name']} {items['bank_account']}")
    flash("입금 계좌 설정을 저장했습니다.")
    return redirect(url_for("admin.payments"))


@bp.route("/media/weekly", methods=["POST"])
@admin_required
def media_weekly():
    """이번 주 운영팀 추천 1~3위. 인기 트래픽 페이지의 TOP3 와 메인 위젯 메달이 이 값을 쓴다."""
    from ..models import weekly_rank
    channel = request.form.get("channel") if request.form.get("channel") in CHANNEL_LABEL else "place"
    try:
        week = date.fromisoformat(request.form.get("week", ""))
    except ValueError:
        week = weekly_rank.week_start()
    week = weekly_rank.week_start(week)          # 어떤 날짜를 줘도 그 주 월요일로
    ranks, seen = {}, set()
    for r in (1, 2, 3):
        tid = request.form.get(f"rank{r}", type=int)
        if not tid or tid in seen:
            continue                              # 빈 칸과 중복은 건너뛴다
        m = media_model.get(tid)
        if m and m["channel"] == channel:
            ranks[r] = tid
            seen.add(tid)
    weekly_rank.save(channel, ranks, week)
    _log("media_weekly", "media", None, f"{CHANNEL_LABEL[channel]} {week:%m.%d} 주간 추천 {len(ranks)}개")
    flash(f"{week:%Y.%m.%d} 주 추천 순위를 저장했습니다." if ranks else "주간 추천 순위를 비웠습니다.")
    return redirect(url_for("admin.media", channel=channel, week=week.isoformat()))


@bp.route("/media/picks", methods=["POST"])
@admin_required
def media_picks():
    """오늘의 인기 — types shown in the wizard's highlight band for this channel today."""
    channel = request.form.get("channel") if request.form.get("channel") in CHANNEL_LABEL else "place"
    ids = [int(i) for i in request.form.getlist("type_ids") if str(i).isdigit()][:6]
    pick_model.save(channel, date.today(), ids)
    _log("media_picks", "media", None, f"{CHANNEL_LABEL[channel]} 오늘의 인기 {len(ids)}개")
    flash("오늘의 인기를 저장했습니다.")
    return redirect(url_for("admin.media", channel=channel))


# =============================================================== credits
@bp.route("/credits")
@admin_required
def credits():
    from ..models import credit as credit_model
    status = request.args.get("status") if request.args.get("status") in ("pending", "approved", "rejected") else None
    page, per_page = _page()
    rows, total = credit_model.list_admin_requests(status, page, per_page)
    return render_template("admin/credits.html", rows=rows, status=status, page=page,
                           total_pages=max(1, -(-total // per_page)),
                           pending_n=credit_model.pending_count(),
                           users=user_model.list_brief(), recent=credit_model.ledger_recent(20))


@bp.route("/credits/<int:req_id>/approve", methods=["POST"])
@admin_required
def credits_approve(req_id):
    from ..models import credit as credit_model
    from ..services import credit_service
    try:
        credit_service.approve_request(req_id, g.user["id"])
    except credit_service.CreditError as e:
        flash(str(e))
        return redirect(url_for("admin.credits"))
    r = credit_model.get_request(req_id)
    _log("credit_approve", "charge_request", req_id, f"충전 승인 · #{req_id} {r['amount']:,}원 (입금 {r['total']:,}원)")
    flash("충전을 승인했습니다.")
    return redirect(url_for("admin.credits"))


@bp.route("/credits/<int:req_id>/reject", methods=["POST"])
@admin_required
def credits_reject(req_id):
    from ..services import credit_service
    reason = (request.form.get("reason") or "").strip()[:200] or "사유 미기재"
    try:
        credit_service.reject_request(req_id, g.user["id"], reason)
    except credit_service.CreditError as e:
        flash(str(e))
        return redirect(url_for("admin.credits"))
    _log("credit_reject", "charge_request", req_id, f"충전 거절 · #{req_id} · {reason}")
    flash("충전 요청을 거절했습니다.")
    return redirect(url_for("admin.credits"))


@bp.route("/credits/adjust", methods=["POST"])
@admin_required
def credits_adjust():
    from ..services import credit_service
    user_id = request.form.get("user_id", type=int)
    amount = (request.form.get("amount", type=int) or 0) * (request.form.get("sign", type=int) or 1)
    memo = (request.form.get("memo") or "").strip()
    target = user_model.get_by_id(user_id) if user_id else None
    if not target:
        flash("회원을 선택해주세요.")
        return redirect(url_for("admin.credits"))
    try:
        bal = credit_service.adjust(user_id, amount, g.user["id"], memo)
    except credit_service.CreditError as e:
        flash(str(e))
        return redirect(url_for("admin.credits"))
    _log("credit_adjust", "user", user_id, f"{target['nickname']} 크레딧 {'충전' if amount > 0 else '차감'} {abs(amount):,}원 → 잔액 {bal:,}원")
    flash(f"{target['nickname']}님 크레딧을 {'충전' if amount > 0 else '차감'}했습니다. (잔액 {bal:,}원)")
    return redirect(url_for("admin.credits"))


# =============================================================== media
@bp.route("/media")
@admin_required
def media():
    channel = request.args.get("channel", "place")
    if channel not in CHANNEL_LABEL:
        channel = "place"
    rows = media_model.list_by_channel(channel, False)
    month = media_model.month_intake_counts()
    for m in rows:
        m["eff"] = media_model.efficiency(m)
        m["auto"] = media_service.calc_efficiency(m["id"])
        m["month"] = month.get(m["id"], 0)
    counts = {ch: len(media_model.list_by_channel(ch, False)) for ch in CHANNEL_LABEL}
    edit_id = request.args.get("edit", type=int)
    edit = media_model.get(edit_id) if edit_id else None
    if edit:
        edit["auto"] = media_service.calc_efficiency(edit["id"])
    new = request.args.get("new") == "1"
    return render_template("admin/media.html", channel=channel, rows=rows, counts=counts, edit=edit, new=new,
                           sections=MEDIA_SECTIONS.get(channel, []),
                           today=date.today(), picks=pick_model.get(channel, date.today()),
                           channel_label=CHANNEL_LABEL, **_weekly_ctx(channel))


def _weekly_ctx(channel):
    """주간 추천 편집 상자에 필요한 값. ?week= 로 지난 주도 손볼 수 있다."""
    from ..models import weekly_rank
    try:
        week = weekly_rank.week_start(date.fromisoformat(request.args.get("week", "")))
    except ValueError:
        week = weekly_rank.week_start()
    cur = {r: t for t, r in weekly_rank.by_type(channel, week).items()}
    return {"week": week, "week_label": weekly_rank.week_label(week), "weekly": cur,
            "this_week": weekly_rank.week_start(), "weekly_empty_now": not weekly_rank.by_type(channel, weekly_rank.week_start())}


@bp.route("/media/save", methods=["POST"])
@admin_required
def media_save():
    f = request.form
    mid = f.get("id", type=int)
    channel = f.get("channel") if f.get("channel") in CHANNEL_LABEL else "place"
    try:
        fields = {
            "channel": channel, "name": f.get("name", "").strip()[:40],
            "group_name": f.get("group_name") if f.get("group_name") in MEDIA_SECTIONS.get(channel, []) else (MEDIA_SECTIONS.get(channel) or ["기성"])[0],
            "tagline": f.get("tagline", "").strip()[:80] or None, "color": f.get("color", "#4B5563")[:7],
            "unit_price": int(f.get("unit_price")), "list_price": int(f["list_price"]) if f.get("list_price", "").strip() else None,
            "min_days": int(f.get("min_days", 3)), "min_daily": int(f.get("min_daily", 50)), "max_daily": int(f.get("max_daily", 500)),
            "cutoff_time": (f.get("cutoff_time") or "13:30")[:5] + ":00",
            "efficiency_manual": int(f["efficiency_manual"]) if f.get("efficiency_manual", "").strip() else None,
            "badge": f.get("badge") if f.get("badge") in ("hot", "best", "new", "pick") else None,
            "badge_until": f.get("badge_until") or None,
            "fit_for": _csv_json(f.get("fit_for")),
            "flow_steps": _csv_json(f.get("flow_steps")),
            "eff_level": f.get("eff_level") if f.get("eff_level") in ("normal", "good", "best") else "good",
            "eff_note": f.get("eff_note", "").strip()[:120] or None,
            "description": f.get("description", "").strip() or None,
            "op_note": f.get("op_note", "").strip()[:200] or None,
            "no_refund_days": int(f["no_refund_days"]) if f.get("no_refund_days", "").strip() else None,
            "rank_lead_days": f.get("rank_lead_days", "").strip()[:20] or None,
            "is_active": 1 if f.get("is_active") == "1" else 0, "same_day": 1 if f.get("same_day") == "1" else 0,
            "sort": int(f.get("sort") or 0),
        }
        if not fields["name"]:
            raise ValueError("이름을 입력해주세요.")
        if fields["max_daily"] and fields["min_daily"] > fields["max_daily"]:
            raise ValueError("일 수량 범위가 올바르지 않습니다.")
    except (ValueError, TypeError) as e:
        flash(f"입력값을 확인해주세요: {e}")
        return redirect(url_for("admin.media", channel=channel, edit=mid))
    if mid:
        media_model.update_fields(mid, fields)
        _log("media_update", "media", mid, f"{fields['name']} 수정 · 단가 {fields['unit_price']:,}")
    else:
        mid = media_model.insert(fields)
        _log("media_create", "media", mid, f"{fields['name']} 추가")
    flash(f"{fields['name']} 저장")
    return redirect(url_for("admin.media", channel=channel, edit=mid))


@bp.route("/media/<int:media_id>/toggle", methods=["POST"])
@admin_required
def media_toggle(media_id):
    m = media_model.get(media_id) or abort(404)
    media_model.update_fields(media_id, {"is_active": 0 if m["is_active"] else 1})
    _log("media_toggle", "media", media_id, f"{m['name']} 노출 {'OFF' if m['is_active'] else 'ON'}")
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=True, is_active=0 if m["is_active"] else 1)
    return redirect(url_for("admin.media", channel=m["channel"]))


@bp.route("/media/<int:media_id>/delete", methods=["POST"])
@admin_required
def media_delete(media_id):
    m = media_model.get(media_id) or abort(404)
    used = media_model.usage_count(media_id)
    if used:
        flash(f"'{m['name']}'는 캠페인 {used}건이 연결되어 삭제할 수 없습니다. 노출 OFF로 숨겨주세요.")
        return redirect(url_for("admin.media", channel=m["channel"], edit=media_id))
    media_service.delete_logo(media_id)
    media_model.delete(media_id)
    _log("media_delete", "media", media_id, f"{m['name']} 삭제 ({m['channel']})")
    flash(f"'{m['name']}' 매체사를 삭제했습니다.")
    return redirect(url_for("admin.media", channel=m["channel"]))


@bp.route("/popular")
@admin_required
def popular():
    channel = request.args.get("channel", "place")
    if channel not in CHANNEL_LABEL:
        channel = "place"
    cats = popular_model.list_categories(channel)
    summary = popular_model.sets_summary(channel)
    metas = popular_model.meta_map(channel)
    edit_id = request.args.get("edit", type=int)
    edit = None
    if edit_id:
        cat = popular_model.get_category(edit_id)
        if cat and cat["channel"] == channel:
            sets = {s["rank"]: s for s in popular_model.sets_for(edit_id)}
            edit = {"cat": cat, "sets": sets, "excludes": popular_model.excludes_for(edit_id), "meta": metas.get(edit_id)}
    medias = media_model.list_by_channel(channel, False)
    for m in medias:
        m["eff"] = media_model.efficiency(m)
    return render_template("admin/popular.html", channel=channel, cats=cats, summary=summary, metas=metas, edit=edit, medias=medias,
                           channel_label=CHANNEL_LABEL)


@bp.route("/popular/category", methods=["POST"])
@admin_required
def popular_category_create():
    channel = request.form.get("channel") if request.form.get("channel") in CHANNEL_LABEL else "place"
    name = (request.form.get("name") or "").strip()[:40]
    if not name:
        flash("카테고리명을 입력해주세요.")
        return redirect(url_for("admin.popular", channel=channel))
    cid = popular_model.create_category(channel, name)
    _log("popular_cat_create", "popular_category", cid, f"{CHANNEL_LABEL[channel]} 카테고리 추가 · {name}")
    return redirect(url_for("admin.popular", channel=channel, edit=cid))


@bp.route("/popular/<int:cat_id>/save", methods=["POST"])
@admin_required
def popular_save(cat_id):
    cat = popular_model.get_category(cat_id) or abort(404)
    f = request.form
    ranks, notes = {}, {}
    for r in (1, 2, 3):
        mid = f.get(f"media_{r}", type=int)
        ranks[r] = mid or None
        notes[r] = (f.get(f"note_{r}") or "").strip()
    chosen = [m for m in ranks.values() if m]
    if len(chosen) != len(set(chosen)):
        flash("같은 매체를 두 순위에 넣을 수 없습니다.")
        return redirect(url_for("admin.popular", channel=cat["channel"], edit=cat_id))
    excludes = {int(x) for x in f.getlist("exclude") if x.isdigit()}
    popular_model.save_sets(cat_id, ranks, notes, excludes, f.get("show_weekly") == "1", g.user["id"])
    popular_model.update_category(cat_id, name=(f.get("name") or cat["name"]).strip()[:40], is_active=f.get("is_active") == "1",
                                  sort=f.get("sort", type=int))
    _log("popular_save", "popular_category", cat_id, f"{cat['name']} 순위 저장 · " + ", ".join(str(m) for m in chosen))
    flash(f"{cat['name']} 저장 — 사용자 화면에 반영됨")
    return redirect(url_for("admin.popular", channel=cat["channel"], edit=cat_id))


@bp.route("/popular/<int:cat_id>/toggle", methods=["POST"])
@admin_required
def popular_toggle(cat_id):
    cat = popular_model.get_category(cat_id) or abort(404)
    popular_model.update_category(cat_id, is_active=not cat["is_active"])
    _log("popular_toggle", "popular_category", cat_id, f"{cat['name']} 노출 {'OFF' if cat['is_active'] else 'ON'}")
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=True, is_active=0 if cat["is_active"] else 1)
    return redirect(url_for("admin.popular", channel=cat["channel"]))


@bp.route("/popular/<int:cat_id>/delete", methods=["POST"])
@admin_required
def popular_delete(cat_id):
    cat = popular_model.get_category(cat_id) or abort(404)
    popular_model.delete_category(cat_id)
    _log("popular_cat_delete", "popular_category", cat_id, f"{cat['name']} 삭제")
    return redirect(url_for("admin.popular", channel=cat["channel"]))


# =============================================================== content
@bp.route("/content")
@admin_required
def content():
    tab = request.args.get("tab", "all")
    if tab not in ("all", "notice", "info", "series", "draft"):
        tab = "all"
    page, per_page = _page()
    rows, total = content_model.admin_list(tab, page, per_page)
    counts = content_model.admin_counts()
    edit_id = request.args.get("edit", type=int)
    edit = content_model.get_any(edit_id) if edit_id else None
    new = request.args.get("new") == "1"
    return render_template("admin/content.html", rows=rows, tab=tab, page=page, total_pages=max(1, -(-total // per_page)), counts=counts,
                           edit=edit, new=new or edit is not None, notice_categories=content_service.NOTICE_CATEGORIES,
                           info_categories=content_service.INFO_CATEGORIES, channel_label=CHANNEL_LABEL,
                           next_series_no=content_model.next_series_no())


@bp.route("/content/save", methods=["POST"])
@admin_required
def content_save():
    f = request.form
    cid = f.get("id", type=int)
    board = f.get("board") if f.get("board") in ("notice", "info", "series") else "info"
    title = (f.get("title") or "").strip()[:200]
    if not title:
        flash("제목을 입력해주세요.")
        return redirect(url_for("admin.content", edit=cid, new=1))
    mode = f.get("mode", "publish")  # publish | draft
    publish_at = None
    status = "draft" if mode == "draft" else "published"
    if mode == "publish" and f.get("when") == "schedule" and f.get("publish_at"):
        try:
            publish_at = datetime.fromisoformat(f["publish_at"])
            status = "scheduled" if publish_at > datetime.now() else "published"
        except ValueError:
            flash("예약 일시 형식이 올바르지 않습니다.")
            return redirect(url_for("admin.content", edit=cid, new=1))
    if status == "published" and publish_at is None:
        publish_at = datetime.now()
    category = f.get("category") or None
    if board == "notice" and category not in content_service.NOTICE_CATEGORIES:
        category = "update"
    if board == "info" and category not in content_service.INFO_CATEGORIES:
        category = "guide"
    fields = {
        "board": board, "category": "series" if board == "series" else category,
        "channel": f.get("channel") if f.get("channel") in CHANNEL_LABEL else None,
        "series_no": f.get("series_no", type=int) if board == "series" else None,
        "title": title, "body": content_service.sanitize(f.get("body")), "status": status, "publish_at": publish_at,
        "is_pinned": 1 if f.get("is_pinned") == "1" else 0, "show_dashboard": 1 if f.get("show_dashboard") == "1" else 0,
        "notify": 1 if (board == "notice" and f.get("notify") == "1") else 0, "author_id": g.user["id"],
    }
    if board == "series" and not fields["series_no"]:
        fields["series_no"] = content_model.next_series_no()
    cid = content_model.save(cid, fields)
    _log("content_save", "content", cid, f"[{board}] {title} · {status}")
    flash({"draft": "임시저장했습니다.", "scheduled": "예약 발행 등록", "published": "발행했습니다."}[status])
    return redirect(url_for("admin.content", edit=cid))


@bp.route("/content/<int:content_id>/pin", methods=["POST"])
@admin_required
def content_pin(content_id):
    c = content_model.get_any(content_id) or abort(404)
    content_model.save(content_id, {"is_pinned": 0 if c["is_pinned"] else 1})
    _log("content_pin", "content", content_id, f"{c['title']} 고정 {'해제' if c['is_pinned'] else '설정'}")
    return _back(url_for("admin.content"))


@bp.route("/content/<int:content_id>/order/<direction>", methods=["POST"])
@admin_required
def content_order(content_id, direction):
    content_model.swap_series_order(content_id, "up" if direction == "up" else "down")
    _log("content_order", "content", content_id, f"시리즈 순서 {direction}")
    return redirect(url_for("admin.content", tab="series"))


@bp.route("/content/<int:content_id>/delete", methods=["POST"])
@admin_required
def content_delete(content_id):
    c = content_model.get_any(content_id) or abort(404)
    content_model.delete(content_id)
    _log("content_delete", "content", content_id, f"{c['title']} 삭제")
    flash("삭제했습니다.")
    return redirect(url_for("admin.content"))


@bp.route("/content/bulk-delete", methods=["POST"])
@admin_required
def content_bulk_delete():
    ids = [int(i) for i in request.form.getlist("ids") if str(i).isdigit()]
    n = 0
    for cid in ids:
        if content_model.get_any(cid):
            content_model.delete(cid)
            n += 1
    if n:
        _log("content_bulk_delete", "content", None, f"글 {n}건 일괄 삭제")
    flash(f"{n}건을 삭제했습니다." if n else "선택된 글이 없습니다.")
    return _back(url_for("admin.content"))


@bp.route("/content/upload", methods=["POST"])
@admin_required
def content_upload():
    try:
        url = content_service.save_image(request.files.get("image"))
    except content_service.ContentError as e:
        return jsonify(ok=False, error=str(e)), 400
    return jsonify(ok=True, url=url)


# =============================================================== banners
@bp.route("/banners/strip", methods=["POST"])
@admin_required
def banners_strip():
    from ..models import settings as settings_model
    f = request.form
    bg = f.get("strip_bg") or "#2563EB"
    if not re.match(r"^#[0-9A-Fa-f]{6}$", bg):
        bg = "#2563EB"
    settings_model.set_many({
        "strip_text": (f.get("strip_text") or "").strip()[:120],
        "strip_link": (f.get("strip_link") or "").strip()[:300],
        "strip_bg": bg,
        "strip_on": "1" if f.get("strip_on") == "1" else "0",
    })
    _log("strip_save", "settings", 0, "띠배너 설정 저장")
    flash("띠배너 설정을 저장했습니다.")
    return redirect(url_for("admin.banners"))


@bp.route("/banners")
@admin_required
def banners():
    rows = banner_model.list_all()
    edit_id = request.args.get("edit", type=int)
    edit = banner_model.get(edit_id) if edit_id else None
    from ..models import settings as settings_model
    s = settings_model.get_all()
    return render_template("admin/banners.html", rows=rows, edit=edit, new=request.args.get("new") == "1",
                           strip={"text": s.get("strip_text") or "", "link": s.get("strip_link") or "",
                                  "bg": s.get("strip_bg") or "#2563EB", "on": s.get("strip_on") == "1"})


BANNER_IMG_EXT = {"png", "jpg", "jpeg", "gif", "webp"}


def _save_banner_image(banner_id, file):
    import os as _os
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in BANNER_IMG_EXT:
        raise ValueError("PNG/JPG/GIF/WEBP 이미지만 업로드할 수 있습니다.")
    data = file.read()
    if len(data) > 5_000_000:
        raise ValueError("이미지는 5MB 이하여야 합니다.")
    d = _os.path.join(current_app.root_path, "static", "uploads", "banners")
    _os.makedirs(d, exist_ok=True)
    for old in _os.listdir(d):
        if old.startswith(f"{banner_id}."):
            _os.remove(_os.path.join(d, old))
    import uuid as _uuid
    name = f"{banner_id}.{ext}"
    with open(_os.path.join(d, name), "wb") as fh:
        fh.write(data)
    return f"/static/uploads/banners/{name}?v={_uuid.uuid4().hex[:6]}"


@bp.route("/banners/save", methods=["POST"])
@admin_required
def banners_save():
    f = request.form
    bid = f.get("id", type=int)
    fields = {"title": (f.get("title") or "").strip()[:120] or "배너",
              "zone": f.get("zone") if f.get("zone") in ("grid", "slide") else "grid",
              "link": (f.get("link") or "").strip()[:300] or None,
              "sort": f.get("sort", 0, type=int), "is_active": 1 if f.get("is_active") == "1" else 0,
              "start_at": f.get("start_at") or None, "end_at": f.get("end_at") or None}
    file = request.files.get("image")
    if not bid and (not file or not file.filename):
        flash("배너 이미지 파일을 선택해주세요.")
        return redirect(url_for("admin.banners", new=1))
    bid = banner_model.save(bid, fields)
    if file and file.filename:
        try:
            url = _save_banner_image(bid, file)
        except ValueError as e:
            flash(str(e))
            return redirect(url_for("admin.banners", edit=bid))
        banner_model.save(bid, {"image_url": url})
    _log("banner_save", "banner", bid, fields["title"])
    flash("배너를 저장했습니다.")
    return redirect(url_for("admin.banners"))


@bp.route("/banners/<int:banner_id>/toggle", methods=["POST"])
@admin_required
def banners_toggle(banner_id):
    b = banner_model.get(banner_id) or abort(404)
    banner_model.save(banner_id, {"is_active": 0 if b["is_active"] else 1})
    _log("banner_toggle", "banner", banner_id, f"{b['title']} 노출 {'OFF' if b['is_active'] else 'ON'}")
    return redirect(url_for("admin.banners"))


@bp.route("/banners/<int:banner_id>/delete", methods=["POST"])
@admin_required
def banners_delete(banner_id):
    b = banner_model.get(banner_id) or abort(404)
    banner_model.delete(banner_id)
    _log("banner_delete", "banner", banner_id, b["title"])
    return redirect(url_for("admin.banners"))


# =============================================================== users
@bp.route("/users")
@admin_required
def users():
    q = (request.args.get("q") or "").strip()[:40] or None
    status = request.args.get("status") or None
    page, per_page = _page()
    rows, total = user_model.list_admin(q, status if status in ("active", "suspended") else None, page, per_page)
    from ..constants import GRADE_LABEL
    return render_template("admin/users.html", rows=rows, q=q, status=status, page=page, total_pages=max(1, -(-total // per_page)),
                           counts=user_model.count_by_status(), open_id=request.args.get("open", type=int), grade_label=GRADE_LABEL)


# =============================================================== operators
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
# 헷갈리는 글자(l·1·I·O·0)와 HTML 에서 이스케이프되는 글자(& < > " ')를 빼서
# 화면에 보여주고 받아 적기 좋게 만든다.
PW_ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%^*-_"


def _gen_password(n=14):
    return "".join(secrets.choice(PW_ALPHABET) for _ in range(n))


@bp.route("/operators")
@admin_required
def operators():
    """운영자 계정 관리. 발급한 비밀번호는 한 번만 보여주고 저장하지 않는다."""
    return render_template("admin/operators.html", rows=user_model.list_admins(),
                           me=g.user["id"], new_pw=session.pop("new_admin_pw", None))


USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,29}$")


def _read_password(form):
    """(비밀번호, 오류). 비우면 자동 생성."""
    pw = (form.get("password") or "").strip()
    if not pw:
        return _gen_password(), None
    if len(pw) < 4 or len(pw) > 72:
        return None, "비밀번호는 4~72자로 입력해주세요."
    return pw, None


@bp.route("/operators/create", methods=["POST"])
@admin_required
def operators_create():
    email = (request.form.get("email") or "").strip().lower()[:120]
    username = (request.form.get("username") or "").strip().lower()[:30]
    nickname = (request.form.get("nickname") or "").strip()[:20] or "운영팀"
    if not username and not email:
        flash("아이디나 이메일 중 하나는 있어야 합니다.")
        return redirect(url_for("admin.operators"))
    if username and not USERNAME_RE.match(username):
        flash("아이디는 영문 소문자·숫자로 3~30자, . _ - 만 쓸 수 있습니다.")
        return redirect(url_for("admin.operators"))
    if email and not EMAIL_RE.match(email):
        flash("이메일 형식이 올바르지 않습니다.")
        return redirect(url_for("admin.operators"))
    if username and user_model.username_taken(username):
        flash("이미 쓰고 있는 아이디입니다.")
        return redirect(url_for("admin.operators"))
    if email and user_model.get_by_email(email):
        flash("이미 쓰고 있는 이메일입니다. 기존 계정의 비밀번호를 재설정하세요.")
        return redirect(url_for("admin.operators"))
    pw, err = _read_password(request.form)
    if err:
        flash(err)
        return redirect(url_for("admin.operators"))
    uid = user_model.create_admin(email, username, generate_password_hash(pw), nickname)
    _log("admin_create", "user", uid, f"운영자 추가 {username or email}")
    session["new_admin_pw"] = {"email": username or email, "pw": pw, "what": "발급"}
    flash(f"운영자 계정을 만들었습니다: {username or email}")
    return redirect(url_for("admin.operators"))


@bp.route("/operators/<int:user_id>/login-id", methods=["POST"])
@admin_required
def operators_login_id(user_id):
    """로그인 아이디 지정·변경. 이메일 없이 만들어진 기존 계정을 살릴 때도 쓴다."""
    u = user_model.get_by_id(user_id) or abort(404)
    if u["role"] != "admin":
        abort(400)
    username = (request.form.get("username") or "").strip().lower()[:30]
    if username and not USERNAME_RE.match(username):
        flash("아이디는 영문 소문자·숫자로 3~30자, . _ - 만 쓸 수 있습니다.")
    elif username and user_model.username_taken(username, exclude_id=user_id):
        flash("이미 쓰고 있는 아이디입니다.")
    else:
        user_model.set_username(user_id, username)
        _log("admin_login_id", "user", user_id, f"{u['nickname']} 아이디 → {username or '없음'}")
        flash("아이디를 저장했습니다." if username else "아이디를 지웠습니다.")
    return redirect(url_for("admin.operators"))


@bp.route("/operators/<int:user_id>/passwd", methods=["POST"])
@admin_required
def operators_passwd(user_id):
    u = user_model.get_by_id(user_id) or abort(404)
    if u["role"] != "admin":
        abort(400)
    pw, err = _read_password(request.form)
    if err:
        flash(err)
        return redirect(url_for("admin.operators"))
    user_model.set_password(user_id, generate_password_hash(pw))
    _log("admin_passwd", "user", user_id, f"{u['username'] or u['email'] or u['nickname']} 비밀번호 재설정")
    session["new_admin_pw"] = {"email": u["username"] or u["email"] or u["nickname"], "pw": pw, "what": "재설정"}
    flash("비밀번호를 재설정했습니다.")
    return redirect(url_for("admin.operators"))


@bp.route("/operators/<int:user_id>/revoke", methods=["POST"])
@admin_required
def operators_revoke(user_id):
    u = user_model.get_by_id(user_id) or abort(404)
    if u["role"] != "admin":
        abort(400)
    if user_id == g.user["id"]:
        flash("본인 권한은 회수할 수 없습니다. 다른 운영자에게 요청하세요.")
    elif user_model.active_admin_count() <= 1:
        flash("마지막 운영자라 회수할 수 없습니다. 다른 운영자를 먼저 추가하세요.")
    else:
        user_model.set_role(user_id, "user")
        _log("admin_revoke", "user", user_id, f"{u['email'] or u['nickname']} 운영 권한 회수")
        flash(f"{u['nickname']}의 운영 권한을 회수했습니다. 계정은 일반 회원으로 남습니다.")
    return redirect(url_for("admin.operators"))


@bp.route("/operators/<int:user_id>/status", methods=["POST"])
@admin_required
def operators_status(user_id):
    u = user_model.get_by_id(user_id) or abort(404)
    if u["role"] != "admin":
        abort(400)
    if user_id == g.user["id"]:
        flash("본인 계정은 정지할 수 없습니다.")
    elif u["status"] == "active" and user_model.active_admin_count() <= 1:
        flash("마지막 운영자라 정지할 수 없습니다.")
    else:
        new = "active" if u["status"] == "suspended" else "suspended"
        user_model.set_status(user_id, new)
        _log("admin_status", "user", user_id, f"{u['email'] or u['nickname']} → {'정상' if new == 'active' else '정지'}")
        flash(f"{u['nickname']}을(를) {'정상 처리' if new == 'active' else '정지'}했습니다.")
    return redirect(url_for("admin.operators"))


@bp.route("/users/<int:user_id>/grade", methods=["POST"])
@admin_required
def user_grade(user_id):
    u = user_model.get_by_id(user_id) or abort(404)
    grade = request.form.get("grade")
    if grade not in ("biz", "agency", "master"):
        abort(400)
    user_model.update_grade(user_id, grade)
    from ..constants import GRADE_LABEL
    _log("user_grade", "user", user_id, f"{u['nickname']} 등급 → {GRADE_LABEL[grade]}")
    flash(f"{u['nickname']} 등급을 {GRADE_LABEL[grade]}(으)로 변경했습니다.")
    return redirect(url_for("admin.users", q=request.args.get("q")))


@bp.route("/users/<int:user_id>/drawer")
@admin_required
def user_drawer(user_id):
    u = user_model.get_by_id(user_id) or abort(404)
    u["login_id"] = user_model.login_id(u.get("email"), u.get("username"), u.get("kakao_id"), u["id"])
    u["signup_via"] = ("운영자 아이디" if u.get("username") else "이메일 가입" if u.get("email")
                       else "카카오 가입" if u.get("kakao_id") else "가입")
    from ..models import post as post_model
    return render_template("admin/_user_drawer.html", u=u, campaigns=campaign_model.list_by_user(user_id, 20),
                           posts=post_model.list_by_user(user_id, 20), paid_total=campaign_model.total_paid(user_id),
                           status_label=STATUS_LABEL, status_class=STATUS_CLASS, channel_label=CHANNEL_LABEL)


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def user_delete(user_id):
    """빈 계정만 삭제한다. 캠페인·크레딧·글이 있으면 기록이 깨지므로 정지를 쓰게 한다."""
    u = user_model.get_by_id(user_id) or abort(404)
    if u["role"] == "admin":
        flash("운영자 계정은 운영자 관리에서 권한을 회수한 뒤 삭제하세요.")
        return _back(url_for("admin.users"))
    blockers = user_model.deletable_blockers(user_id)
    if blockers:
        flash(f"{u['nickname']}은(는) {', '.join(blockers)}이 있어 삭제할 수 없습니다. 정지를 이용하세요.")
        return _back(url_for("admin.users"))
    user_model.purge(user_id)
    _log("user_delete", "user", user_id, f"{u['nickname']} 회원 삭제")
    flash(f"{u['nickname']} 회원을 삭제했습니다.")
    return _back(url_for("admin.users"))


@bp.route("/users/<int:user_id>/status", methods=["POST"])
@admin_required
def user_status(user_id):
    u = user_model.get_by_id(user_id) or abort(404)
    if u["role"] == "admin":
        flash("관리자 계정은 변경할 수 없습니다.")
        return redirect(url_for("admin.users"))
    new = "active" if u["status"] == "suspended" else "suspended"
    user_model.set_status(user_id, new)
    _log("user_status", "user", user_id, f"{u['nickname']} → {'정상' if new == 'active' else '정지'}")
    flash(f"{u['nickname']} {'정지 해제' if new == 'active' else '정지'}")
    return redirect(url_for("admin.users", q=request.args.get("q")))


# =============================================================== reports
# =============================================================== 게시글 관리
@bp.route("/posts")
@admin_required
def posts():
    """익명 게시판·질문답변 글 관리. 블라인드는 신고 화면, 완전 삭제는 여기서."""
    from ..models import post as post_model
    tab = request.args.get("tab") or "all"
    q = (request.args.get("q") or "").strip()[:40] or None
    page, per_page = _page()
    slug = tab if tab in ("anon", "qna") else None
    rows, total = post_model.list_admin(slug, q, True if tab == "blind" else None, page, per_page)
    return render_template("admin/posts.html", rows=rows, tab=tab, q=q, page=page,
                           total_pages=max(1, -(-total // per_page)), counts=post_model.admin_counts(),
                           channel_label=CHANNEL_LABEL)


@bp.route("/posts/<int:post_id>/delete", methods=["POST"])
@admin_required
def post_delete(post_id):
    from ..models import post as post_model
    p = post_model.get(post_id) or abort(404)
    post_model.purge(post_id)
    _log("post_delete", "post", post_id, f"게시글 삭제 · {p['title'][:40]}")
    flash("게시글을 삭제했습니다. 댓글도 함께 지워집니다.")
    return _back(url_for("admin.posts"))


@bp.route("/posts/bulk-delete", methods=["POST"])
@admin_required
def posts_bulk_delete():
    from ..models import post as post_model
    ids = [int(i) for i in request.form.getlist("ids") if str(i).isdigit()]
    n = 0
    for pid in ids:
        if post_model.get(pid):
            post_model.purge(pid)
            n += 1
    if n:
        _log("post_bulk_delete", "post", None, f"게시글 {n}건 일괄 삭제")
    flash(f"{n}건을 삭제했습니다." if n else "선택된 글이 없습니다.")
    return _back(url_for("admin.posts"))


@bp.route("/posts/<int:post_id>/blind", methods=["POST"])
@admin_required
def post_blind(post_id):
    from ..models import post as post_model
    p = post_model.get(post_id) or abort(404)
    blind = not p["is_blind"]
    report_model.set_blind("post", post_id, blind)
    _log("post_blind" if blind else "post_unblind", "post", post_id, f"{p['title'][:30]} {'블라인드' if blind else '해제'}")
    flash("블라인드 처리했습니다." if blind else "블라인드를 해제했습니다.")
    return _back(url_for("admin.posts"))


@bp.route("/reports")
@admin_required
def reports():
    tt = request.args.get("type") or None
    page, per_page = _page()
    rows, total = report_model.list_reported(tt if tt in ("post", "comment") else None, page, per_page)
    return render_template("admin/reports.html", rows=rows, tt=tt, page=page, total_pages=max(1, -(-total // per_page)))


@bp.route("/reports/<target_type>/<int:target_id>/delete", methods=["POST"])
@admin_required
def report_delete(target_type, target_id):
    from ..models import post as post_model
    if target_type == "post":
        post_model.purge(target_id)
    elif target_type == "comment":
        post_model.purge_comment(target_id)
    else:
        abort(404)
    _log("report_delete", target_type, target_id, f"{target_type}#{target_id} 삭제")
    flash("삭제했습니다.")
    return _back(url_for("admin.reports"))


@bp.route("/reports/<target_type>/<int:target_id>/blind", methods=["POST"])
@admin_required
def report_blind(target_type, target_id):
    if target_type not in ("post", "comment"):
        abort(404)
    blind = request.form.get("blind") == "1"
    report_model.set_blind(target_type, target_id, blind)
    _log("report_blind" if blind else "report_unblind", target_type, target_id, f"{target_type}#{target_id} {'블라인드' if blind else '해제'}")
    return redirect(url_for("admin.reports"))


# =============================================================== agency
@bp.route("/agency")
@admin_required
def agency():
    from ..models import agency as agency_model
    tab = request.args.get("tab", "requests")
    page, per_page = _page()
    if tab == "proposals":
        rows, total = agency_model.list_all_proposals(page, per_page)
    elif tab == "applies":
        rows, total = agency_model.list_applies(None, page, per_page)
    else:
        tab = "requests"; rows, total = agency_model.list_requests(None, None, None, page, per_page)
    return render_template("admin/agency.html", tab=tab, rows=rows, page=page, total_pages=max(1, -(-total // per_page)),
                           pending_applies=agency_model.pending_applies_count(), ag_status=agency_model.STATUS_LABEL,
                           ag_pill=agency_model.STATUS_PILL, ag_channel=agency_model.CHANNEL_LABEL)


@bp.route("/agency/requests/<int:req_id>/status", methods=["POST"])
@admin_required
def agency_request_status(req_id):
    from ..models import agency as agency_model
    r = agency_model.get_request(req_id) or abort(404)
    status = request.form.get("status") if request.form.get("status") in ("open", "closed") else "closed"
    agency_model.set_status(req_id, status)
    _log("agency_status", "agency_request", req_id, f"의뢰 #{req_id} {r['industry']} → {status}")
    return redirect(url_for("admin.agency"))


@bp.route("/agency/applies/<int:apply_id>/review", methods=["POST"])
@admin_required
def agency_apply_review(apply_id):
    from ..models import agency as agency_model
    from ..services import notify_service
    approve = request.form.get("approve") == "1"
    a = agency_model.review_apply(apply_id, approve, g.user["id"]) or abort(404)
    _log("agency_apply_" + ("approve" if approve else "reject"), "user", a["user_id"], f"대행사 인증 {'승인' if approve else '반려'} · {a['biz_no']}")
    notify_service.push(a["user_id"], "agency", "대행사 인증이 " + ("승인되었습니다. 이제 의뢰에 제안을 보낼 수 있어요." if approve else "반려되었습니다."), "/community/agency")
    flash("처리했습니다.")
    return redirect(url_for("admin.agency", tab="applies"))


@bp.route("/agency/requests/<int:req_id>/delete", methods=["POST"])
@admin_required
def agency_request_delete(req_id):
    from ..models import agency as agency_model
    r = agency_model.get_request(req_id) or abort(404)
    agency_model.purge_request(req_id)
    _log("agency_delete", "agency", req_id, f"의뢰 삭제 · {r.get('industry') or r.get('channel')}")
    flash("의뢰를 삭제했습니다. 딸린 제안도 함께 지워집니다.")
    return _back(url_for("admin.agency"))


@bp.route("/agency/proposals/<int:pid>/delete", methods=["POST"])
@admin_required
def agency_proposal_delete(pid):
    from ..models import agency as agency_model
    p = agency_model.get_proposal(pid) or abort(404)
    agency_model.purge_proposal(pid)
    _log("agency_proposal_delete", "agency", pid, f"제안 삭제 (의뢰 #{p['request_id']})")
    flash("제안을 삭제했습니다.")
    return _back(url_for("admin.agency"))


@bp.route("/agency/applies/<int:apply_id>/delete", methods=["POST"])
@admin_required
def agency_apply_delete(apply_id):
    from ..models import agency as agency_model
    agency_model.purge_apply(apply_id)
    _log("agency_apply_delete", "agency", apply_id, "대행사 인증 신청 삭제")
    flash("인증 신청을 삭제했습니다.")
    return _back(url_for("admin.agency"))


@bp.route("/agency/close-stale", methods=["POST"])
@admin_required
def agency_close_stale():
    from ..models import agency as agency_model
    n = agency_model.close_stale(30)
    _log("agency_close_stale", None, None, f"30일 경과 의뢰 자동 마감 {n}건")
    flash(f"{n}건 마감")
    return redirect(url_for("admin.agency"))
