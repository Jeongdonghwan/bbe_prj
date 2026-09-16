"""/credit — prepaid credit charge wizard (bank transfer -> admin approval)."""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..services import credit_service
from .auth import login_required
from .campaign import bank_info

bp = Blueprint("credit", __name__, url_prefix="/credit")


@bp.route("/charge", methods=["GET", "POST"])
@login_required
def charge():
    if request.method == "POST":
        amount = request.form.get("amount", type=int) or 0
        depositor = request.form.get("depositor", "")
        tax = request.form.get("tax_invoice") == "1"
        biz_snapshot = None
        if tax:
            name = (request.form.get("biz_name") or g.user["biz_name"] or "").strip()
            no = (request.form.get("biz_no") or g.user["biz_no"] or "").strip()
            email = (request.form.get("biz_email") or g.user["biz_email"] or "").strip()
            if not name or not no:
                flash("세금계산서 발행에는 상호와 사업자번호가 필요합니다.")
                return redirect(url_for("credit.charge"))
            biz_snapshot = f"{name} / {no} / {email or '-'}"
            if request.form.get("biz_name"):  # newly typed -> keep on profile too
                from ..models import user as user_model
                user_model.update_biz(g.user["id"], name[:60], no[:20],
                                      g.user.get("biz_type") or "", g.user.get("biz_item") or "", email[:120])
        try:
            credit_service.request_charge(g.user, amount, depositor, tax, biz_snapshot)
        except credit_service.CreditError as e:
            flash(str(e))
            return redirect(url_for("credit.charge"))
        flash("충전 요청을 접수했습니다. 입금 확인 후 크레딧이 지급됩니다.")
        return redirect(url_for("my.index"))
    return render_template("credit/charge.html", bank=bank_info(), balance=g.user["credit_balance"],
                           min_charge=credit_service.MIN_CHARGE)
