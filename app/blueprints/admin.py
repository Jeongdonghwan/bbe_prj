"""/admin/* — operator screens. Every write is recorded in admin_log."""
import csv
import io
from datetime import date, datetime

from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request, send_file,
                   url_for)

from ..constants import (CHANNEL_LABEL, PAY_METHOD_LABEL, PAYMENT_STATUS_LABEL, STATUS_CLASS, STATUS_LABEL,
                         STATUS_ORDER)
from ..models import admin_log
from ..models import banner as banner_model
from ..models import campaign as campaign_model
from ..models import content as content_model
from ..models import media as media_model
from ..models import payment as payment_model
from ..models import popular as popular_model
from ..models import report as report_model
from ..models import settings as settings_model
from ..models import user as user_model
from ..services import campaign_service, content_service, forbidden_service, media_service, payment_service
from .auth import admin_required
from .main import render_placeholder

bp = Blueprint("admin", __name__, url_prefix="/admin")

PAGES = {
    "": "운영 현황", "orders": "주문 관리", "payments": "결제 내역", "media": "매체사 관리", "popular": "인기 트래픽 설정",
    "content": "공지 · 정보글", "banners": "배너 관리", "users": "회원 목록", "agency": "대행의뢰 · 제안", "reports": "신고 · 블라인드",
}


def _log(action, target_type=None, target_id=None, summary=None):
    admin_log.log(g.user["id"], action, target_type, target_id, summary)


def _back(default):
    ref = request.form.get("back") or request.referrer
    return redirect(ref if ref and "/admin" in ref else default)


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
    page, per_page = _page()
    rows = campaign_model.admin_list(status, channel, media_id, period, q, page, per_page)
    for r in rows:
        r["warn"] = forbidden_service.check([r["biz_name"], r["product_name"], r["main_keyword"], *(r["setting_keywords"] or [])], r["channel"])
        r["day_idx"] = campaign_service.day_index(r)
        r["total_days"] = campaign_service.days_between(r["start_date"], r["end_date"])
        r["today"] = campaign_model.today_rank(r["id"]) if r["status"] == "running" else None
    total = campaign_model.admin_count(status, channel, media_id, period, q)
    counts = campaign_model.admin_status_counts()
    medias = (media_model.list_by_channel(channel, False) if channel else
              media_model.list_by_channel("place", False) + media_model.list_by_channel("store", False) + media_model.list_by_channel("coupang", False))
    return render_template(
        "admin/orders.html", rows=rows, page=page, total_pages=max(1, -(-total // per_page)), counts=counts,
        total_all=sum(counts.values()), status=status, channel=channel, media_id=media_id, period=period, q=q, medias=medias,
        status_order=STATUS_ORDER, status_label=STATUS_LABEL, status_class=STATUS_CLASS, channel_label=CHANNEL_LABEL,
        pay_method_label=PAY_METHOD_LABEL,
    )


def _apply_action(c, action, reason=""):
    """Shared by single/bulk actions. Returns (ok, message)."""
    try:
        if action == "approve":
            c = campaign_service.transition(c, "approved", g.user["id"], "운영팀 승인")
            if c["start_date"] <= date.today():
                c = campaign_service.transition(c, "running", g.user["id"], "구동 시작")
            _log("order_approve", "campaign", c["id"], f"{c['order_no']} 승인 → {c['status']}")
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


@bp.route("/orders/export")
@admin_required
def orders_export():
    from openpyxl import Workbook
    status = request.args.get("status") or None
    channel = request.args.get("channel") or None
    rows = campaign_model.admin_all(status if status in STATUS_LABEL else None, channel if channel in CHANNEL_LABEL else None,
                                    request.args.get("media", type=int), request.args.get("period") or None, request.args.get("q") or None)
    wb = Workbook(); ws = wb.active; ws.title = "orders"
    ws.append(["주문번호", "상태", "채널", "회원", "연락처", "업체", "상품", "키워드", "매체", "시작", "종료", "일 수량", "총 수량",
               "단가", "할인", "VAT", "결제 금액", "환불", "결제수단", "시작 순위", "현재 순위", "링크", "등록일"])
    for r in rows:
        ws.append([r["order_no"], STATUS_LABEL[r["status"]], CHANNEL_LABEL[r["channel"]], r["nickname"], r["user_phone"], r["biz_name"],
                   r["product_name"], r["main_keyword"], r["media_name"], r["start_date"], r["end_date"], r["daily_qty"], r["total_qty"],
                   r["unit_price"], r["discount"], r["vat"], r["paid_amount"], r["refund_amount"], PAY_METHOD_LABEL[r["pay_method"]],
                   r["rank_start"], r["rank_now"], r["target_url"], r["created_at"]])
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    _log("order_export", None, None, f"엑셀 내보내기 {len(rows)}건")
    return send_file(buf, as_attachment=True, download_name=f"orders_{date.today():%Y%m%d}.xlsx",
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
                           channel_label=CHANNEL_LABEL)


@bp.route("/media/save", methods=["POST"])
@admin_required
def media_save():
    f = request.form
    mid = f.get("id", type=int)
    channel = f.get("channel") if f.get("channel") in CHANNEL_LABEL else "place"
    try:
        fields = {
            "channel": channel, "name": f.get("name", "").strip()[:40],
            "group_name": f.get("group_name") if f.get("group_name") in ("리워드", "유입", "복합") else "유입",
            "tagline": f.get("tagline", "").strip()[:80] or None, "color": f.get("color", "#4B5563")[:7],
            "unit_price": int(f.get("unit_price")), "list_price": int(f["list_price"]) if f.get("list_price", "").strip() else None,
            "min_days": int(f.get("min_days", 3)), "min_daily": int(f.get("min_daily", 50)), "max_daily": int(f.get("max_daily", 500)),
            "cutoff_time": (f.get("cutoff_time") or "13:30")[:5] + ":00",
            "efficiency_manual": int(f["efficiency_manual"]) if f.get("efficiency_manual", "").strip() else None,
            "badge": f.get("badge") if f.get("badge") in ("rec", "best", "new") else None,
            "eff_level": f.get("eff_level") if f.get("eff_level") in ("normal", "good", "best") else "good",
            "eff_note": f.get("eff_note", "").strip()[:120] or None,
            "description": f.get("description", "").strip() or None,
            "is_active": 1 if f.get("is_active") == "1" else 0, "same_day": 1 if f.get("same_day") == "1" else 0,
            "sort": int(f.get("sort") or 0),
        }
        if not fields["name"]:
            raise ValueError("이름을 입력해주세요.")
        if fields["min_daily"] > fields["max_daily"]:
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
    try:
        if request.files.get("logo") and request.files["logo"].filename:
            media_service.save_logo(mid, request.files["logo"])
            _log("media_logo", "media", mid, f"{fields['name']} 로고 업로드")
    except media_service.MediaError as e:
        flash(f"저장됨. 로고 오류: {e}")
        return redirect(url_for("admin.media", channel=channel, edit=mid))
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


@bp.route("/media/<int:media_id>/logo/delete", methods=["POST"])
@admin_required
def media_logo_delete(media_id):
    m = media_model.get(media_id) or abort(404)
    media_service.delete_logo(media_id)
    _log("media_logo_delete", "media", media_id, f"{m['name']} 로고 삭제")
    return redirect(url_for("admin.media", channel=m["channel"], edit=media_id))


# =============================================================== popular
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


@bp.route("/content/upload", methods=["POST"])
@admin_required
def content_upload():
    try:
        url = content_service.save_image(request.files.get("image"))
    except content_service.ContentError as e:
        return jsonify(ok=False, error=str(e)), 400
    return jsonify(ok=True, url=url)


# =============================================================== banners
@bp.route("/banners")
@admin_required
def banners():
    rows = banner_model.list_all()
    edit_id = request.args.get("edit", type=int)
    edit = banner_model.get(edit_id) if edit_id else None
    return render_template("admin/banners.html", rows=rows, edit=edit, new=request.args.get("new") == "1")


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
    from ..models import post as post_model
    return render_template("admin/_user_drawer.html", u=u, campaigns=campaign_model.list_by_user(user_id, 20),
                           posts=post_model.list_by_user(user_id, 20), paid_total=campaign_model.total_paid(user_id),
                           status_label=STATUS_LABEL, status_class=STATUS_CLASS, channel_label=CHANNEL_LABEL)


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
@bp.route("/reports")
@admin_required
def reports():
    tt = request.args.get("type") or None
    page, per_page = _page()
    rows, total = report_model.list_reported(tt if tt in ("post", "comment") else None, page, per_page)
    return render_template("admin/reports.html", rows=rows, tt=tt, page=page, total_pages=max(1, -(-total // per_page)))


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


@bp.route("/agency/close-stale", methods=["POST"])
@admin_required
def agency_close_stale():
    from ..models import agency as agency_model
    n = agency_model.close_stale(30)
    _log("agency_close_stale", None, None, f"30일 경과 의뢰 자동 마감 {n}건")
    flash(f"{n}건 마감")
    return redirect(url_for("admin.agency"))
