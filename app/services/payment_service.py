"""Single entry point for payments and refunds.

create()          -> payments row (pending) for a newly created campaign
confirm_card()    -> PG approve (adapter) -> paid -> campaign review
confirm_bank()    -> operator marks transfer received -> paid -> campaign review
refund()          -> full/partial cancel via PG (card) or manual (bank) -> refunded/partial_refund
expire_unpaid()   -> pending bank transfers past due -> expired -> campaign cancelled

Every change also writes a status_log row so the campaign drawer timeline shows payment history.
"""
from datetime import datetime, timedelta

from ..constants import BANK_DUE_DAYS
from ..models import campaign as campaign_model
from ..models import payment as payment_model
from .pg import PGError, get_adapter


class PaymentError(Exception):
    pass


def _norm(s):
    return "".join((s or "").split())


def bank_due_at(now=None):
    """Due = N business days later (settings.bank_due_days, default constant), 23:59."""
    from ..models import settings as settings_model
    try:
        days = int(settings_model.get_all().get("bank_due_days") or BANK_DUE_DAYS)
    except (ValueError, TypeError):
        days = BANK_DUE_DAYS
    d = (now or datetime.now()).date()
    added = 0
    while added < days:
        d += timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return datetime.combine(d, datetime.max.time()).replace(microsecond=0)


def create(campaign, user, method, depositor=None):
    if method not in ("card", "bank"):
        raise PaymentError("invalid payment method")
    if method == "bank":
        depositor = (depositor or "").strip()
        if not depositor:
            raise PaymentError("입금자명을 입력해주세요.")
        mismatch = _norm(depositor) != _norm(user["nickname"]) and _norm(depositor) != _norm(user.get("biz_name"))
        pid = payment_model.insert(campaign["id"], user["id"], "bank", campaign["paid_amount"],
                                   depositor=depositor, name_mismatch=mismatch, bank_due_at=bank_due_at())
        campaign_model.add_log(campaign["id"], None, "pay_wait", user["id"],
                               f"무통장 입금 대기 · {campaign['paid_amount']:,}원 · 입금자 {depositor}")
    else:
        pid = payment_model.insert(campaign["id"], user["id"], "card", campaign["paid_amount"],
                                   pg_provider=get_adapter().name)
        campaign_model.add_log(campaign["id"], None, "pay_wait", user["id"], f"카드 결제 요청 · {campaign['paid_amount']:,}원")
    return payment_model.get(pid)


def _mark_paid(payment, tid, actor_id, memo):
    from . import campaign_service  # late import to avoid cycle
    payment_model.update(payment["id"], {"status": "paid", "pg_tid": tid, "paid_at": datetime.now()})
    campaign_model.update(payment["campaign_id"], {"paid_at": datetime.now()})
    campaign = campaign_model.get(payment["campaign_id"])
    return campaign_service.transition(campaign, "review", actor_id, memo)


def confirm_card(campaign, actor_id, token=None):
    payment = payment_model.get_for_campaign(campaign["id"], for_update=True)
    if not payment or payment["method"] != "card":
        raise PaymentError("카드 결제 건이 아닙니다.")
    if payment["status"] == "paid":
        return campaign  # idempotent
    if payment["status"] != "pending":
        raise PaymentError(f"결제 상태가 올바르지 않습니다: {payment['status']}")
    try:
        res = get_adapter().confirm(payment, token)
    except PGError as e:
        raise PaymentError(str(e))
    if not res.ok:
        raise PaymentError(res.message or "결제 승인 실패")
    return _mark_paid(payment, res.tid, actor_id, f"카드 결제 승인 · {payment['amount']:,}원 · {res.tid}")


def confirm_bank(campaign, admin_id, memo=None):
    payment = payment_model.get_for_campaign(campaign["id"], for_update=True)
    if not payment or payment["method"] != "bank":
        raise PaymentError("무통장 결제 건이 아닙니다.")
    if payment["status"] != "pending":
        raise PaymentError(f"결제 상태가 올바르지 않습니다: {payment['status']}")
    return _mark_paid(payment, None, admin_id, memo or f"입금 확인 · {payment['amount']:,}원 · 입금자 {payment['depositor']}")


def refund(campaign, amount, actor_id, reason):
    """Refund `amount` (<= remaining). Returns updated payment."""
    payment = payment_model.get_for_campaign(campaign["id"], for_update=True)
    if not payment or payment["status"] not in ("paid", "partial_refund"):
        raise PaymentError("환불 가능한 결제가 없습니다.")
    remaining = payment["amount"] - payment["refund_amount"]
    amount = int(amount)
    if amount <= 0 or amount > remaining:
        raise PaymentError(f"환불 금액이 올바르지 않습니다 (가능 {remaining:,}원)")
    if payment["method"] == "card":
        try:
            res = get_adapter().cancel(payment, amount, reason)
        except PGError as e:
            raise PaymentError(str(e))
        if not res.ok:
            raise PaymentError(res.message or "PG 취소 실패")
    new_refund = payment["refund_amount"] + amount
    status = "refunded" if new_refund >= payment["amount"] else "partial_refund"
    payment_model.update(payment["id"], {"status": status, "refund_amount": new_refund, "refunded_at": datetime.now(),
                                         "memo": reason[:200] if reason else None})
    campaign_model.update(campaign["id"], {"refund_amount": new_refund})
    kind = "전액 환불" if status == "refunded" else "부분 환불"
    campaign_model.add_log(campaign["id"], campaign["status"], campaign["status"], actor_id,
                           f"{kind} {amount:,}원 ({'카드 취소' if payment['method'] == 'card' else '계좌 환불'}) · {reason}")
    return payment_model.get(payment["id"])


def cancel_pending(campaign, actor_id, reason):
    """User cancels an unpaid order (bank pending or card never confirmed)."""
    payment = payment_model.get_for_campaign(campaign["id"], for_update=True)
    if payment and payment["status"] == "pending":
        payment_model.update(payment["id"], {"status": "cancelled", "memo": reason[:200]})
    campaign_model.add_log(campaign["id"], campaign["status"], campaign["status"], actor_id, f"결제 취소 · {reason}")


def expire_unpaid(actor_id=None):
    """Batch/admin: expire bank transfers past due and cancel their campaigns. Returns count."""
    from . import campaign_service
    n = 0
    for p in payment_model.list_expired_pending():
        payment_model.update(p["id"], {"status": "expired"})
        campaign = campaign_model.get(p["campaign_id"])
        if campaign and campaign["status"] == "pay_wait":
            campaign_service.transition(campaign, "cancelled", actor_id, "입금 기한 만료 · 자동 취소")
        n += 1
    return n
