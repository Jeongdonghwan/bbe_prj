"""payments table. Status changes only via services.payment_service."""
from ..db import execute, query, query_one


def insert(campaign_id, user_id, method, amount, depositor=None, name_mismatch=False, bank_due_at=None, pg_provider=None):
    return execute(
        """INSERT INTO payments (campaign_id, user_id, method, amount, depositor, name_mismatch, bank_due_at, pg_provider)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        [campaign_id, user_id, method, amount, depositor, 1 if name_mismatch else 0, bank_due_at, pg_provider])


def get(payment_id):
    return query_one("SELECT * FROM payments WHERE id = %s", [payment_id])


def get_for_campaign(campaign_id, for_update=False):
    return query_one(
        "SELECT * FROM payments WHERE campaign_id = %s ORDER BY id DESC LIMIT 1" + (" FOR UPDATE" if for_update else ""),
        [campaign_id])


def update(payment_id, fields):
    sets = ", ".join(f"{k} = %s" for k in fields)
    execute(f"UPDATE payments SET {sets} WHERE id = %s", [*fields.values(), payment_id])


def list_expired_pending():
    return query("SELECT * FROM payments WHERE method = 'bank' AND status = 'pending' AND bank_due_at < NOW()")


def list_admin(status=None, method=None, page=1, per_page=20):
    where, params = ["1=1"], []
    if status:
        where.append("p.status = %s"); params.append(status)
    if method:
        where.append("p.method = %s"); params.append(method)
    w = " AND ".join(where)
    rows = query(
        f"""SELECT p.*, c.order_no, c.channel, c.biz_name, c.status AS campaign_status, u.nickname
            FROM payments p JOIN campaigns c ON c.id = p.campaign_id JOIN users u ON u.id = p.user_id
            WHERE {w} ORDER BY p.created_at DESC, p.id DESC LIMIT %s OFFSET %s""",
        params + [per_page, (page - 1) * per_page])
    total = query_one(f"SELECT COUNT(*) AS n FROM payments p WHERE {w}", params)["n"]
    return rows, total


def pending_bank_summary():
    return query_one(
        "SELECT COUNT(*) AS n, COALESCE(SUM(amount), 0) AS total FROM payments WHERE method = 'bank' AND status = 'pending'")
