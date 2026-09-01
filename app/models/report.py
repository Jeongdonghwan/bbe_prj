"""reports + blind handling for posts/comments (admin view)."""
from ..db import execute, query, query_one


def list_reported(target_type=None, page=1, per_page=20):
    """Posts/comments with report_cnt >= 1 (posts) or reports rows (comments)."""
    rows = []
    if target_type in (None, "post"):
        rows += query(
            """SELECT 'post' AS target_type, p.id AS target_id, p.title AS text, p.report_cnt AS cnt, p.is_blind, p.user_id,
                      b.name AS board_name, p.created_at,
                      (SELECT GROUP_CONCAT(DISTINCT reason SEPARATOR ' / ') FROM reports r WHERE r.target_type='post' AND r.target_id=p.id) AS reasons
               FROM posts p JOIN boards b ON b.id = p.board_id WHERE p.report_cnt >= 1 OR p.is_blind = 1""")
    if target_type in (None, "comment"):
        rows += query(
            """SELECT 'comment' AS target_type, c.id AS target_id, LEFT(c.body, 80) AS text,
                      (SELECT COUNT(*) FROM reports r WHERE r.target_type='comment' AND r.target_id=c.id) AS cnt, c.is_blind, c.user_id,
                      b.name AS board_name, c.created_at,
                      (SELECT GROUP_CONCAT(DISTINCT reason SEPARATOR ' / ') FROM reports r WHERE r.target_type='comment' AND r.target_id=c.id) AS reasons
               FROM comments c JOIN posts p ON p.id = c.post_id JOIN boards b ON b.id = p.board_id
               WHERE c.is_blind = 1 OR EXISTS (SELECT 1 FROM reports r WHERE r.target_type='comment' AND r.target_id=c.id)""")
    rows.sort(key=lambda r: (-(r["cnt"] or 0), r["created_at"]), reverse=False)
    rows.sort(key=lambda r: -(r["cnt"] or 0))
    total = len(rows)
    return rows[(page - 1) * per_page: page * per_page], total


def set_blind(target_type, target_id, blind):
    table = "posts" if target_type == "post" else "comments"
    execute(f"UPDATE {table} SET is_blind = %s WHERE id = %s", [1 if blind else 0, target_id])


def count_reported():
    a = query_one("SELECT COUNT(*) AS n FROM posts WHERE report_cnt >= 1 AND is_blind = 0")["n"]
    b = query_one("SELECT COUNT(DISTINCT target_id) AS n FROM reports WHERE target_type = 'comment'")["n"]
    return a + b
