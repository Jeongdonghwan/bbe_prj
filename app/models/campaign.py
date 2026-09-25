"""campaigns / campaign_daily / status_log tables. Status changes only via services.campaign_service.transition."""
import json

from ..db import execute, query, query_one

ACTIVE_STATUSES = ("pay_wait", "review", "approved", "running")
PAID_STATUSES = ("review", "approved", "running", "done", "stopped", "rejected")

SELECT = """SELECT c.*, m.name AS media_name, m.color AS media_color, m.logo_url AS media_logo, m.min_days, m.min_daily, m.max_daily
            FROM campaigns c JOIN media m ON m.id = c.media_id"""


def _decode(row):
    if row:
        for k in ("sub_keywords", "setting_keywords", "extra"):
            v = row.get(k)
            if isinstance(v, str):
                try:
                    row[k] = json.loads(v)
                except ValueError:
                    row[k] = None
    return row


def get(campaign_id):
    return _decode(query_one(f"{SELECT} WHERE c.id = %s", [campaign_id]))


def get_by_order_no(order_no):
    return _decode(query_one(f"{SELECT} WHERE c.order_no = %s", [order_no]))


def order_no_exists(order_no):
    return query_one("SELECT 1 FROM campaigns WHERE order_no = %s", [order_no]) is not None


def insert(data):
    cols = ", ".join(data)
    ph = ", ".join(["%s"] * len(data))
    vals = [json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for v in data.values()]
    return execute(f"INSERT INTO campaigns ({cols}) VALUES ({ph})", vals)


def delete(campaign_id):
    """Hard-delete a just-created row when credit spend fails (no logs/payments yet)."""
    execute("DELETE FROM campaigns WHERE id = %s", [campaign_id])


def update(campaign_id, data):
    sets = ", ".join(f"{k} = %s" for k in data)
    vals = [json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for v in data.values()]
    execute(f"UPDATE campaigns SET {sets} WHERE id = %s", [*vals, campaign_id])


def set_status(campaign_id, status):
    """Only campaign_service.transition may call this."""
    execute("UPDATE campaigns SET status = %s WHERE id = %s", [status, campaign_id])


# ---- lists ---------------------------------------------------------------
def _filters(user_id, channel, status, period, media_id, q):
    where, params = ["c.user_id = %s", "c.channel = %s"], [user_id, channel]
    if status:
        where.append("c.status = %s"); params.append(status)
    if period == "month":
        where.append("c.created_at >= DATE_FORMAT(CURDATE(), '%%Y-%%m-01')")
    elif period == "last":
        where.append("c.created_at >= DATE_FORMAT(CURDATE() - INTERVAL 1 MONTH, '%%Y-%%m-01') AND c.created_at < DATE_FORMAT(CURDATE(), '%%Y-%%m-01')")
    if media_id:
        where.append("c.media_id = %s"); params.append(media_id)
    if q:
        where.append("(c.order_no LIKE %s OR c.biz_name LIKE %s OR c.main_keyword LIKE %s OR c.product_name LIKE %s)")
        params += [f"%{q}%"] * 4
    return " AND ".join(where), params


def list_user(user_id, channel, status=None, period=None, media_id=None, q=None, page=1, per_page=20):
    where, params = _filters(user_id, channel, status, period, media_id, q)
    rows = query(f"{SELECT} WHERE {where} ORDER BY c.created_at DESC, c.id DESC LIMIT %s OFFSET %s",
                 params + [per_page, (page - 1) * per_page])
    return [_decode(r) for r in rows]


def count_user(user_id, channel, status=None, period=None, media_id=None, q=None):
    where, params = _filters(user_id, channel, status, period, media_id, q)
    return query_one(f"SELECT COUNT(*) AS n FROM campaigns c WHERE {where}", params)["n"]


def status_counts(user_id, channel):
    rows = query("SELECT status, COUNT(*) AS n FROM campaigns WHERE user_id = %s AND channel = %s GROUP BY status",
                 [user_id, channel])
    return {r["status"]: r["n"] for r in rows}


def media_used(user_id, channel):
    return query(
        """SELECT DISTINCT m.id, m.name FROM campaigns c JOIN media m ON m.id = c.media_id
           WHERE c.user_id = %s AND c.channel = %s ORDER BY m.name""", [user_id, channel])


def list_recent_channel(user_id, channel, limit=5):
    ph = ",".join(["%s"] * len(ACTIVE_STATUSES))
    return [_decode(r) for r in query(
        f"{SELECT} WHERE c.user_id = %s AND c.channel = %s AND c.status IN ({ph}) ORDER BY c.created_at DESC LIMIT %s",
        [user_id, channel, *ACTIVE_STATUSES, limit])]


# ---- summaries -----------------------------------------------------------
def summary_by_channel(user_id):
    rows = query("SELECT channel, status, COUNT(*) AS n FROM campaigns WHERE user_id = %s GROUP BY channel, status", [user_id])
    out = {}
    for r in rows:
        out.setdefault(r["channel"], {})[r["status"]] = r["n"]
    return out


def count_done(user_id):
    return query_one("SELECT COUNT(*) AS n FROM campaigns WHERE user_id = %s AND status = 'done'", [user_id])["n"]


def count_active(user_id):
    ph = ",".join(["%s"] * len(ACTIVE_STATUSES))
    return query_one(f"SELECT COUNT(*) AS n FROM campaigns WHERE user_id = %s AND status IN ({ph})", [user_id, *ACTIVE_STATUSES])["n"]


def total_paid(user_id):
    row = query_one("SELECT COALESCE(SUM(paid_amount - refund_amount), 0) AS n FROM campaigns WHERE user_id = %s AND paid_at IS NOT NULL", [user_id])
    return int(row["n"])


def month_paid(user_id, channel=None):
    where, params = "user_id = %s AND paid_at IS NOT NULL AND paid_at >= DATE_FORMAT(CURDATE(), '%%Y-%%m-01')", [user_id]
    if channel:
        where += " AND channel = %s"; params.append(channel)
    return int(query_one(f"SELECT COALESCE(SUM(paid_amount - refund_amount), 0) AS n FROM campaigns WHERE {where}", params)["n"])


def last_month_paid(user_id, channel=None):
    where, params = ("user_id = %s AND paid_at >= DATE_FORMAT(CURDATE() - INTERVAL 1 MONTH, '%%Y-%%m-01') "
                     "AND paid_at < DATE_FORMAT(CURDATE(), '%%Y-%%m-01')"), [user_id]
    if channel:
        where += " AND channel = %s"; params.append(channel)
    return int(query_one(f"SELECT COALESCE(SUM(paid_amount - refund_amount), 0) AS n FROM campaigns WHERE {where}", params)["n"])


def running_today_spend(user_id, channel):
    row = query_one(
        """SELECT COALESCE(SUM(unit_price * daily_qty), 0) AS n FROM campaigns
           WHERE user_id = %s AND channel = %s AND status = 'running'
             AND start_date <= CURDATE()""", [user_id, channel])
    return int(row["n"])


def avg_rank_change(user_id, channel):
    row = query_one(
        """SELECT AVG(rank_start - rank_now) AS avg_up, COUNT(*) AS n FROM campaigns
           WHERE user_id = %s AND channel = %s AND status = 'done' AND rank_start IS NOT NULL AND rank_now IS NOT NULL""",
        [user_id, channel])
    return (float(row["avg_up"]) if row["avg_up"] is not None else None), row["n"]


def avg_daily_qty_for_category(channel, category):
    row = query_one(
        """SELECT AVG(daily_qty) AS a, COUNT(*) AS n FROM campaigns
           WHERE channel = %s AND status = 'done' AND JSON_UNQUOTE(JSON_EXTRACT(extra, '$.category')) = %s""",
        [channel, category])
    return int(row["a"]) if row["n"] else None


def list_payments(user_id, page=1, per_page=20):
    return [_decode(r) for r in query(
        f"{SELECT} WHERE c.user_id = %s ORDER BY c.created_at DESC, c.id DESC LIMIT %s OFFSET %s",
        [user_id, per_page, (page - 1) * per_page])]


def count_payments(user_id):
    return query_one("SELECT COUNT(*) AS n FROM campaigns WHERE user_id = %s", [user_id])["n"]


# ---- campaign_daily ------------------------------------------------------
def upsert_daily(campaign_id, date, rank, done_qty):
    execute(
        """INSERT INTO campaign_daily (campaign_id, date, rank, done_qty) VALUES (%s,%s,%s,%s)
           ON DUPLICATE KEY UPDATE rank = VALUES(rank), done_qty = VALUES(done_qty)""",
        [campaign_id, date, rank, done_qty])


def list_daily(campaign_id):
    return query("SELECT * FROM campaign_daily WHERE campaign_id = %s ORDER BY date", [campaign_id])


def total_done_qty(campaign_id):
    return int(query_one("SELECT COALESCE(SUM(done_qty), 0) AS n FROM campaign_daily WHERE campaign_id = %s", [campaign_id])["n"])


# ---- status_log ----------------------------------------------------------
def add_log(campaign_id, from_status, to_status, actor_id=None, memo=None):
    return execute(
        "INSERT INTO status_log (campaign_id, from_status, to_status, actor_id, memo) VALUES (%s,%s,%s,%s,%s)",
        [campaign_id, from_status, to_status, actor_id, memo])


def list_log(campaign_id):
    return query("SELECT * FROM status_log WHERE campaign_id = %s ORDER BY created_at DESC, id DESC", [campaign_id])


# ---- admin ---------------------------------------------------------------
ADMIN_SELECT = """SELECT c.*, m.name AS media_name, m.color AS media_color, u.nickname, u.phone AS user_phone,
                         u.email AS user_email, u.biz_name AS user_biz, u.kakao_id AS user_kakao
                  FROM campaigns c JOIN media m ON m.id = c.media_id JOIN users u ON u.id = c.user_id"""


def _admin_filters(status, channel, media_id, period, q, user_id=None, ids=None, date_from=None, date_to=None):
    """ids/user_id/date_from/date_to: 엑셀 추출용 (2026-09-23). 날짜 범위는 등록일 기준 — period 와 같은 축."""
    where, params = ["1=1"], []
    if status:
        where.append("c.status = %s"); params.append(status)
    if user_id:
        where.append("c.user_id = %s"); params.append(user_id)
    if ids:
        where.append(f"c.id IN ({','.join(['%s'] * len(ids))})"); params += list(ids)
    if date_from:
        where.append("c.created_at >= %s"); params.append(date_from)
    if date_to:
        where.append("c.created_at < DATE_ADD(%s, INTERVAL 1 DAY)"); params.append(date_to)
    if channel:
        where.append("c.channel = %s"); params.append(channel)
    if media_id:
        where.append("c.media_id = %s"); params.append(media_id)
    if period == "today":
        where.append("c.created_at >= CURDATE()")
    elif period == "week":
        where.append("c.created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)")
    elif period == "month":
        where.append("c.created_at >= DATE_FORMAT(CURDATE(), '%%Y-%%m-01')")
    if q:
        where.append("(c.order_no LIKE %s OR u.nickname LIKE %s OR c.biz_name LIKE %s OR c.main_keyword LIKE %s)")
        params += [f"%{q}%"] * 4
    return " AND ".join(where), params


def admin_list(status=None, channel=None, media_id=None, period=None, q=None, page=1, per_page=20, **flt):
    w, p = _admin_filters(status, channel, media_id, period, q, **flt)
    rows = query(f"{ADMIN_SELECT} WHERE {w} ORDER BY c.created_at DESC, c.id DESC LIMIT %s OFFSET %s", p + [per_page, (page - 1) * per_page])
    return [_decode(r) for r in rows]


def admin_all(status=None, channel=None, media_id=None, period=None, q=None, limit=5000, **flt):
    w, p = _admin_filters(status, channel, media_id, period, q, **flt)
    return [_decode(r) for r in query(f"{ADMIN_SELECT} WHERE {w} ORDER BY c.created_at DESC LIMIT %s", p + [limit])]


def admin_count(status=None, channel=None, media_id=None, period=None, q=None, **flt):
    w, p = _admin_filters(status, channel, media_id, period, q, **flt)
    return query_one(f"SELECT COUNT(*) AS n FROM campaigns c JOIN users u ON u.id = c.user_id WHERE {w}", p)["n"]


def accounts_with_campaigns():
    """계정 필터용 — 캠페인이 있는 회원만."""
    return query(
        """SELECT u.id, u.nickname, u.email, u.biz_name, COUNT(c.id) AS n
           FROM users u JOIN campaigns c ON c.user_id = u.id GROUP BY u.id ORDER BY u.biz_name, u.nickname""")


def daily_records(campaign_ids, date_from, date_to):
    """{(campaign_id, date): {done_qty, rank}} — 어드민이 기록한 일별 작업량·순위."""
    if not campaign_ids:
        return {}
    ph = ",".join(["%s"] * len(campaign_ids))
    rows = query(
        f"""SELECT campaign_id, date, done_qty, `rank` FROM campaign_daily
            WHERE campaign_id IN ({ph}) AND date BETWEEN %s AND %s""",
        list(campaign_ids) + [date_from, date_to])
    return {(r["campaign_id"], r["date"]): r for r in rows}


def admin_status_counts():
    return {r["status"]: r["n"] for r in query("SELECT status, COUNT(*) AS n FROM campaigns GROUP BY status")}


def review_queue(limit=20):
    return [_decode(r) for r in query(f"{ADMIN_SELECT} WHERE c.status = 'review' ORDER BY c.paid_at ASC, c.id ASC LIMIT %s", [limit])]


def oldest_review_minutes():
    row = query_one("SELECT TIMESTAMPDIFF(MINUTE, MIN(COALESCE(paid_at, created_at)), NOW()) AS m FROM campaigns WHERE status = 'review'")
    return row["m"]


def running_without_today_rank():
    row = query_one(
        """SELECT COUNT(*) AS n FROM campaigns c WHERE c.status = 'running' AND c.start_date <= CURDATE()
           AND NOT EXISTS (SELECT 1 FROM campaign_daily d WHERE d.campaign_id = c.id AND d.date = CURDATE())""")
    return row["n"]


def today_intake():
    return query_one(
        """SELECT COUNT(*) AS n, COALESCE(SUM(paid_amount), 0) AS amount FROM campaigns
           WHERE created_at >= CURDATE() AND status <> 'cancelled'""")


def today_intake_by_media(limit=5):
    return query(
        """SELECT m.name, COUNT(*) AS n, COALESCE(SUM(c.paid_amount), 0) AS amount FROM campaigns c JOIN media m ON m.id = c.media_id
           WHERE c.created_at >= CURDATE() AND c.status <> 'cancelled' GROUP BY m.id ORDER BY n DESC LIMIT %s""", [limit])


def today_rank(campaign_id):
    return query_one("SELECT rank, done_qty FROM campaign_daily WHERE campaign_id = %s AND date = CURDATE()", [campaign_id])


def list_by_user(user_id, limit=20):
    return [_decode(r) for r in query(f"{SELECT} WHERE c.user_id = %s ORDER BY c.created_at DESC LIMIT %s", [user_id, limit])]


def set_admin_memo(campaign_id, memo):
    execute("UPDATE campaigns SET admin_memo = %s WHERE id = %s", [memo or None, campaign_id])


def done_rank_stats(media_id, days=30):
    row = query_one(
        """SELECT COUNT(*) AS n, SUM(rank_start IS NOT NULL AND rank_now IS NOT NULL AND rank_now < rank_start) AS up
           FROM campaigns WHERE media_id = %s AND status = 'done' AND updated_at >= DATE_SUB(NOW(), INTERVAL %s DAY)""", [media_id, days])
    return row["n"], int(row["up"] or 0)


# ---- 순위 자동 추적 -------------------------------------------------------
ACTIVE_TRACK_STATUSES = ("approved", "running")


def by_track(track_id):
    """이 trackId 로 순위를 받아야 하는 진행 중 캠페인들. 같은 키워드·상품이면 여럿일 수 있다."""
    ph = ",".join(["%s"] * len(ACTIVE_TRACK_STATUSES))
    return [_decode(r) for r in query(
        f"SELECT * FROM campaigns WHERE track_id = %s AND status IN ({ph})",
        [track_id, *ACTIVE_TRACK_STATUSES])]


def count_active_by_track(track_id, exclude_id=None):
    ph = ",".join(["%s"] * len(ACTIVE_TRACK_STATUSES))
    sql = f"SELECT COUNT(*) AS n FROM campaigns WHERE track_id = %s AND status IN ({ph})"
    p = [track_id, *ACTIVE_TRACK_STATUSES]
    if exclude_id:
        sql += " AND id <> %s"
        p.append(exclude_id)
    return query_one(sql, p)["n"]


def daily_rank(campaign_id, day):
    return query_one("SELECT `rank`, done_qty FROM campaign_daily WHERE campaign_id = %s AND date = %s",
                     [campaign_id, day])


def untracked_running(limit=200):
    """구동 중인데 아직 추적 슬롯이 없는 쇼핑 캠페인 — 등록 실패분 보정용."""
    return [_decode(r) for r in query(
        """SELECT * FROM campaigns WHERE channel = 'store' AND status IN ('approved','running')
           AND track_id IS NULL ORDER BY id LIMIT %s""", [limit])]


def mark_tracked(track_id, status):
    """콜백이 도착했음을 남긴다 (collected / not_found)."""
    execute("UPDATE campaigns SET track_status = %s WHERE track_id = %s", [status, track_id])


def tracked_without_today_rank(limit=200):
    """추적 슬롯은 있는데 오늘 순위가 안 들어온 구동 캠페인 — 콜백 유실 보정용."""
    return [_decode(r) for r in query(
        """SELECT c.* FROM campaigns c
           WHERE c.track_id IS NOT NULL AND c.status IN ('approved','running')
             AND c.start_date <= CURDATE() AND c.end_date >= CURDATE()
             AND NOT EXISTS (SELECT 1 FROM campaign_daily d
                             WHERE d.campaign_id = c.id AND d.date = CURDATE() AND d.`rank` IS NOT NULL)
           ORDER BY c.id LIMIT %s""", [limit])]


def purge(campaign_id):
    """캠페인과 딸린 기록을 완전히 지운다 (어드민 삭제). 크레딧 원장은 회계 기록이라 남긴다."""
    for t in ("campaign_daily", "status_log", "payments", "reviews"):
        execute(f"DELETE FROM {t} WHERE campaign_id = %s", [campaign_id])
    execute("DELETE FROM campaigns WHERE id = %s", [campaign_id])


def due_to_start():
    """시작일이 된 승인 캠페인."""
    return [_decode(r) for r in query(
        "SELECT * FROM campaigns WHERE status = 'approved' AND start_date <= CURDATE() ORDER BY id")]


def due_to_finish():
    """종료일이 지난 구동 캠페인."""
    return [_decode(r) for r in query(
        "SELECT * FROM campaigns WHERE status = 'running' AND end_date < CURDATE() ORDER BY id")]
