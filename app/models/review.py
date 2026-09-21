"""reviews — 캠페인을 완료한 사업자가 남기는 상품 후기.

rating_avg / review_cnt 는 media 에 캐시해 둔다. 목록 조회에서 집계하지 않으므로,
후기를 넣거나 숨길 때마다 recount() 를 불러야 한다.
"""
from ..db import execute, query, query_one

VISIBLE = ("shown", "pinned")


def list_for(type_id, limit=30):
    return query(
        """SELECT id, stars, body, nick, keyword, days, status, created_at
           FROM reviews WHERE type_id = %s AND status IN ('shown','pinned')
           ORDER BY status = 'pinned' DESC, created_at DESC LIMIT %s""",
        [type_id, limit])


def star_dist(type_id):
    """[5점수, 4점수, 3점수, 2점수, 1점수] — 드로어의 분포 바에 쓴다."""
    rows = query(
        """SELECT stars, COUNT(*) AS n FROM reviews
           WHERE type_id = %s AND status IN ('shown','pinned') GROUP BY stars""", [type_id])
    by = {r["stars"]: r["n"] for r in rows}
    return [by.get(s, 0) for s in (5, 4, 3, 2, 1)]


def done_campaign_without_review(user_id, type_id):
    """후기를 쓸 수 있는 완료 캠페인 1건. 완료 캠페인당 1건이므로 이미 쓴 건은 제외한다."""
    return query_one(
        """SELECT c.id, c.main_keyword, c.start_date, c.end_date, c.daily_qty
           FROM campaigns c
           LEFT JOIN reviews r ON r.campaign_id = c.id
           WHERE c.user_id = %s AND c.media_id = %s AND c.status = 'done' AND r.id IS NULL
           ORDER BY c.end_date DESC LIMIT 1""",
        [user_id, type_id])


def insert(type_id, user_id, campaign_id, stars, body, nick, keyword, days):
    return execute(
        """INSERT INTO reviews (type_id, user_id, campaign_id, stars, body, nick, keyword, days)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        [type_id, user_id, campaign_id, stars, body, nick, keyword, days])


def set_status(review_id, status):
    execute("UPDATE reviews SET status = %s WHERE id = %s", [status, review_id])


def recount(type_id):
    """Refresh the cached average/count on media after any visibility change."""
    row = query_one(
        """SELECT COUNT(*) AS n, COALESCE(AVG(stars), 0) AS avg_stars FROM reviews
           WHERE type_id = %s AND status IN ('shown','pinned')""", [type_id])
    execute("UPDATE media SET review_cnt = %s, rating_avg = %s WHERE id = %s",
            [row["n"], round(float(row["avg_stars"]), 1), type_id])
    return row["n"]
