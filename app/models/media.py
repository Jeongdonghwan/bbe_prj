"""media table."""
from ..db import execute, query, query_one


def list_by_channel(channel, active_only=True):
    where = "channel = %s" + (" AND is_active = 1" if active_only else "")
    return query(f"SELECT * FROM media WHERE {where} ORDER BY group_name, sort, id", [channel])


def get(media_id):
    return query_one("SELECT * FROM media WHERE id = %s", [media_id])


def efficiency(m):
    return m["efficiency_manual"] if m["efficiency_manual"] is not None else m["efficiency_auto"]


def recent_intake(channel, days=7):
    """{media_id: [count per day, oldest first]} for the last `days` days."""
    rows = query(
        """SELECT media_id, DATE(created_at) AS d, COUNT(*) AS n FROM campaigns
           WHERE channel = %s AND created_at >= DATE_SUB(CURDATE(), INTERVAL %s DAY) AND status <> 'cancelled'
           GROUP BY media_id, DATE(created_at)""",
        [channel, days - 1],
    )
    out = {}
    for r in rows:
        out.setdefault(r["media_id"], {})[r["d"].isoformat()] = r["n"]
    return out


def month_intake_counts():
    rows = query(
        """SELECT media_id, COUNT(*) AS n FROM campaigns
           WHERE created_at >= DATE_FORMAT(CURDATE(), '%%Y-%%m-01') AND status <> 'cancelled' GROUP BY media_id"""
    )
    return {r["media_id"]: r["n"] for r in rows}


def update_fields(media_id, fields):
    """Admin update (P4). fields: dict of column -> value (whitelisted by caller)."""
    if not fields:
        return
    sets = ", ".join(f"{k} = %s" for k in fields)
    execute(f"UPDATE media SET {sets} WHERE id = %s", [*fields.values(), media_id])


def insert(fields):
    cols = ", ".join(fields)
    ph = ", ".join(["%s"] * len(fields))
    return execute(f"INSERT INTO media ({cols}) VALUES ({ph})", list(fields.values()))


def usage_count(media_id):
    return query_one("SELECT COUNT(*) AS n FROM campaigns WHERE media_id = %s", [media_id])["n"]


def delete(media_id):
    """Hard delete. Caller must ensure no campaigns reference this media."""
    execute("DELETE FROM popular_sets WHERE media_id = %s", [media_id])
    execute("DELETE FROM popular_excludes WHERE media_id = %s", [media_id])
    execute("DELETE FROM media WHERE id = %s", [media_id])
