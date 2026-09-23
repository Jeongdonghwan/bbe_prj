"""credit_ledger / charge_requests tables + users.credit_balance.

Balance changes go through apply() only, which locks the user row so
concurrent spends cannot overdraw.
"""
from ..db import execute, query, query_one


class CreditError(Exception):
    pass


def balance(user_id):
    row = query_one("SELECT credit_balance FROM users WHERE id = %s", [user_id])
    return row["credit_balance"] if row else 0


def apply(user_id, type_, amount, ref_type=None, ref_id=None, memo=None, actor_id=None):
    """Atomically add `amount` (signed) to the user's balance and write a ledger row."""
    amount = int(amount)
    if amount == 0:
        raise CreditError("금액이 0원입니다.")
    if amount < 0:
        affected = execute(
            "UPDATE users SET credit_balance = credit_balance + %s WHERE id = %s AND credit_balance >= %s",
            [amount, user_id, -amount], rowcount=True)
        if not affected:
            raise CreditError("크레딧 잔액이 부족합니다.")
    else:
        execute("UPDATE users SET credit_balance = credit_balance + %s WHERE id = %s", [amount, user_id])
    bal = balance(user_id)
    execute(
        """INSERT INTO credit_ledger (user_id, type, amount, balance_after, ref_type, ref_id, memo, actor_id)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        [user_id, type_, amount, bal, ref_type, ref_id, (memo or "")[:200] or None, actor_id])
    return bal


def ledger(user_id, page=1, per_page=20):
    rows = query(
        "SELECT * FROM credit_ledger WHERE user_id = %s ORDER BY id DESC LIMIT %s OFFSET %s",
        [user_id, per_page, (page - 1) * per_page])
    total = query_one("SELECT COUNT(*) AS n FROM credit_ledger WHERE user_id = %s", [user_id])["n"]
    return rows, total


def ledger_recent(limit=20):
    return query(
        """SELECT l.*, u.nickname, u.email FROM credit_ledger l JOIN users u ON u.id = l.user_id
           ORDER BY l.id DESC LIMIT %s""", [limit])


# ---- charge requests ------------------------------------------------------
def create_request(user_id, amount, vat, total, depositor, tax_invoice, biz_snapshot):
    return execute(
        """INSERT INTO charge_requests (user_id, amount, vat, total, depositor, tax_invoice, biz_snapshot)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        [user_id, amount, vat, total, depositor[:40], 1 if tax_invoice else 0, (biz_snapshot or "")[:200] or None])


def get_request(req_id, for_update=False):
    return query_one(f"SELECT * FROM charge_requests WHERE id = %s{' FOR UPDATE' if for_update else ''}", [req_id])


def list_user_requests(user_id, status=None, page=1, per_page=20):
    where, params = "user_id = %s", [user_id]
    if status:
        where += " AND status = %s"
        params.append(status)
    rows = query(f"SELECT * FROM charge_requests WHERE {where} ORDER BY id DESC LIMIT %s OFFSET %s",
                 params + [per_page, (page - 1) * per_page])
    total = query_one(f"SELECT COUNT(*) AS n FROM charge_requests WHERE {where}", params)["n"]
    return rows, total


def list_admin_requests(status=None, page=1, per_page=20):
    where, params = "1=1", []
    if status:
        where, params = "r.status = %s", [status]
    rows = query(
        f"""SELECT r.*, u.nickname, u.email, u.credit_balance FROM charge_requests r JOIN users u ON u.id = r.user_id
            WHERE {where} ORDER BY r.status = 'pending' DESC, r.id DESC LIMIT %s OFFSET %s""",
        params + [per_page, (page - 1) * per_page])
    total = query_one(f"SELECT COUNT(*) AS n FROM charge_requests r WHERE {where}", params)["n"]
    return rows, total


def set_request_status(req_id, status, admin_id, reason=None):
    execute(
        "UPDATE charge_requests SET status = %s, reject_reason = %s, processed_by = %s, processed_at = NOW() WHERE id = %s",
        [status, (reason or "")[:200] or None, admin_id, req_id])


def pending_count():
    return query_one("SELECT COUNT(*) AS n FROM charge_requests WHERE status = 'pending'")["n"]


def campaign_refunds(campaign_ids):
    """환불 원장 — 정산 시트에서 환불을 발생 주(週)에 −로 넣기 위해."""
    if not campaign_ids:
        return []
    ph = ",".join(["%s"] * len(campaign_ids))
    return query(
        f"""SELECT ref_id AS campaign_id, amount, memo, created_at FROM credit_ledger
            WHERE type = 'refund' AND ref_type = 'campaign' AND ref_id IN ({ph}) ORDER BY created_at""",
        list(campaign_ids))
