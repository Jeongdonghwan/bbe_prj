"""In-app notifications (no KakaoTalk / SMS sending — P5). push() respects user notify_* toggles."""
from ..db import execute, query, query_one

TYPE_FIELD = {"comment": "notify_comment", "answer": "notify_comment", "proposal": None, "campaign": "notify_campaign",
              "payment": "notify_campaign", "agency": None, "notice": "notify_event"}


def push(user_id, ntype, title, link=None):
    if not user_id:
        return None
    field = TYPE_FIELD.get(ntype)
    if field:
        u = query_one(f"SELECT {field} AS on_ FROM users WHERE id = %s", [user_id])
        if u and not u["on_"]:
            return None
    return execute("INSERT INTO notifications (user_id, type, title, link) VALUES (%s,%s,%s,%s)", [user_id, ntype, title[:200], link])


def unread_count(user_id):
    return query_one("SELECT COUNT(*) AS n FROM notifications WHERE user_id = %s AND is_read = 0", [user_id])["n"]


def list_user(user_id, page=1, per_page=20):
    rows = query("SELECT * FROM notifications WHERE user_id = %s ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
                 [user_id, per_page, (page - 1) * per_page])
    total = query_one("SELECT COUNT(*) AS n FROM notifications WHERE user_id = %s", [user_id])["n"]
    return rows, total


def mark_all_read(user_id):
    execute("UPDATE notifications SET is_read = 1 WHERE user_id = %s AND is_read = 0", [user_id])


def mark_read(user_id, notification_id):
    execute("UPDATE notifications SET is_read = 1 WHERE user_id = %s AND id = %s", [user_id, notification_id])
