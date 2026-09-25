"""users table."""
from ..db import execute, query, query_one


def get_by_id(user_id):
    return query_one("SELECT * FROM users WHERE id = %s", [user_id])


def get_by_kakao_id(kakao_id):
    return query_one("SELECT * FROM users WHERE kakao_id = %s", [kakao_id])


def create(kakao_id, nickname, role="user"):
    return execute("INSERT INTO users (kakao_id, nickname, role) VALUES (%s, %s, %s)", [kakao_id, nickname, role])


def get_by_email(email):
    return query_one("SELECT * FROM users WHERE email = %s", [email])


def get_by_login(login):
    """운영자 로그인: 아이디(username) 또는 이메일 어느 쪽이든 받는다."""
    return query_one("SELECT * FROM users WHERE username = %s OR email = %s LIMIT 1", [login, login])


def username_taken(username, exclude_id=None):
    sql, p = "SELECT id FROM users WHERE username = %s", [username]
    if exclude_id:
        sql += " AND id <> %s"
        p.append(exclude_id)
    return query_one(sql, p) is not None


def set_username(user_id, username):
    execute("UPDATE users SET username = %s WHERE id = %s", [username or None, user_id])


def create_local(email, password_hash, nickname, phone, notify_event=False):
    return execute(
        "INSERT INTO users (email, password_hash, nickname, phone, notify_event) VALUES (%s,%s,%s,%s,%s)",
        [email, password_hash, nickname, phone, 1 if notify_event else 0])


def update_profile(user_id, nickname, phone):
    execute("UPDATE users SET nickname = %s, phone = %s WHERE id = %s", [nickname, phone, user_id])


def list_brief():
    """id/nickname/email/balance for admin dropdowns (active users)."""
    return query("SELECT id, nickname, email, credit_balance FROM users WHERE status = 'active' ORDER BY id")


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
def login_id(email=None, username=None, kakao_id=None, user_id=None):
    """회원의 로그인 아이디 한 줄 표기 — 화면과 엑셀이 같은 문자열을 쓰도록 여기서만 만든다.

    운영자는 username, 이메일 가입은 email, 카카오 가입은 kakao:<id>. 아무것도 없으면 #번호.
    """
    if username:
        return username
    if email:
        return email
    if kakao_id:
        return f"kakao:{kakao_id}"
    return f"#{user_id}" if user_id else "-"


def list_admin(q=None, status=None, page=1, per_page=20):
    from ..db import query, query_one  # local import keeps top clean
    where, params = ["1=1"], []
    if q:
        # 아이디로도 찾을 수 있어야 한다 — 어드민이 보는 값이 곧 검색어다.
        where.append("(nickname LIKE %s OR phone LIKE %s OR biz_name LIKE %s "
                     "OR email LIKE %s OR username LIKE %s OR kakao_id LIKE %s)")
        params += [f"%{q}%"] * 6
    if status:
        where.append("status = %s"); params.append(status)
    w = " AND ".join(where)
    rows = query(
        f"""SELECT u.*, (SELECT COUNT(*) FROM campaigns c WHERE c.user_id = u.id) AS campaign_cnt,
                   (SELECT COALESCE(SUM(paid_amount - refund_amount), 0) FROM campaigns c WHERE c.user_id = u.id AND paid_at IS NOT NULL) AS paid_total
            FROM users u WHERE {w} ORDER BY u.created_at DESC, u.id DESC LIMIT %s OFFSET %s""",
        params + [per_page, (page - 1) * per_page])
    for r in rows:
        r["login_id"] = login_id(r.get("email"), r.get("username"), r.get("kakao_id"), r["id"])
        r["signup_via"] = ("운영자 아이디" if r.get("username") else "이메일 가입" if r.get("email")
                           else "카카오 가입" if r.get("kakao_id") else "경로 미확인")
    total = query_one(f"SELECT COUNT(*) AS n FROM users WHERE {w}", params)["n"]
    return rows, total


def set_status(user_id, status):
    execute("UPDATE users SET status = %s WHERE id = %s", [status, user_id])


def count_by_status():
    from ..db import query
    return {r["status"]: r["n"] for r in query("SELECT status, COUNT(*) AS n FROM users GROUP BY status")}


# ---- 운영자 관리 (2026-09-25) ---------------------------------------------
def touch_login(user_id):
    execute("UPDATE users SET last_login_at = NOW() WHERE id = %s", [user_id])


def list_admins():
    return query(
        """SELECT id, email, username, nickname, status, last_login_at, created_at,
                  (password_hash IS NOT NULL) AS has_pw
           FROM users WHERE role = 'admin' ORDER BY id""")


def active_admin_count():
    return query_one("SELECT COUNT(*) AS n FROM users WHERE role = 'admin' AND status = 'active'")["n"]


def create_admin(email, username, password_hash, nickname):
    return execute(
        """INSERT INTO users (email, username, password_hash, nickname, role, status, notify_event)
           VALUES (%s,%s,%s,%s,'admin','active',0)""", [email or None, username or None, password_hash, nickname])


def set_password(user_id, password_hash):
    execute("UPDATE users SET password_hash = %s WHERE id = %s", [password_hash, user_id])


def set_role(user_id, role):
    """role 은 users.role ENUM('user','admin'). 사업자 등급(grade)과 다른 축이다."""
    if role not in ("user", "admin"):
        raise ValueError(role)
    execute("UPDATE users SET role = %s WHERE id = %s", [role, user_id])


def deletable_blockers(user_id):
    """회원 삭제를 막는 사유 목록. 비어 있으면 지워도 안전하다."""
    out = []
    n = query_one("SELECT COUNT(*) AS n FROM campaigns WHERE user_id = %s", [user_id])["n"]
    if n:
        out.append(f"캠페인 {n}건")
    n = query_one("SELECT COUNT(*) AS n FROM credit_ledger WHERE user_id = %s", [user_id])["n"]
    if n:
        out.append(f"크레딧 내역 {n}건")
    n = query_one("SELECT COUNT(*) AS n FROM posts WHERE user_id = %s", [user_id])["n"]
    if n:
        out.append(f"게시글 {n}건")
    bal = query_one("SELECT credit_balance FROM users WHERE id = %s", [user_id])
    if bal and bal["credit_balance"]:
        out.append(f"잔여 크레딧 {bal['credit_balance']:,}원")
    return out


def purge(user_id):
    """딸린 흔적까지 지운다. deletable_blockers 가 빈 경우에만 부를 것."""
    for sql in ("DELETE FROM comments WHERE user_id = %s",
                "DELETE FROM post_likes WHERE user_id = %s",
                "DELETE FROM reports WHERE user_id = %s",
                "DELETE FROM notifications WHERE user_id = %s",
                "DELETE FROM store_slots WHERE user_id = %s",
                "DELETE FROM charge_requests WHERE user_id = %s",
                "DELETE FROM series_reads WHERE user_id = %s",
                "DELETE FROM users WHERE id = %s"):
        execute(sql, [user_id])
