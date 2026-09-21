"""weekly_ranks — 운영팀이 주간으로 정하는 채널별 추천 1~3위."""
from datetime import date, timedelta

from ..db import execute, query


def week_start(d=None):
    d = d or date.today()
    return d - timedelta(days=d.weekday())


def week_label(start=None):
    start = start or week_start()
    end = start + timedelta(days=6)
    return f"{start.strftime('%Y.%m.%d')} – {end.strftime('%m.%d')}"


def by_type(channel, start=None):
    """{type_id: rank} for the given week. Empty when the week has not been set."""
    rows = query("SELECT type_id, `rank` FROM weekly_ranks WHERE channel = %s AND week_start = %s",
                 [channel, start or week_start()])
    return {r["type_id"]: r["rank"] for r in rows}


def save(channel, ranks, start=None):
    """ranks: {rank: type_id}. Replaces the whole week for this channel."""
    start = start or week_start()
    execute("DELETE FROM weekly_ranks WHERE channel = %s AND week_start = %s", [channel, start])
    for rank, type_id in sorted(ranks.items()):
        execute("INSERT INTO weekly_ranks (week_start, channel, type_id, `rank`) VALUES (%s,%s,%s,%s)",
                [start, channel, int(type_id), int(rank)])
