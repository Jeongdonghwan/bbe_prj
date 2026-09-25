"""posts / comments / post_likes / reports (community boards anon, qna). Lists never expose body."""
from ..db import execute, query, query_one

BLIND_THRESHOLD = 3

LIST_COLS = """p.id, p.board_id, p.user_id, p.anon_nick, p.channel_tag, p.title, LEFT(p.body, 300) AS body, p.image_url, p.is_solved, p.views, p.likes,
               p.report_cnt, p.is_blind, p.created_at,
               (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id AND c.is_blind = 0) AS comment_cnt,
               (SELECT COUNT(*) FROM comments c JOIN users u ON u.id = c.user_id WHERE c.post_id = p.id AND u.role = 'admin' AND c.is_blind = 0) AS admin_cnt"""


def board_id(slug):
    r = query_one("SELECT id FROM boards WHERE slug = %s", [slug])
    return r["id"] if r else None


def latest_anon_posts(limit=5):
    """Dashboard widget: title + anon nick + comment count only."""
    return query(
        f"""SELECT {LIST_COLS} FROM posts p JOIN boards b ON b.id = p.board_id
            WHERE b.slug = 'anon' AND p.is_blind = 0 ORDER BY p.created_at DESC, p.id DESC LIMIT %s""", [limit])


def _filters(slug, tag, q, extra=None):
    where, params = ["b.slug = %s", "p.is_blind = 0"], [slug]
    if tag:
        where.append("p.channel_tag = %s"); params.append(tag)
    if q:
        where.append("p.title LIKE %s"); params.append(f"%{q}%")
    if extra:
        where.append(extra)
    return " AND ".join(where), params


def list_board(slug, sort="new", tag=None, q=None, page=1, per_page=20):
    extra, order = None, "p.created_at DESC, p.id DESC"
    if sort == "hot":
        extra = "p.likes >= 10 AND p.created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)"
        order = "p.likes DESC, p.created_at DESC"
    elif sort == "answers":
        order = "comment_cnt DESC, p.created_at DESC"
    elif sort == "unanswered":
        extra = "NOT EXISTS (SELECT 1 FROM comments c WHERE c.post_id = p.id AND c.is_blind = 0)"
    elif sort == "admin":
        extra = "EXISTS (SELECT 1 FROM comments c JOIN users u ON u.id = c.user_id WHERE c.post_id = p.id AND u.role = 'admin' AND c.is_blind = 0)"
    w, params = _filters(slug, tag, q, extra)
    rows = query(f"SELECT {LIST_COLS} FROM posts p JOIN boards b ON b.id = p.board_id WHERE {w} ORDER BY {order} LIMIT %s OFFSET %s",
                 params + [per_page, (page - 1) * per_page])
    total = query_one(f"SELECT COUNT(*) AS n FROM posts p JOIN boards b ON b.id = p.board_id WHERE {w}", params)["n"]
    return rows, total


def hot_24h(slug, limit=5):
    return query(
        f"""SELECT {LIST_COLS} FROM posts p JOIN boards b ON b.id = p.board_id
            WHERE b.slug = %s AND p.is_blind = 0 AND p.created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            ORDER BY (p.likes * 2 + comment_cnt) DESC, p.views DESC LIMIT %s""", [slug, limit])


def get(post_id):
    return query_one(
        f"""SELECT {LIST_COLS}, p.body, p.accepted_comment_id, b.slug AS board_slug, b.name AS board_name
            FROM posts p JOIN boards b ON b.id = p.board_id WHERE p.id = %s""", [post_id])


def create(slug, user_id, anon_nick, title, body, channel_tag=None, image_url=None):
    bid = board_id(slug)
    return execute(
        "INSERT INTO posts (board_id, user_id, anon_nick, channel_tag, title, body, image_url) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        [bid, user_id, anon_nick, channel_tag, title, body, image_url])


def add_view(post_id):
    execute("UPDATE posts SET views = views + 1 WHERE id = %s", [post_id])


def list_by_user(user_id, limit=20):
    return query(
        f"""SELECT {LIST_COLS}, b.slug AS board_slug, b.name AS board_name FROM posts p JOIN boards b ON b.id = p.board_id
            WHERE p.user_id = %s ORDER BY p.created_at DESC LIMIT %s""", [user_id, limit])


def count_by_user(user_id):
    rows = query("SELECT b.slug, COUNT(*) AS n FROM posts p JOIN boards b ON b.id = p.board_id WHERE p.user_id = %s GROUP BY b.slug", [user_id])
    return {r["slug"]: r["n"] for r in rows}


# ---- likes ---------------------------------------------------------------
def toggle_like(post_id, user_id):
    if query_one("SELECT 1 FROM post_likes WHERE post_id = %s AND user_id = %s", [post_id, user_id]):
        execute("DELETE FROM post_likes WHERE post_id = %s AND user_id = %s", [post_id, user_id])
        execute("UPDATE posts SET likes = GREATEST(likes - 1, 0) WHERE id = %s", [post_id]); liked = False
    else:
        execute("INSERT INTO post_likes (post_id, user_id) VALUES (%s,%s)", [post_id, user_id])
        execute("UPDATE posts SET likes = likes + 1 WHERE id = %s", [post_id]); liked = True
    return liked, query_one("SELECT likes FROM posts WHERE id = %s", [post_id])["likes"]


def liked_by(post_id, user_id):
    return bool(user_id) and query_one("SELECT 1 FROM post_likes WHERE post_id = %s AND user_id = %s", [post_id, user_id]) is not None


# ---- reports -------------------------------------------------------------
def report(target_type, target_id, user_id, reason):
    """Returns (ok, blinded). One report per user per target; 3 reports -> auto blind."""
    if query_one("SELECT 1 FROM reports WHERE target_type = %s AND target_id = %s AND user_id = %s", [target_type, target_id, user_id]):
        return False, False
    execute("INSERT INTO reports (target_type, target_id, user_id, reason) VALUES (%s,%s,%s,%s)", [target_type, target_id, user_id, reason[:200]])
    n = query_one("SELECT COUNT(*) AS n FROM reports WHERE target_type = %s AND target_id = %s", [target_type, target_id])["n"]
    blinded = n >= BLIND_THRESHOLD
    if target_type == "post":
        execute("UPDATE posts SET report_cnt = %s, is_blind = IF(%s, 1, is_blind) WHERE id = %s", [n, blinded, target_id])
    else:
        execute("UPDATE comments SET is_blind = IF(%s, 1, is_blind) WHERE id = %s", [blinded, target_id])
    return True, blinded


# ---- comments ------------------------------------------------------------
def list_comments(post_id):
    return query(
        """SELECT c.*, u.role AS user_role FROM comments c JOIN users u ON u.id = c.user_id
           WHERE c.post_id = %s ORDER BY (u.role = 'admin') DESC, COALESCE(c.parent_id, c.id), c.id""", [post_id])


def add_comment(post_id, user_id, anon_nick, body, parent_id=None):
    return execute("INSERT INTO comments (post_id, user_id, parent_id, anon_nick, body) VALUES (%s,%s,%s,%s,%s)",
                   [post_id, user_id, parent_id, anon_nick, body])


def get_comment(comment_id):
    return query_one("SELECT * FROM comments WHERE id = %s", [comment_id])


def count_comments_by_user(user_id):
    return query_one("SELECT COUNT(*) AS n FROM comments WHERE user_id = %s", [user_id])["n"]


# ---- 어드민 관리 (2026-09-25) ---------------------------------------------
def list_admin(slug=None, q=None, blind=None, page=1, per_page=20):
    """게시글 관리 목록. slug 를 주면 그 게시판만, blind=True 면 블라인드 처리된 글만."""
    where, params = ["1=1"], []
    if slug:
        where.append("b.slug = %s"); params.append(slug)
    if q:
        where.append("(p.title LIKE %s OR p.body LIKE %s OR p.anon_nick LIKE %s)"); params += [f"%{q}%"] * 3
    if blind is not None:
        where.append("p.is_blind = %s"); params.append(1 if blind else 0)
    w = " AND ".join(where)
    rows = query(
        f"""SELECT p.*, b.slug, b.name AS board_name,
                   (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id) AS comment_cnt
            FROM posts p JOIN boards b ON b.id = p.board_id
            WHERE {w} ORDER BY p.created_at DESC, p.id DESC LIMIT %s OFFSET %s""",
        params + [per_page, (page - 1) * per_page])
    total = query_one(f"SELECT COUNT(*) AS n FROM posts p JOIN boards b ON b.id = p.board_id WHERE {w}", params)["n"]
    return rows, total


def admin_counts():
    rows = query(
        """SELECT b.slug, COUNT(*) AS n FROM posts p JOIN boards b ON b.id = p.board_id GROUP BY b.slug""")
    out = {r["slug"]: r["n"] for r in rows}
    out["all"] = sum(out.values())
    out["blind"] = query_one("SELECT COUNT(*) AS n FROM posts WHERE is_blind = 1")["n"]
    return out


def purge(post_id):
    """글과 딸린 댓글·추천·신고·닉네임을 지운다."""
    for sql in ("DELETE FROM comments WHERE post_id = %s",
                "DELETE FROM post_likes WHERE post_id = %s",
                "DELETE FROM post_nicks WHERE post_id = %s",
                "DELETE FROM reports WHERE target_type = 'post' AND target_id = %s",
                "DELETE FROM posts WHERE id = %s"):
        execute(sql, [post_id])


def purge_comment(comment_id):
    execute("DELETE FROM reports WHERE target_type = 'comment' AND target_id = %s", [comment_id])
    execute("DELETE FROM comments WHERE id = %s", [comment_id])
