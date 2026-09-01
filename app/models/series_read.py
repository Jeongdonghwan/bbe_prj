"""series_reads (logged-in read marks for the 입문 시리즈)."""
from ..db import execute, query


def read_ids(user_id):
    return {r["content_id"] for r in query("SELECT content_id FROM series_reads WHERE user_id = %s", [user_id])}


def mark(user_id, content_id):
    execute("INSERT IGNORE INTO series_reads (user_id, content_id) VALUES (%s,%s)", [user_id, content_id])


def merge_session(user_id, ids):
    for cid in ids or []:
        mark(user_id, cid)
