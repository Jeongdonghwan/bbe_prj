"""weekly_ranks — 운영팀이 주간으로 정하는 채널별 추천 1~3위."""
from datetime import date, timedelta

from ..db import execute, query, query_one


def week_start(d=None):
    d = d or date.today()
    return d - timedelta(days=d.weekday())


def week_label(start=None):
    start = start or week_start()
    end = start + timedelta(days=6)
    return f"{start.strftime('%Y.%m.%d')} – {end.strftime('%m.%d')}"


def latest_week(channel, on_or_before=None):
    """이 채널에 실제로 순위가 들어 있는 가장 최근 주. 운영팀이 이번 주를 아직 안 정했으면 지난주를 쓴다."""
    row = query_one("SELECT MAX(week_start) AS w FROM weekly_ranks WHERE channel = %s AND week_start <= %s",
                    [channel, on_or_before or week_start()])
    return row["w"] if row and row["w"] else None


def by_type(channel, start=None):
    """{type_id: rank}. start 를 안 주면 이번 주, 이번 주가 비어 있으면 가장 최근 주로 물러난다."""
    if start is None:
        start = latest_week(channel) or week_start()
    rows = query("SELECT type_id, `rank` FROM weekly_ranks WHERE channel = %s AND week_start = %s",
                 [channel, start])
    return {r["type_id"]: r["rank"] for r in rows}


def save(channel, ranks, start=None):
    """ranks: {rank: type_id}. Replaces the whole week for this channel."""
    start = start or week_start()
    execute("DELETE FROM weekly_ranks WHERE channel = %s AND week_start = %s", [channel, start])
    for rank, type_id in sorted(ranks.items()):
        execute("INSERT INTO weekly_ranks (week_start, channel, type_id, `rank`) VALUES (%s,%s,%s,%s)",
                [start, channel, int(type_id), int(rank)])
