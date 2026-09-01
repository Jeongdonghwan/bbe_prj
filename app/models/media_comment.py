"""media_comments — per-media discussion shown on the popular-traffic page."""
from ..db import execute, query


def counts(media_ids):
    if not media_ids:
        return {}
    ph = ",".join(["%s"] * len(media_ids))
    rows = query(f"SELECT media_id, COUNT(*) AS n FROM media_comments WHERE media_id IN ({ph}) GROUP BY media_id",
                 list(media_ids))
    return {r["media_id"]: r["n"] for r in rows}


def list_for(media_id, limit=20):
    rows = query("SELECT id, anon_nick, body, created_at FROM media_comments WHERE media_id = %s ORDER BY id DESC LIMIT %s",
                 [media_id, limit])
    return rows[::-1]


def insert(media_id, user_id, nick, body):
    return execute("INSERT INTO media_comments (media_id, user_id, anon_nick, body) VALUES (%s,%s,%s,%s)",
                   [media_id, user_id, nick, body])
