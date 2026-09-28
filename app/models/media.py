"""media table (the ad_types catalog)."""
import json
from datetime import date

from ..db import execute, query, query_one

BADGE_LABEL = {"hot": "인기", "best": "BEST", "new": "NEW", "pick": "추천"}


def decorate(m):
    """JSON columns -> lists, and drop a badge whose badge_until has passed."""
    if not m:
        return m
    for k in ("fit_for", "flow_steps"):
        v = m.get(k)
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except ValueError:
                v = None
        m[k] = v or []
    if m.get("badge") and m.get("badge_until") and m["badge_until"] < date.today():
        m["badge"] = None
    m["badge_label"] = BADGE_LABEL.get(m.get("badge"))
    return m


def list_by_channel(channel, active_only=True):
    where = "channel = %s" + (" AND is_active = 1" if active_only else "")
    return [decorate(m) for m in query(f"SELECT * FROM media WHERE {where} ORDER BY group_name, sort, id", [channel])]


def get(media_id):
    return decorate(query_one("SELECT * FROM media WHERE id = %s", [media_id]))


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


# ---- 계정별 단가 (2026-09-28) --------------------------------------------
# 같은 매체라도 회원마다 다른 단가를 줄 수 있다. 없으면 media.unit_price 가 그대로 쓰인다.
# 단가는 "지금 얼마인가"만 담는다 — 이미 만들어진 캠페인은 campaigns.unit_price 에
# 그때 값이 박제되므로 여기를 바꿔도 과거 주문 금액은 변하지 않는다.
def user_prices(user_id):
    """{media_id: unit_price} — 그 회원에게만 적용되는 단가."""
    if not user_id:
        return {}
    return {r["media_id"]: r["unit_price"]
            for r in query("SELECT media_id, unit_price FROM user_media_prices WHERE user_id = %s", [user_id])}


def apply_user_prices(user_id, medias):
    """매체 목록에 회원 단가를 덮어씌운다. 원래 값은 base_price 로 남긴다."""
    prices = user_prices(user_id)
    for m in medias:
        base = m["unit_price"]
        m["base_price"] = base
        if m["id"] in prices:
            m["unit_price"] = prices[m["id"]]
            m["custom_price"] = True
    return medias


def price_for(user_id, media):
    """이 회원에게 적용할 단가 하나."""
    if not user_id or not media:
        return media["unit_price"] if media else 0
    row = query_one("SELECT unit_price FROM user_media_prices WHERE user_id = %s AND media_id = %s",
                    [user_id, media["id"]])
    return row["unit_price"] if row else media["unit_price"]


def set_user_price(user_id, media_id, unit_price, memo=None, actor_id=None):
    execute("""INSERT INTO user_media_prices (user_id, media_id, unit_price, memo, updated_by)
               VALUES (%s,%s,%s,%s,%s)
               ON DUPLICATE KEY UPDATE unit_price = VALUES(unit_price), memo = VALUES(memo),
                                       updated_by = VALUES(updated_by)""",
            [user_id, media_id, int(unit_price), (memo or "").strip()[:200] or None, actor_id])


def clear_user_price(user_id, media_id):
    execute("DELETE FROM user_media_prices WHERE user_id = %s AND media_id = %s", [user_id, media_id])


def user_price_rows(user_id):
    """어드민 화면용 — 채널·정렬 순서로 매체 전부 + 그 회원의 단가."""
    return query(
        """SELECT m.id, m.channel, m.name, m.group_name, m.unit_price AS base_price, m.is_active,
                  p.unit_price AS custom_price, p.memo
           FROM media m LEFT JOIN user_media_prices p ON p.media_id = m.id AND p.user_id = %s
           ORDER BY FIELD(m.channel,'store','place','coupang'), m.sort, m.name""", [user_id])


def users_with_custom_prices():
    return query(
        """SELECT u.id, u.nickname, u.email, u.username, u.kakao_id, u.biz_name, COUNT(*) AS n
           FROM user_media_prices p JOIN users u ON u.id = p.user_id
           GROUP BY u.id ORDER BY u.biz_name, u.nickname""")
