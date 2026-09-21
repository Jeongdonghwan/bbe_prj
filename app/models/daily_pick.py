"""daily_picks — admin-curated "오늘의 인기" ad types per channel and date."""
import json

from ..db import execute, query_one


def get(channel, pick_date):
    row = query_one("SELECT type_ids FROM daily_picks WHERE channel = %s AND pick_date = %s", [channel, pick_date])
    if not row:
        return []
    ids = row["type_ids"]
    if isinstance(ids, str):
        try:
            ids = json.loads(ids)
        except ValueError:
            return []
    return [int(i) for i in ids or []]


def save(channel, pick_date, type_ids):
    execute(
        """INSERT INTO daily_picks (pick_date, channel, type_ids) VALUES (%s,%s,%s)
           ON DUPLICATE KEY UPDATE type_ids = VALUES(type_ids)""",
        [pick_date, channel, json.dumps([int(i) for i in type_ids])])
