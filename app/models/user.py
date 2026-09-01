"""users table."""
from ..db import execute, query_one


def get_by_id(user_id):
    return query_one("SELECT * FROM users WHERE id = %s", [user_id])


def get_by_kakao_id(kakao_id):
    return query_one("SELECT * FROM users WHERE kakao_id = %s", [kakao_id])


def create(kakao_id, nickname, role="user"):
    return execute("INSERT INTO users (kakao_id, nickname, role) VALUES (%s, %s, %s)", [kakao_id, nickname, role])


def get_by_email(email):
    return query_one("SELECT * FROM users WHERE email = %s", [email])


def create_local(email, password_hash, nickname, phone, notify_event=False):
    return execute(
        "INSERT INTO users (email, password_hash, nickname, phone, notify_event) VALUES (%s,%s,%s,%s,%s)",
        [email, password_hash, nickname, phone, 1 if notify_event else 0])


def update_profile(user_id, nickname, phone):
    execute("UPDATE users SET nickname = %s, phone = %s WHERE id = %s", [nickname, phone, user_id])


def update_biz(user_id, biz_name, biz_no, biz_type, biz_item, biz_email):
    execute(
        "UPDATE users SET biz_name = %s, biz_no = %s, biz_type = %s, biz_item = %s, biz_email = %s WHERE id = %s",
        [biz_name or None, biz_no or None, biz_type or None, biz_item or None, biz_email or None, user_id],
    )


NOTIFY_FIELDS = ("notify_campaign", "notify_comment", "notify_event")


def update_notify(user_id, field, value):
    if field not in NOTIFY_FIELDS:
        raise ValueError("invalid notify field")
    execute(f"UPDATE users SET {field} = %s WHERE id = %s", [1 if value else 0, user_id])


def update_grade(user_id, grade):
    execute("UPDATE users SET grade = %s WHERE id = %s", [grade, user_id])


def suspend(user_id):
    execute("UPDATE users SET status = 'suspended' WHERE id = %s", [user_id])


# ---- admin ---------------------------------------------------------------
def list_admin(q=None, status=None, page=1, per_page=20):
    from ..db import query, query_one  # local import keeps top clean
    where, params = ["1=1"], []
    if q:
        where.append("(nickname LIKE %s OR phone LIKE %s OR biz_name LIKE %s)"); params += [f"%{q}%"] * 3
    if status:
        where.append("status = %s"); params.append(status)
    w = " AND ".join(where)
    rows = query(
        f"""SELECT u.*, (SELECT COUNT(*) FROM campaigns c WHERE c.user_id = u.id) AS campaign_cnt,
                   (SELECT COALESCE(SUM(paid_amount - refund_amount), 0) FROM campaigns c WHERE c.user_id = u.id AND paid_at IS NOT NULL) AS paid_total
            FROM users u WHERE {w} ORDER BY u.created_at DESC, u.id DESC LIMIT %s OFFSET %s""",
        params + [per_page, (page - 1) * per_page])
    total = query_one(f"SELECT COUNT(*) AS n FROM users WHERE {w}", params)["n"]
    return rows, total


def set_status(user_id, status):
    execute("UPDATE users SET status = %s WHERE id = %s", [status, user_id])


def count_by_status():
    from ..db import query
    return {r["status"]: r["n"] for r in query("SELECT status, COUNT(*) AS n FROM users GROUP BY status")}
