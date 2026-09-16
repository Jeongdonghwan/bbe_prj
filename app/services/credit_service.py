"""Prepaid credit (2026-09-16, replaces per-order card payment).

Flow: user files a bank-transfer charge request (amount + 10% VAT = deposit total)
→ admin approves (credits the supply amount) or rejects. Admin can also adjust
any balance directly. Campaigns spend credit at face value (no VAT on spend).
All balance changes go through models/credit.apply().
"""
from ..constants import VAT_RATE
from ..models import credit as credit_model
from .notify_service import push

CreditError = credit_model.CreditError

MIN_CHARGE = 10_000
CHARGE_UNIT = 1_000


def quote_charge(amount):
    amount = int(amount)
    vat = int(round(amount * VAT_RATE))
    return {"amount": amount, "vat": vat, "total": amount + vat}


def request_charge(user, amount, depositor, tax_invoice=False, biz_snapshot=None):
    amount = int(amount)
    if amount < MIN_CHARGE:
        raise CreditError(f"최소 충전 금액은 {MIN_CHARGE:,}원입니다.")
    if amount % CHARGE_UNIT:
        raise CreditError(f"{CHARGE_UNIT:,}원 단위로 입력해주세요.")
    depositor = (depositor or "").strip()
    if not depositor:
        raise CreditError("입금자명을 입력해주세요.")
    q = quote_charge(amount)
    return credit_model.create_request(user["id"], q["amount"], q["vat"], q["total"],
                                       depositor, tax_invoice, biz_snapshot)


def approve_request(req_id, admin_id, memo=None):
    r = credit_model.get_request(req_id, for_update=True)
    if not r or r["status"] != "pending":
        raise CreditError("대기 중인 충전 요청이 아닙니다.")
    credit_model.set_request_status(req_id, "approved", admin_id)
    bal = credit_model.apply(r["user_id"], "charge", r["amount"], "charge_request", req_id,
                             memo or f"충전 승인 · 입금 {r['total']:,}원", admin_id)
    push(r["user_id"], "credit", f"크레딧 {r['amount']:,}원이 충전되었습니다. (잔액 {bal:,}원)", "/my")
    return bal


def reject_request(req_id, admin_id, reason):
    r = credit_model.get_request(req_id, for_update=True)
    if not r or r["status"] != "pending":
        raise CreditError("대기 중인 충전 요청이 아닙니다.")
    credit_model.set_request_status(req_id, "rejected", admin_id, reason)
    push(r["user_id"], "credit", f"충전 요청이 거절되었습니다: {reason}", "/my")


def adjust(user_id, amount, admin_id, memo):
    """Admin direct top-up (+) or deduction (-)."""
    memo = (memo or "").strip() or "관리자 조정"
    bal = credit_model.apply(user_id, "adjust", int(amount), "admin", None, memo, admin_id)
    if int(amount) > 0:
        push(user_id, "credit", f"크레딧 {int(amount):,}원이 충전되었습니다. (잔액 {bal:,}원)", "/my")
    return bal


def spend(user_id, amount, campaign_id, memo):
    return credit_model.apply(user_id, "spend", -int(amount), "campaign", campaign_id, memo)


def refund(user_id, amount, campaign_id, memo):
    return credit_model.apply(user_id, "refund", int(amount), "campaign", campaign_id, memo)
