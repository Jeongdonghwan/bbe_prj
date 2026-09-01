"""Campaign orders: quote, create (campaign + payment in one transaction), transition (state table + status_log)."""
import math
import secrets
from datetime import date, datetime

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
    return campaign_model.get(campaign["id"])


_NOTIFY_TITLES = {
    "review": "결제가 확인되어 검수를 시작합니다", "approved": "검수를 통과했습니다 · 곧 구동 시작", "running": "캠페인 구동이 시작되었습니다",
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
    if st in ("pay_wait", "review", "approved"):
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
