"""store_slots table (shopping keyword tracking slots)."""
from ..db import execute, query, query_one


def list_user(user_id):
    return query("SELECT * FROM store_slots WHERE user_id = %s ORDER BY created_at DESC, id DESC", [user_id])


def count_user(user_id):
    return query_one("SELECT COUNT(*) AS n FROM store_slots WHERE user_id = %s", [user_id])["n"]


def get(slot_id, user_id):
    return query_one("SELECT * FROM store_slots WHERE id = %s AND user_id = %s", [slot_id, user_id])


def insert(user_id, keyword, product_url, store_name, pc_cnt, mo_cnt, reco):
    return execute(
        """INSERT INTO store_slots (user_id, keyword, product_url, store_name, pc_cnt, mo_cnt, reco_qty, fetched_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())""",
        [user_id, keyword, product_url or None, store_name or None, pc_cnt, mo_cnt, reco])


def update_volume(slot_id, pc_cnt, mo_cnt, reco):
    execute("UPDATE store_slots SET pc_cnt = %s, mo_cnt = %s, reco_qty = %s, fetched_at = NOW() WHERE id = %s",
            [pc_cnt, mo_cnt, reco, slot_id])


def delete(slot_id, user_id):
    execute("DELETE FROM store_slots WHERE id = %s AND user_id = %s", [slot_id, user_id])


def list_all():
    return query("SELECT * FROM store_slots ORDER BY id")
