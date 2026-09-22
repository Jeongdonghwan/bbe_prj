"""/campaign/<channel> — create (with payment), pay/bank pages, manage list + drawer, store hub slots."""
import json
from datetime import date, datetime, timedelta

from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request, session,
                   url_for)

from ..constants import (CHANNEL_LABEL, DATE_PRESETS, PAY_METHOD_LABEL, PAYMENT_STATUS_LABEL, PLACE_CATEGORIES, TRAFFIC_CHANNELS,
                         STATUS_CLASS, STATUS_LABEL, STATUS_ORDER, STORE_SLOT_MAX, reco_qty)
from ..models import campaign as campaign_model
from ..models import content as content_model
from ..models import media as media_model
from ..models import review as review_model
from ..models import weekly_rank
from ..models import payment as payment_model
from ..models import store_slot as slot_model
from ..services import (campaign_service, forbidden_service, keyword_service, payment_service, rank_client,
                        url_service)
from .auth import login_required
from .main import render_placeholder


def bank_info():
    from ..models import settings as settings_model
    s = settings_model.get_all()
    cfg = current_app.config["BANK_INFO"]
    return {"bank": s.get("bank_name") or cfg["bank"], "account": s.get("bank_account") or cfg["account"], "holder": s.get("bank_holder") or cfg["holder"]}

bp = Blueprint("campaign", __name__, url_prefix="/campaign")
api = Blueprint("campaign_api", __name__, url_prefix="/api/campaign")
prod = Blueprint("product_api", __name__, url_prefix="/api/product")
pop = Blueprint("popular", __name__)

CHANNELS = CHANNEL_LABEL


def _channel(channel):
    if channel not in CHANNELS:
        abort(404)
    return channel


def _own(channel, campaign_id):
    c = campaign_model.get(campaign_id)
    if not c or c["user_id"] != g.user["id"] or c["channel"] != channel:
        abort(404)
    return c


# =============================================================== create
def _media_ctx(channel):
    """Media tiles grouped into fixed sections (리워드/유입/복합, stored in media.group_name)."""
    from ..constants import MEDIA_SECTIONS
    medias = media_model.list_by_channel(channel)
    for m in medias:
        m["initial"] = m["name"][:1]
    medias.sort(key=lambda m: (0 if m["badge"] == "rec" else 1, m["sort"], m["unit_price"]))
    sections = []
    order = MEDIA_SECTIONS.get(channel, [])
    for name in order:
        items = [m for m in medias if m["group_name"] == name]
        if items:
            sections.append({"name": name, "items": items})
    rest = [m for m in medias if m["group_name"] not in order]
    if rest:
        sections.append({"name": "기타", "items": rest})
    return medias, sections


def _prefill(channel):
    """Prefill from ?copy=, ?edit=, ?slot= or session 'campaign_prefill'."""
    pre, editing = {}, None
    cid = request.args.get("copy", type=int)
    xid = request.args.get("extend", type=int)
    eid = request.args.get("edit", type=int)
    sid = request.args.get("slot", type=int)
    if eid:
        editing = _own(channel, eid)
        if editing["status"] != "pay_wait":
            flash("결제 대기 상태의 주문만 수정할 수 있습니다.")
            return redirect(url_for("campaign.manage", channel=channel))
        pre = dict(editing)
    elif cid or xid:
        src = _own(channel, cid or xid)
        pre = {k: src[k] for k in ("media_id", "biz_name", "product_name", "target_url", "main_keyword", "sub_keywords",
                                    "setting_keywords", "keyword_mode", "extra", "daily_qty")}
        pre["media_id"] = src["media_id"]
        if xid:
            days = (src["end_date"] - src["start_date"]).days + 1
            start = _next_weekday(max(date.today(), src["end_date"] + timedelta(days=1)))
            pre["start_date"] = start.isoformat()
            pre["end_date"] = (start + timedelta(days=days - 1)).isoformat()
            flash(f"{src['order_no']} 기간 연장 — 기존 종료일 다음 영업일부터 같은 설정으로 이어집니다.")
    elif sid and channel == "store":
        s = slot_model.get(sid, g.user["id"])
        if s:
            pre = {"main_keyword": s["keyword"], "target_url": s["product_url"] or "", "biz_name": s["store_name"] or "",
                   "daily_qty": s["reco_qty"], "slot_reco": s["reco_qty"]}
    elif session.get("campaign_prefill"):
        pre = session.pop("campaign_prefill")
    if "media_id" not in pre and request.args.get("media", type=int):
        pre["media_id"] = request.args.get("media", type=int)
    return pre, editing


def _next_weekday(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


@bp.route("/<channel>/new", methods=["GET", "POST"])
@login_required
def new(channel):
    _channel(channel)
    if request.method == "POST":
        return _create(channel)
    picked = request.args.get("type", type=int)
    if picked:
        # 인기 트래픽에서 상품을 고르고 넘어온 경우. Step 2 자동 선택은 다음 작업.
        current_app.logger.info("wizard %s opened with type=%s", channel, picked)
    pre = _prefill(channel)
    if not isinstance(pre, tuple):
        return pre
    pre, editing = pre
    medias, sections = _media_ctx(channel)
    from ..models import daily_pick as pick_model
    picks = pick_model.get(channel, date.today())
    by_id = {m["id"]: m for m in medias}
    today_picks = [by_id[i]["name"] for i in picks if i in by_id]
    min_start = campaign_service.earliest_start()
    pre_start = min_start
    if pre.get("start_date"):
        try:
            cand = pre["start_date"] if isinstance(pre["start_date"], date) else date.fromisoformat(str(pre["start_date"]))
            pre_start = max(cand, min_start)
        except (ValueError, TypeError):
            pre_start = min_start
    pre_days = 10
    if pre.get("start_date") and pre.get("end_date"):
        try:
            sd = pre["start_date"] if isinstance(pre["start_date"], date) else date.fromisoformat(str(pre["start_date"]))
            ed = pre["end_date"] if isinstance(pre["end_date"], date) else date.fromisoformat(str(pre["end_date"]))
            d = campaign_service.days_between(sd, ed)
            pre_days = d if d in DATE_PRESETS else 10
        except (ValueError, TypeError):
            pre_days = 10
    return render_template(
        "campaign/new.html", channel=channel, channels=CHANNELS, sections=sections,
        pre=pre, editing=editing, presets=DATE_PRESETS, pre_days=pre_days,
        min_start=min_start, pre_start=pre_start,
        group_names=[s["name"] for s in sections],
        types_json=json.dumps({
            m["id"]: {"g": next((i for i, s in enumerate(sections) if m in s["items"]), 0),
                      "n": m["name"], "p": m["unit_price"], "max": m["max_daily"] or 0,
                      "badge": m["badge"], "badge_label": m["badge_label"],
                      "desc": m["description"] or "", "fit": m["fit_for"], "flow": m["flow_steps"]}
            for m in medias}, ensure_ascii=False),
        today_picks=today_picks,
        # 미리보기는 쇼핑·스토어만. 쿠팡·플레이스는 순위 서버가 읽지 못한다 (2026-09-21 JDH).
        preview_on=channel == "store",
        preview_live=channel == "store" and rank_client.configured(),
        balance=g.user["credit_balance"], place_categories=PLACE_CATEGORIES,
        bank=bank_info(), is_debug=current_app.debug,
    )


def _parse_form(channel, media, form):
    """Validate the create/edit form. Returns (data, error_message)."""
    f = {}
    try:
        f["start_date"] = date.fromisoformat(form.get("start_date", ""))
        f["end_date"] = date.fromisoformat(form.get("end_date", ""))
    except ValueError:
        return None, "기간을 선택해주세요."
    if f["end_date"] < f["start_date"]:
        return None, "종료일이 시작일보다 빠릅니다."
    if f["start_date"] <= date.today():
        return None, "시작일은 내일 이후여야 합니다. 당일 구동은 제공하지 않습니다."
    days = campaign_service.days_between(f["start_date"], f["end_date"])
    if days < media["min_days"]:
        return None, f"이 매체는 최소 {media['min_days']}일 이상 설정해야 합니다."
    if days > 60:
        return None, "기간은 최대 60일입니다."
    try:
        f["daily_qty"] = int(form.get("daily_qty", "0"))
    except ValueError:
        return None, "일 작업량을 입력해주세요."
    if f["daily_qty"] < media["min_daily"]:
        return None, f"일 작업량은 {media['min_daily']}건 이상이어야 합니다."
    if media["max_daily"] and f["daily_qty"] > media["max_daily"]:
        return None, f"이 유형의 일 작업량은 최대 {media['max_daily']}건입니다."

    f["biz_name"] = (form.get("biz_name") or "").strip()[:80]
    f["product_name"] = (form.get("product_name") or "").strip()[:120] or None
    try:
        f["target_url"] = url_service.normalize(form.get("target_url"), channel)
    except url_service.URLError as e:
        return None, str(e)
    f["main_keyword"] = " ".join((form.get("main_keyword") or "").split())[:60]
    if not f["main_keyword"]:
        return None, "희망 키워드를 입력해주세요."
    if channel in ("store", "coupang"):
        # 상품명은 선택 입력 (2026-09-21 JDH). 비우면 키워드를 목록 표시명으로 쓴다.
        f["biz_name"] = f["product_name"] or f["main_keyword"]
    elif not f["biz_name"]:
        return None, "플레이스명을 입력해주세요."
    f["sub_keywords"] = []
    f["keyword_mode"] = "manual"
    f["setting_keywords"] = [f["main_keyword"]]
    extra = {}
    if channel == "place" and form.get("category") in PLACE_CATEGORIES:
        extra["category"] = form.get("category")  # legacy prefills only; the field was dropped 2026-09-01
    f["extra"] = extra

    found = forbidden_service.check([f["biz_name"], f["product_name"], f["main_keyword"]], channel)
    if found["block"]:
        return None, f"사용할 수 없는 문구가 포함되어 있습니다: {', '.join(found['block'])}"
    f["warn_words"] = ", ".join(found["warn"]) or None
    return f, None


def _create(channel):
    """Credit model: wizard posts type/date/qty; server re-reads the unit price and re-checks the total."""
    media_id = request.form.get("media_id", type=int)
    media = media_model.get(media_id) if media_id else None
    if not media or media["channel"] != channel or not media["is_active"]:
        flash("광고 유형을 선택해주세요.")
        return redirect(url_for("campaign.new", channel=channel))
    days = request.form.get("days", type=int)
    if days not in DATE_PRESETS:
        flash("광고 기간을 선택해주세요.")
        return redirect(url_for("campaign.new", channel=channel))
    earliest = campaign_service.earliest_start()
    try:
        start = date.fromisoformat(request.form.get("start_date", ""))
    except ValueError:
        flash("시작일을 선택해주세요.")
        return _back(channel, media_id)
    if start < earliest:
        flash(f"시작일은 {earliest.strftime('%Y.%m.%d')} 이후로 선택해주세요. 접수는 24시간 가능하고 구동은 다음 날부터 시작됩니다.")
        return _back(channel, media_id)
    form = request.form.to_dict()
    form["start_date"] = start.isoformat()
    form["end_date"] = (start + timedelta(days=days - 1)).isoformat()
    data, err = _parse_form(channel, media, form)
    if err:
        flash(err)
        return _back(channel, media_id)
    note = (request.form.get("request_note") or "").strip()[:500]
    if note:
        data["extra"]["request_note"] = note
    expected = int(media["unit_price"]) * data["daily_qty"] * days
    shown = request.form.get("client_total", type=int)
    if shown is not None and shown != expected:
        flash(f"금액이 달라졌습니다. 총 광고비 {expected:,}원으로 다시 확인해주세요.")
        return _back(channel, media_id)
    try:
        c = campaign_service.create_with_credit(g.user, media, data)
    except campaign_service.CampaignError as e:
        flash(str(e))
        return _back(channel, media_id)
    flash(f"광고를 만들었습니다. 검수 후 구동이 시작됩니다. (주문번호 {c['order_no']})")
    return redirect(url_for("campaign.manage", channel=channel, open=c["id"]))


def _back(channel, media_id):
    """Return to the wizard keeping what the user typed."""
    session["campaign_prefill"] = {k: v for k, v in request.form.items() if k != "csrf"}
    session["campaign_prefill"]["media_id"] = media_id
    return redirect(url_for("campaign.new", channel=channel))


@bp.route("/<channel>/<int:campaign_id>/pay")
@login_required
def pay(channel, campaign_id):
    c = _own(_channel(channel), campaign_id)
    p = payment_model.get_for_campaign(c["id"])
    if c["status"] != "pay_wait" or not p or p["method"] != "card":
        return redirect(url_for("campaign.manage", channel=channel, open=c["id"]))
    from ..services.pg import get_adapter
    adapter = get_adapter()
    params = adapter.request(p, c, g.user)
    return render_template("campaign/pay.html", channel=channel, c=c, p=p, pg=params, adapter=adapter,
                           is_debug=current_app.debug, status_label=STATUS_LABEL)


@bp.route("/<channel>/<int:campaign_id>/pay/confirm", methods=["POST"])
@login_required
def pay_confirm(channel, campaign_id):
    c = _own(_channel(channel), campaign_id)
    from ..services.pg import get_adapter
    if get_adapter().name == "mock" and not current_app.debug:
        abort(404)
    try:
        payment_service.confirm_card(c, g.user["id"], request.form.get("token"))
    except payment_service.PaymentError as e:
        flash(str(e))
        return redirect(url_for("campaign.pay", channel=channel, campaign_id=c["id"]))
    flash(f"결제가 완료되었습니다. 주문 {c['order_no']}은(는) 검수 후 구동됩니다.")
    return redirect(url_for("campaign.manage", channel=channel, open=c["id"]))


@bp.route("/<channel>/<int:campaign_id>/bank")
@login_required
def bank(channel, campaign_id):
    c = _own(_channel(channel), campaign_id)
    p = payment_model.get_for_campaign(c["id"])
    if not p or p["method"] != "bank":
        return redirect(url_for("campaign.manage", channel=channel, open=c["id"]))
    return render_template("campaign/bank.html", channel=channel, c=c, p=p, bank=bank_info(),
                           status_label=STATUS_LABEL, pay_status_label=PAYMENT_STATUS_LABEL)


# =============================================================== manage
@bp.route("/<channel>")
@login_required
def manage(channel):
    _channel(channel)
    uid = g.user["id"]
    status = request.args.get("status") or None
    if status and status not in STATUS_LABEL:
        status = None
    period = request.args.get("period") or None
    media_id = request.args.get("media", type=int)
    q = (request.args.get("q") or "").strip()[:60] or None
    page = max(1, request.args.get("page", 1, type=int))
    per_page = current_app.config["PER_PAGE"]
    rows = campaign_model.list_user(uid, channel, status, period, media_id, q, page, per_page)
    total = campaign_model.count_user(uid, channel, status, period, media_id, q)
    for r in rows:
        r["prog"] = campaign_service.progress(r)
    counts = campaign_model.status_counts(uid, channel)
    running = counts.get("running", 0)
    avg_up, done_n = campaign_model.avg_rank_change(uid, channel)
    month, last = campaign_model.month_paid(uid, channel), campaign_model.last_month_paid(uid, channel)
    delta = None if not last else int((month - last) / last * 100)
    stats = {
        "running": running, "today_spend": campaign_model.running_today_spend(uid, channel),
        "waiting": counts.get("pay_wait", 0) + counts.get("review", 0) + counts.get("approved", 0),
        "month_paid": month, "delta": delta, "avg_up": avg_up, "done_n": done_n,
    }
    return render_template(
        "campaign/manage.html", channel=channel, channels=CHANNELS, rows=rows, page=page,
        total_pages=max(1, -(-total // per_page)), counts=counts, total_all=sum(counts.values()),
        status=status, period=period, media_id=media_id, q=q, stats=stats,
        media_options=campaign_model.media_used(uid, channel),
        status_order=STATUS_ORDER, status_label=STATUS_LABEL, status_class=STATUS_CLASS,
        open_id=request.args.get("open", type=int),
    )


@bp.route("/<channel>/<int:campaign_id>/drawer")
@login_required
def drawer(channel, campaign_id):
    c = _own(_channel(channel), campaign_id)
    p = payment_model.get_for_campaign(c["id"])
    daily = campaign_model.list_daily(c["id"])
    ranks = [d for d in daily if d["rank"]]
    best = min((d["rank"] for d in ranks), default=None)
    worst = max((d["rank"] for d in ranks), default=None)
    for d in ranks:
        # lower rank = taller bar
        d["h"] = 100 if worst == best else int(30 + (worst - d["rank"]) / (worst - best) * 70)
    return render_template(
        "campaign/_drawer.html", channel=channel, c=c, p=p, daily=daily, ranks=ranks[-14:],
        done_qty=campaign_model.total_done_qty(c["id"]), logs=campaign_model.list_log(c["id"]),
        prog=campaign_service.progress(c), day_idx=campaign_service.day_index(c),
        status_label=STATUS_LABEL, status_class=STATUS_CLASS, pay_method_label=PAY_METHOD_LABEL,
        pay_status_label=PAYMENT_STATUS_LABEL,
    )


@bp.route("/<channel>/<int:campaign_id>/ranks")
@login_required
def ranks(channel, campaign_id):
    """Daily rank sheet shown in a modal from the manage list (2026-09-01)."""
    _channel(channel)
    c = _own(channel, campaign_id)
    days, today_rank, delta = [], None, None
    if channel != "coupang":
        rankmap = {d["date"]: d["rank"] for d in campaign_model.list_daily(campaign_id)}
        cur = min(date.today(), c["end_date"])
        while cur >= c["start_date"]:
            days.append({"date": cur, "rank": rankmap.get(cur)})
            cur -= timedelta(days=1)
        today_rank = rankmap.get(date.today())
        if c["rank_start"] and today_rank:
            delta = c["rank_start"] - today_rank
    return render_template("campaign/_ranks.html", c=c, channel=channel, days=days,
                           today_rank=today_rank, delta=delta,
                           wd=["월", "화", "수", "목", "금", "토", "일"])


@bp.route("/<channel>/<int:campaign_id>/cancel", methods=["POST"])
@login_required
def cancel(channel, campaign_id):
    c = _own(_channel(channel), campaign_id)
    try:
        campaign_service.cancel(c, g.user["id"])
        flash("주문을 취소했습니다.")
    except campaign_service.CampaignError as e:
        flash(str(e))
    return redirect(url_for("campaign.manage", channel=channel))


@bp.route("/<channel>/<int:campaign_id>/stop", methods=["POST"])
@login_required
def stop(channel, campaign_id):
    c = _own(_channel(channel), campaign_id)
    try:
        c = campaign_service.stop(c, g.user["id"])
        flash(f"캠페인을 중단했습니다. 잔여일분 {c['refund_amount']:,}원이 환불 처리됩니다.")
    except (campaign_service.CampaignError, payment_service.PaymentError) as e:
        flash(str(e))
    return redirect(url_for("campaign.manage", channel=channel, open=c["id"]))


# =============================================================== store slots (2-4-1, standalone page)
@bp.route("/store/slots")
@login_required
def slots():
    return render_template("campaign/slots.html", channel="store", channels=CHANNELS, store=_store_hub_ctx())


def _store_hub_ctx():
    uid = g.user["id"]
    slots = slot_model.list_user(uid)
    for s in slots:
        s["total"] = s["pc_cnt"] + s["mo_cnt"]
        s["daily"] = round(s["total"] / 30)
    notices = content_model.list_channel_notices("store", 1)
    return {
        "slots": slots, "slot_max": STORE_SLOT_MAX, "slot_used": len(slots),
        "notice": notices[0] if notices else None, "notice_count": content_model.count_channel_notices("store"),
        "running": campaign_model.list_recent_channel(uid, "store", 5),
    }


@bp.route("/store/slots", methods=["POST"])
@login_required
def slot_add():
    kw = " ".join((request.form.get("keyword") or "").split())[:60]
    if not kw:
        flash("상품 키워드를 입력해주세요.")
    elif slot_model.count_user(g.user["id"]) >= STORE_SLOT_MAX:
        flash(f"슬롯은 최대 {STORE_SLOT_MAX}개입니다.")
    else:
        url = (request.form.get("product_url") or "").strip()[:500]
        if url:
            try:
                url = url_service.normalize(url, "store")
            except url_service.URLError as e:
                flash(str(e))
                return redirect(url_for("campaign.slots"))
        pc, mo = keyword_service.search_volume(kw)
        slot_model.insert(g.user["id"], kw, url, (request.form.get("store_name") or "").strip()[:80], pc, mo, reco_qty(pc + mo))
        flash(f"'{kw}' 슬롯을 등록했습니다.")
    return redirect(url_for("campaign.slots"))


@bp.route("/store/slots/<int:slot_id>/delete", methods=["POST"])
@login_required
def slot_delete(slot_id):
    slot_model.delete(slot_id, g.user["id"])
    return redirect(url_for("campaign.slots"))


@bp.route("/<channel>/popular")
def popular_legacy(channel):
    _channel(channel)
    return redirect(url_for("popular.popular", ch=channel, cat=request.args.get("cat")))


def traffic_list(channel):
    """Active types for a channel, decorated with this week's operator rank."""
    ranks = weekly_rank.by_type(channel)
    rows = media_model.list_by_channel(channel)
    for m in rows:
        m["rank"] = ranks.get(m["id"])
    rows.sort(key=lambda m: (m["rank"] or 99, -m["review_cnt"]))
    return rows


def _channel_view(channel):
    """One channel's sections. 세 채널을 모두 렌더해 두고 탭은 클라이언트에서 전환한다."""
    rows = traffic_list(channel)
    own = [m for m in rows if m["origin"] == "own"]
    groups = []
    if any(m["group_key"] for m in own):
        for key, label in (("reward", "자체 개발 · 리워드"), ("inflow", "자체 개발 · 유입플")):
            items = [m for m in own if m["group_key"] == key]
            if items:
                groups.append((label, items))
    elif own:
        groups.append(("자체 개발", own))
    ready = [m for m in rows if m["origin"] == "ready"]
    if ready:
        groups.append(("기성 매체", ready))
    return {"top3": [m for m in rows if m["rank"]][:3], "groups": groups, "total": len(rows)}


@pop.route("/popular")
def popular():
    """채널·정렬 모두 클라이언트 전환. 현재 채널은 ?ch= 에 남겨 새로고침·공유 시 유지된다."""
    valid = [k for k, _ in TRAFFIC_CHANNELS]
    channel = request.args.get("ch") if request.args.get("ch") in valid else valid[0]
    return render_template("popular/index.html", channel=channel, channels=TRAFFIC_CHANNELS,
                           week_label=weekly_rank.week_label(),
                           views={ch: _channel_view(ch) for ch in valid})


@pop.route("/popular/drawer/<int:type_id>")
def popular_drawer(type_id):
    """Drawer contents only — the page and the dashboard widget both inject this."""
    m = media_model.get(type_id)
    if not m or not m["is_active"]:
        abort(404)
    m["rank"] = weekly_rank.by_type(m["channel"]).get(m["id"])
    draft = review_model.done_campaign_without_review(g.user["id"], type_id) if g.get("user") else None
    return render_template("popular/_drawer.html", m=m, channel_label=CHANNELS[m["channel"]],
                           reviews=review_model.list_for(type_id), dist=review_model.star_dist(type_id),
                           can_write=bool(draft), draft=draft or {})


@pop.route("/popular/review", methods=["POST"])
@login_required
def popular_review():
    """후기는 그 상품으로 완료한 캠페인이 있어야 쓸 수 있고, 완료 캠페인당 1건이다."""
    from ..services import mask_service, nick_service
    type_id = request.form.get("type_id", type=int)
    m = media_model.get(type_id) if type_id else None
    if not m:
        abort(404)
    stars = request.form.get("stars", type=int) or 0
    body = " ".join((request.form.get("body") or "").split())[:600]
    draft = review_model.done_campaign_without_review(g.user["id"], type_id)
    if not draft or draft["id"] != request.form.get("campaign_id", type=int):
        flash("이 상품으로 완료한 캠페인이 있어야 후기를 쓸 수 있습니다.")
    elif not 1 <= stars <= 5 or len(body) < 10:
        flash("별점을 고르고 후기를 10자 이상 적어주세요.")
    else:
        review_model.insert(type_id, g.user["id"], draft["id"], stars, mask_service.mask(body),
                            nick_service.draw(), draft["main_keyword"],
                            campaign_service.days_between(draft["start_date"], draft["end_date"]))
        review_model.recount(type_id)
        flash("후기를 등록했습니다.")
    return redirect(url_for("popular.popular", ch=m["channel"]))


# =============================================================== JSON API
@api.route("/quote", methods=["POST"])
def api_quote():
    d = request.get_json(silent=True) or request.form
    media = media_model.get(int(d.get("media_id", 0) or 0))
    if not media:
        return jsonify(ok=False, error="media"), 400
    try:
        s, e = date.fromisoformat(d["start_date"]), date.fromisoformat(d["end_date"])
        qty = int(d["daily_qty"])
    except (KeyError, ValueError):
        return jsonify(ok=False, error="input"), 400
    days = campaign_service.days_between(s, e)
    return jsonify(ok=True, **campaign_service.quote(media["unit_price"], qty, days))


@prod.route("/preview")
@login_required
def api_product_preview():
    """Proxy to the rank server so the partner token stays server side.

    Best-effort: any failure answers {"ok": false} and the wizard just keeps manual entry.
    """
    return jsonify(rank_client.product_preview(request.args.get("url", "")))


@api.route("/keywords")
def api_keywords():
    return jsonify(keywords=keyword_service.suggest_setting_keywords(request.args.get("kw", ""), request.args.get("channel", "place")))


@api.route("/volume")
def api_volume():
    kw = (request.args.get("kw") or "").strip()
    if not kw:
        return jsonify(ok=False)
    pc, mo = keyword_service.search_volume(kw)
    return jsonify(ok=True, pc=pc, mo=mo, total=pc + mo, daily=round((pc + mo) / 30), reco=reco_qty(pc + mo))
