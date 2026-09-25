"""Campaign orders: quote, create (campaign + payment in one transaction), transition (state table + status_log)."""
import math
import secrets
from datetime import date, datetime, timedelta

from ..constants import DISCOUNT_RULES, TRANSITIONS, VAT_RATE
from ..models import campaign as campaign_model
from ..models import media as media_model
from . import payment_service


class CampaignError(Exception):
    pass


# ---- quote ---------------------------------------------------------------
def quote(unit_price, daily_qty, days):
    order = int(unit_price) * int(daily_qty) * int(days)
    discount = 0
    for minimum, rate in DISCOUNT_RULES:
        if order >= minimum:
            discount = int(round(order * rate))
            break
    supply = order - discount
    vat = int(round(supply * VAT_RATE))
    return {"order": order, "discount": discount, "supply": supply, "vat": vat, "total": supply + vat,
            "days": int(days), "daily_qty": int(daily_qty), "unit_price": int(unit_price)}


def days_between(start, end):
    return (end - start).days + 1


# ---- create ----------------------------------------------------------------
def new_order_no():
    for _ in range(20):
        no = "N" + "".join(str(secrets.randbelow(10)) for _ in range(9))
        if not campaign_model.order_no_exists(no):
            return no
    raise CampaignError("order_no allocation failed")


def create(user, media, form, method, depositor=None):
    """form: validated dict from blueprint (biz_name, product_name, target_url, main_keyword, sub_keywords,
    setting_keywords, keyword_mode, extra, start_date, end_date, daily_qty, warn_words)."""
    days = days_between(form["start_date"], form["end_date"])
    q = quote(media["unit_price"], form["daily_qty"], days)
    cid = campaign_model.insert({
        "order_no": new_order_no(), "user_id": user["id"], "channel": media["channel"], "media_id": media["id"],
        "status": "pay_wait",
        "biz_name": form["biz_name"], "product_name": form.get("product_name"), "target_url": form["target_url"],
        "nv_mid": form.get("nv_mid"),
        "main_keyword": form["main_keyword"], "sub_keywords": form.get("sub_keywords") or [],
        "setting_keywords": form.get("setting_keywords") or [], "keyword_mode": form.get("keyword_mode", "ai"),
        "extra": form.get("extra") or {},
        "start_date": form["start_date"], "end_date": form["end_date"],
        "daily_qty": form["daily_qty"], "total_qty": form["daily_qty"] * days,
        "unit_price": media["unit_price"], "discount": q["discount"], "vat": q["vat"], "paid_amount": q["total"],
        "pay_method": method, "warn_words": form.get("warn_words"),
    })
    campaign = campaign_model.get(cid)
    payment_service.create(campaign, user, method, depositor)
    return campaign


def earliest_start(now=None):
    """접수는 24시간, 구동은 익일부터. ORDER_CUTOFF(16:00) 이후 접수는 익익일 (2026-09-21 JDH)."""
    from ..constants import ORDER_CUTOFF
    now = now or datetime.now()
    return now.date() + timedelta(days=1 if now.strftime("%H:%M") < ORDER_CUTOFF else 2)


def create_with_credit(user, media, form):
    """Credit model (2026-09-16): cost = 단가×일수량×일수, VAT 없음(충전 시 부과).
    Spends credit atomically, then creates the campaign already in review."""
    from . import credit_service
    days = days_between(form["start_date"], form["end_date"])
    cost = int(media["unit_price"]) * int(form["daily_qty"]) * days
    cid = campaign_model.insert({
        "order_no": new_order_no(), "user_id": user["id"], "channel": media["channel"], "media_id": media["id"],
        "status": "review",
        "biz_name": form["biz_name"], "product_name": form.get("product_name"), "target_url": form["target_url"],
        "nv_mid": form.get("nv_mid"),
        "main_keyword": form["main_keyword"], "sub_keywords": form.get("sub_keywords") or [],
        "setting_keywords": form.get("setting_keywords") or [], "keyword_mode": form.get("keyword_mode", "manual"),
        "extra": form.get("extra") or {},
        "start_date": form["start_date"], "end_date": form["end_date"],
        "daily_qty": form["daily_qty"], "total_qty": form["daily_qty"] * days,
        "unit_price": media["unit_price"], "discount": 0, "vat": 0, "paid_amount": cost,
        "pay_method": "credit", "paid_at": datetime.now(), "warn_words": form.get("warn_words"),
    })
    try:
        credit_service.spend(user["id"], cost, cid, f"광고비 · {media['name']} {days}일")
    except credit_service.CreditError:
        campaign_model.delete(cid)
        raise CampaignError("크레딧 잔액이 부족합니다. 충전 후 다시 시도해주세요.")
    campaign_model.add_log(cid, None, "review", user["id"], f"크레딧 결제 {cost:,}원 · 검수 대기")
    c = campaign_model.get(cid)
    spawn_track(c)          # 등록 즉시 순위 추적 시작 (검수 결과를 기다리지 않는다)
    return campaign_model.get(cid)


def update_pending(campaign, media, form, depositor=None):
    """Edit an unpaid (pay_wait) order in place; recomputes amount and payment."""
    from ..models import payment as payment_model
    if campaign["status"] != "pay_wait":
        raise CampaignError("결제 대기 상태에서만 수정할 수 있습니다.")
    days = days_between(form["start_date"], form["end_date"])
    q = quote(media["unit_price"], form["daily_qty"], days)
    campaign_model.update(campaign["id"], {
        "media_id": media["id"], "biz_name": form["biz_name"], "product_name": form.get("product_name"),
        "target_url": form["target_url"], "main_keyword": form["main_keyword"],
        "sub_keywords": form.get("sub_keywords") or [], "setting_keywords": form.get("setting_keywords") or [],
        "keyword_mode": form.get("keyword_mode", "ai"), "extra": form.get("extra") or {},
        "start_date": form["start_date"], "end_date": form["end_date"],
        "daily_qty": form["daily_qty"], "total_qty": form["daily_qty"] * days,
        "unit_price": media["unit_price"], "discount": q["discount"], "vat": q["vat"], "paid_amount": q["total"],
        "warn_words": form.get("warn_words"),
    })
    p = payment_model.get_for_campaign(campaign["id"])
    if p and p["status"] == "pending":
        fields = {"amount": q["total"]}
        if p["method"] == "bank" and depositor:
            fields["depositor"] = depositor
        payment_model.update(p["id"], fields)
    campaign_model.add_log(campaign["id"], "pay_wait", "pay_wait", campaign["user_id"], f"주문 수정 · {q['total']:,}원")
    return campaign_model.get(campaign["id"])


# ---- transition ----------------------------------------------------------
def transition(campaign, to_status, actor_id=None, memo=None):
    """The only way to change campaigns.status. Validates the table, writes status_log, handles refunds."""
    frm = campaign["status"]
    if to_status not in TRANSITIONS.get(frm, set()):
        raise CampaignError(f"허용되지 않는 상태 변경: {frm} → {to_status}")
    campaign_model.set_status(campaign["id"], to_status)
    campaign_model.add_log(campaign["id"], frm, to_status, actor_id, memo)
    _notify_status(campaign, frm, to_status, memo)
    if to_status in ("approved", "running"):
        spawn_track(campaign)
    elif to_status in ("done", "stopped", "cancelled", "rejected"):
        untrack_if_unused(campaign)
    return campaign_model.get(campaign["id"])


def advance_due(actor_id=None):
    """종료일이 지난 구동건을 완료로 넘긴다 (크론). approved 로 남은 옛 주문도 함께 정리.

    지금은 승인하면 곧장 running 이라 앞쪽 루프는 옛 주문 전용이다. 뒤쪽 루프가 본론 —
    운영자가 매일 "완료"를 누르지 않아도 종료일이 지나면 알아서 닫힌다.
    """
    started = finished = 0
    for c in campaign_model.due_to_start():
        try:
            transition(c, "running", actor_id, "시작일 도래 · 자동 구동")
            started += 1
        except CampaignError:
            pass
    for c in campaign_model.due_to_finish():
        try:
            transition(c, "done", actor_id,
                       f"종료일 경과 · 자동 완료 (누적 {campaign_model.total_done_qty(c['id']):,}건)")
            finished += 1
        except CampaignError:
            pass
    return started, finished


# ---- 순위 자동 추적 (docs/RANK_INTEGRATION.md 2단계) ------------------------
def spawn_track(campaign):
    """순위 서버에 추적 슬롯을 만든다. 쇼핑 채널만, 실패해도 상태 전이는 그대로 간다."""
    from . import rank_client
    if campaign["channel"] != "store" or campaign.get("track_id"):
        return None
    r = rank_client.register_slot(campaign.get("main_keyword"), campaign.get("target_url"))
    if not r.get("ok"):
        return None
    fields = {"track_id": r["trackId"], "track_status": r.get("status") or "queued"}
    campaign_model.update(campaign["id"], fields)
    # 오늘 이미 수집된 키워드면 순위가 바로 들어 있다.
    if r.get("status") == "collected" and r.get("rank") is not None and r.get("date"):
        try:
            apply_rank(campaign["id"], date.fromisoformat(r["date"]), r["rank"])
        except (ValueError, TypeError):
            pass
    return r["trackId"]


def untrack_if_unused(campaign):
    """같은 track_id 를 쓰는 다른 진행 캠페인이 없을 때만 추적을 끊는다.

    순위 서버의 파트너 슬롯은 `partner:bbe` 공용 계정이라 우리가 지우면 트리플업 쪽
    추적도 끊긴다. 그래서 기본은 끄고(RANK_UNTRACK_ON_STOP), 켠 경우에만 삭제한다.
    """
    from flask import current_app

    from . import rank_client
    tid = campaign.get("track_id")
    if not tid or not current_app.config.get("RANK_UNTRACK_ON_STOP"):
        return False
    if campaign_model.count_active_by_track(tid, exclude_id=campaign["id"]):
        return False
    return bool(rank_client.untrack(tid).get("ok"))


_BACKFILL_AT = {}          # {campaign_id: datetime} — 프로세스 내 5분 스로틀


def backfill_ranks(campaign, throttle_min=5):
    """순위 화면 진입 시 오늘 순위가 없으면 순위 서버에서 직접 가져와 채운다.

    콜백은 재시도해도 끝내 실패할 수 있어서(배포 중이었다거나) 이 경로가 최종 보정이다.
    같은 캠페인을 연달아 열어도 서버를 계속 때리지 않도록 스로틀을 건다.
    """
    from . import rank_client
    tid = campaign.get("track_id")
    if not tid or campaign["status"] not in ("approved", "running", "done"):
        return False
    if campaign_model.daily_rank(campaign["id"], date.today()):
        return False
    last = _BACKFILL_AT.get(campaign["id"])
    if last and (datetime.now() - last).total_seconds() < throttle_min * 60:
        return False
    _BACKFILL_AT[campaign["id"]] = datetime.now()
    r = rank_client.slot_ranks(tid)
    if not r.get("ok"):
        return False
    n = 0
    for row in r.get("ranks") or []:
        try:
            day = date.fromisoformat(str(row.get("date")))
        except (TypeError, ValueError):
            continue
        rk = row.get("rank")
        if rk is None or campaign["start_date"] and day < campaign["start_date"]:
            continue
        if campaign["end_date"] and day > campaign["end_date"]:
            continue
        if campaign_model.daily_rank(campaign["id"], day):
            continue
        apply_rank(campaign["id"], day, int(rk))
        n += 1
    return bool(n)


def apply_rank(campaign_id, day, rank):
    """콜백·폴백이 받은 순위를 기록. 어드민 수동 입력(record_rank)과 같은 자리에 쓴다."""
    c = campaign_model.get(campaign_id)
    if not c or rank is None:
        return None
    prev = campaign_model.daily_rank(campaign_id, day)
    campaign_model.upsert_daily(campaign_id, day, rank, prev["done_qty"] if prev else c["daily_qty"])
    fields = {"rank_now": rank}
    if c["rank_start"] is None:
        fields["rank_start"] = rank
    campaign_model.update(campaign_id, fields)
    return rank


_NOTIFY_TITLES = {
    "review": "결제가 확인되어 검수를 시작합니다", "approved": "검수를 통과했습니다 · 곧 구동 시작",
    "running": "검수를 통과했습니다 · 시작일부터 구동됩니다",
    "rejected": "검수 반려 — 결제 금액이 환불됩니다", "done": "캠페인이 완료되었습니다", "stopped": "캠페인이 중단되었습니다 · 잔여일분 환불",
    "cancelled": "주문이 취소되었습니다",
}


def _notify_status(campaign, frm, to_status, memo):
    from . import notify_service
    title = _NOTIFY_TITLES.get(to_status)
    if not title:
        return
    ntype = "payment" if (frm == "pay_wait" and to_status == "review") else "campaign"
    notify_service.push(campaign["user_id"], ntype, f"[{campaign['order_no']}] {title}",
                        f"/campaign/{campaign['channel']}?open={campaign['id']}")


def reject(campaign, admin_id, reason):
    if not reason:
        raise CampaignError("반려 사유는 필수입니다.")
    campaign_model.update(campaign["id"], {"reject_reason": reason})
    c = transition(campaign, "rejected", admin_id, f"반려 · {reason}")
    payment_service.refund(c, c["paid_amount"] - c["refund_amount"], admin_id, f"반려 · {reason}")
    return campaign_model.get(c["id"])


def stop(campaign, actor_id, reason="사용자 중단 요청"):
    """running -> stopped, refund remaining days pro-rata."""
    if campaign["status"] != "running":
        raise CampaignError("진행 중인 캠페인만 중단할 수 있습니다.")
    today = date.today()
    total_days = days_between(campaign["start_date"], campaign["end_date"])
    elapsed = max(0, min(total_days, (today - campaign["start_date"]).days + 1))
    remaining = total_days - elapsed
    amount = int(round(campaign["paid_amount"] * remaining / total_days)) if remaining > 0 else 0
    c = transition(campaign, "stopped", actor_id, f"{reason} · {elapsed}/{total_days}일 진행 · 잔여 {remaining}일분 환불")
    if amount > 0:
        payment_service.refund(c, amount, actor_id, f"중단 · 잔여 {remaining}일분")
    return campaign_model.get(c["id"])


def cancel(campaign, actor_id, reason="사용자 취소"):
    if campaign["status"] != "pay_wait":
        raise CampaignError("결제 대기 상태에서만 취소할 수 있습니다.")
    payment_service.cancel_pending(campaign, actor_id, reason)
    return transition(campaign, "cancelled", actor_id, reason)


def record_rank(campaign, day, rank, done_qty, actor_id=None):
    if campaign["status"] not in ("running", "approved", "done"):
        raise CampaignError("진행 중인 캠페인만 순위를 입력할 수 있습니다.")
    campaign_model.upsert_daily(campaign["id"], day, rank, done_qty)
    fields = {"rank_now": rank}
    if campaign["rank_start"] is None:
        fields["rank_start"] = rank
    campaign_model.update(campaign["id"], fields)
    return campaign_model.get(campaign["id"])


# ---- progress helpers (templates) -----------------------------------------
def progress(campaign, today=None):
    """{'total', 'elapsed', 'pct', 'label', 'sub', 'cls'} for the manage table progress cell."""
    today = today or date.today()
    total = days_between(campaign["start_date"], campaign["end_date"])
    st = campaign["status"]
    # 승인 직후에도 상태는 running 이지만 시작일 전이면 "MM.DD 시작" 으로 보여준다.
    if st in ("pay_wait", "review", "approved") or (st == "running" and today < campaign["start_date"]):
        return {"cls": "wait", "pct": 0, "label": f"{campaign['start_date']:%m.%d} 시작", "sub": f"{total}일", "total": total, "elapsed": 0}
    if st == "rejected":
        return {"cls": "rej", "pct": 0, "label": (campaign.get("reject_reason") or "반려"), "sub": "전액 환불", "total": total, "elapsed": 0}
    if st == "cancelled":
        return {"cls": "rej", "pct": 0, "label": "취소됨", "sub": "", "total": total, "elapsed": 0}
    elapsed = max(0, min(total, (today - campaign["start_date"]).days + 1))
    if st == "done":
        elapsed = total
    pct = int(elapsed / total * 100) if total else 0
    sub = f"{campaign['end_date']:%m.%d} 종료"
    if st == "stopped":
        sub = f"{total - elapsed}일분 환불" if campaign["refund_amount"] else "중단"
    return {"cls": "done" if st in ("done", "stopped") else "", "pct": pct, "label": f"{elapsed} / {total}일", "sub": sub,
            "total": total, "elapsed": elapsed}


def day_index(campaign, today=None):
    today = today or date.today()
    return max(0, (today - campaign["start_date"]).days + 1)
