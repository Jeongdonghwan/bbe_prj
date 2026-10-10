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


def user_summary(user_id):
    """회원 크레딧 요약 — 승인된 충전 합계·건수, 대기 건수, 원장 구분별 합계."""
    req = query_one("""SELECT COALESCE(SUM(CASE WHEN status='approved' THEN amount END), 0) AS charged,
                              COALESCE(SUM(CASE WHEN status='approved' THEN total END), 0) AS paid,
                              SUM(status='approved') AS approved_n, SUM(status='pending') AS pending_n,
                              SUM(status='rejected') AS rejected_n
                       FROM charge_requests WHERE user_id = %s""", [user_id])
    led = {r["type"]: r["s"] for r in query(
        "SELECT type, COALESCE(SUM(amount), 0) AS s FROM credit_ledger WHERE user_id = %s GROUP BY type", [user_id])}
    return {**req, "approved_n": req["approved_n"] or 0, "pending_n": req["pending_n"] or 0,
            "rejected_n": req["rejected_n"] or 0, "ledger": led}


def ledger_recent(limit=20):
    return query(
        """SELECT l.*, u.nickname, u.email FROM credit_ledger l JOIN users u ON u.id = l.user_id
           ORDER BY l.id DESC LIMIT %s""", [limit])


def ledger_all(type_=None, page=1, per_page=20):
    """전체 크레딧 원장 — 어드민 결제 내역의 열람용. type_ 은 charge/spend/refund/adjust."""
    where, params = "1=1", []
    if type_:
        where, params = "l.type = %s", [type_]
    rows = query(
        f"""SELECT l.*, u.nickname, u.email, u.username, u.kakao_id, u.biz_name
            FROM credit_ledger l JOIN users u ON u.id = l.user_id
            WHERE {where} ORDER BY l.id DESC LIMIT %s OFFSET %s""",
        params + [per_page, (page - 1) * per_page])
    total = query_one(f"SELECT COUNT(*) AS n FROM credit_ledger l WHERE {where}", params)["n"]
    return rows, total


def processed_requests(page=1, per_page=20):
    """처리가 끝난 충전 요청(승인·거절) — 결제 내역에 남는 기록."""
    rows = query(
        """SELECT r.*, u.nickname, u.email, u.username, u.kakao_id, u.biz_name, a.nickname AS admin_nick
           FROM charge_requests r JOIN users u ON u.id = r.user_id
           LEFT JOIN users a ON a.id = r.processed_by
           WHERE r.status <> 'pending' ORDER BY r.processed_at DESC, r.id DESC LIMIT %s OFFSET %s""",
        [per_page, (page - 1) * per_page])
    total = query_one("SELECT COUNT(*) AS n FROM charge_requests WHERE status <> 'pending'")["n"]
    return rows, total


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


def list_admin_requests(status=None, page=1, per_page=20, stale_days=None, user_id=None, order=None):
    """stale_days: 입금 기한이 지나도록 입금이 안 된 대기 건만 (운영자가 직접 거절하도록 모아 보여준다).
    user_id: 회원 한 명의 충전 이력만."""
    where, params = "1=1", []
    if stale_days:
        where = "r.status = 'pending' AND r.created_at < DATE_SUB(NOW(), INTERVAL %s DAY)"
        params = [int(stale_days)]
    elif status:
        where, params = "r.status = %s", [status]
    if user_id:
        where += " AND r.user_id = %s"
        params.append(int(user_id))
    rows = query(
        f"""SELECT r.*, u.nickname, u.email, u.credit_balance FROM charge_requests r JOIN users u ON u.id = r.user_id
            WHERE {where} ORDER BY {order + ', ' if order else ''}r.status = 'pending' DESC, r.id DESC LIMIT %s OFFSET %s""",
        params + [per_page, (page - 1) * per_page])
    total = query_one(f"SELECT COUNT(*) AS n FROM charge_requests r WHERE {where}", params)["n"]
    return rows, total


def set_request_status(req_id, status, admin_id, reason=None):
    execute(
        "UPDATE charge_requests SET status = %s, reject_reason = %s, processed_by = %s, processed_at = NOW() WHERE id = %s",
        [status, (reason or "")[:200] or None, admin_id, req_id])


def pending_count():
    return query_one("SELECT COUNT(*) AS n FROM charge_requests WHERE status = 'pending'")["n"]


def stale_pending_count(days):
    """입금 기한이 지나도록 대기 중인 충전 요청 수 — 자동 거절은 하지 않는다(늦게 입금하는 회원이 있다)."""
    return query_one(
        "SELECT COUNT(*) AS n FROM charge_requests WHERE status = 'pending' "
        "AND created_at < DATE_SUB(NOW(), INTERVAL %s DAY)", [int(days)])["n"]


def campaign_refunds(campaign_ids):
    """환불 원장 — 정산 시트에서 환불을 발생 주(週)에 −로 넣기 위해."""
    if not campaign_ids:
        return []
    ph = ",".join(["%s"] * len(campaign_ids))
    return query(
        f"""SELECT ref_id AS campaign_id, amount, memo, created_at FROM credit_ledger
            WHERE type = 'refund' AND ref_type = 'campaign' AND ref_id IN ({ph}) ORDER BY created_at""",
        list(campaign_ids))
