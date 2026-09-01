"""contents table (notice / info / series)."""
from ..db import execute, query, query_one

PUBLISHED = "status = 'published' AND (publish_at IS NULL OR publish_at <= NOW())"


def list_contents(board, category=None, page=1, per_page=20, q=None):
    where = f"board = %s AND {PUBLISHED}"
    params = [board]
    if category:
        where += " AND category = %s"
        params.append(category)
    if q:
        where += " AND (title LIKE %s OR body LIKE %s)"
        params += [f"%{q}%"] * 2
    offset = (page - 1) * per_page
    rows = query(
        f"""SELECT id, board, category, title, body, is_pinned, views,
                   COALESCE(publish_at, created_at) AS published_at
            FROM contents WHERE {where}
            ORDER BY is_pinned DESC, COALESCE(publish_at, created_at) DESC, id DESC
            LIMIT %s OFFSET %s""",
        params + [per_page, offset],
    )
    return rows


def count_contents(board, category=None, q=None):
    where = f"board = %s AND {PUBLISHED}"
    params = [board]
    if category:
        where += " AND category = %s"
        params.append(category)
    if q:
        where += " AND (title LIKE %s OR body LIKE %s)"
        params += [f"%{q}%"] * 2
    return query_one(f"SELECT COUNT(*) AS n FROM contents WHERE {where}", params)["n"]


def get_content(content_id, boards):
    placeholders = ",".join(["%s"] * len(boards))
    return query_one(
        f"""SELECT *, COALESCE(publish_at, created_at) AS published_at
            FROM contents WHERE id = %s AND board IN ({placeholders}) AND {PUBLISHED}""",
        [content_id, *boards],
    )


def get_prev_next(content):
    """Adjacent published items in the same board by publish order."""
    base = f"board = %s AND {PUBLISHED} AND id <> %s"
    ts = content["published_at"]
    prev_row = query_one(
        f"""SELECT id, title FROM contents WHERE {base}
            AND (COALESCE(publish_at, created_at) < %s OR (COALESCE(publish_at, created_at) = %s AND id < %s))
            ORDER BY COALESCE(publish_at, created_at) DESC, id DESC LIMIT 1""",
        [content["board"], content["id"], ts, ts, content["id"]],
    )
    next_row = query_one(
        f"""SELECT id, title FROM contents WHERE {base}
            AND (COALESCE(publish_at, created_at) > %s OR (COALESCE(publish_at, created_at) = %s AND id > %s))
            ORDER BY COALESCE(publish_at, created_at) ASC, id ASC LIMIT 1""",
        [content["board"], content["id"], ts, ts, content["id"]],
    )
    return prev_row, next_row


def increment_views(content_id):
    execute("UPDATE contents SET views = views + 1 WHERE id = %s", [content_id])


def list_series():
    return query(
        f"""SELECT id, series_no, title, body FROM contents
            WHERE board = 'series' AND {PUBLISHED}
            ORDER BY series_no ASC, id ASC"""
    )


def dashboard_notices(limit=5):
    return query(
        f"""SELECT id, category, title, is_pinned, COALESCE(publish_at, created_at) AS published_at
            FROM contents WHERE board = 'notice' AND show_dashboard = 1 AND {PUBLISHED}
            ORDER BY is_pinned DESC, COALESCE(publish_at, created_at) DESC, id DESC LIMIT %s""",
        [limit],
    )


def list_channel_notices(channel, limit=5):
    return query(
        f"""SELECT id, title, COALESCE(publish_at, created_at) AS published_at FROM contents
            WHERE board = 'notice' AND channel = %s AND {PUBLISHED}
            ORDER BY is_pinned DESC, COALESCE(publish_at, created_at) DESC LIMIT %s""", [channel, limit])


def count_channel_notices(channel):
    return query_one(f"SELECT COUNT(*) AS n FROM contents WHERE board = 'notice' AND channel = %s AND {PUBLISHED}", [channel])["n"]


# ---- admin ---------------------------------------------------------------
def admin_list(tab="all", page=1, per_page=20):
    where, params = [], []
    if tab == "notice":
        where.append("board = 'notice'")
    elif tab == "info":
        where.append("board = 'info'")
    elif tab == "series":
        where.append("board = 'series'")
    elif tab == "draft":
        where.append("status = 'draft'")
    w = (" WHERE " + " AND ".join(where)) if where else ""
    order = "series_no ASC, id ASC" if tab == "series" else "COALESCE(publish_at, created_at) DESC, id DESC"
    rows = query(f"SELECT * FROM contents{w} ORDER BY {order} LIMIT %s OFFSET %s", params + [per_page, (page - 1) * per_page])
    total = query_one(f"SELECT COUNT(*) AS n FROM contents{w}", params)["n"]
    return rows, total


def admin_counts():
    rows = query("SELECT board, status, COUNT(*) AS n FROM contents GROUP BY board, status")
    out = {"all": 0, "notice": 0, "info": 0, "series": 0, "draft": 0}
    for r in rows:
        out["all"] += r["n"]; out[r["board"]] += r["n"]
        if r["status"] == "draft":
            out["draft"] += r["n"]
    return out


def get_any(content_id):
    return query_one("SELECT * FROM contents WHERE id = %s", [content_id])


def save(content_id, fields):
    if content_id:
        sets = ", ".join(f"{k} = %s" for k in fields)
        execute(f"UPDATE contents SET {sets} WHERE id = %s", [*fields.values(), content_id])
        return content_id
    cols = ", ".join(fields); ph = ", ".join(["%s"] * len(fields))
    return execute(f"INSERT INTO contents ({cols}) VALUES ({ph})", list(fields.values()))


def delete(content_id):
    execute("DELETE FROM contents WHERE id = %s", [content_id])


def swap_series_order(content_id, direction):
    """Move a series item up/down by swapping series_no with its neighbour."""
    me = get_any(content_id)
    if not me or me["board"] != "series":
        return
    op, order = ("<", "DESC") if direction == "up" else (">", "ASC")
    other = query_one(f"SELECT id, series_no FROM contents WHERE board = 'series' AND series_no {op} %s ORDER BY series_no {order} LIMIT 1", [me["series_no"]])
    if not other:
        return
    execute("UPDATE contents SET series_no = %s WHERE id = %s", [other["series_no"], me["id"]])
    execute("UPDATE contents SET series_no = %s WHERE id = %s", [me["series_no"], other["id"]])


def next_series_no():
    return query_one("SELECT COALESCE(MAX(series_no), 0) + 1 AS n FROM contents WHERE board = 'series'")["n"]
