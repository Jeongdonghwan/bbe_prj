"""popular_categories / popular_sets / popular_excludes / popular_meta (admin-curated rankings)."""
from ..db import execute, query, query_one


def list_categories(channel, active_only=False):
    where = "channel = %s" + (" AND is_active = 1" if active_only else "")
    return query(f"SELECT * FROM popular_categories WHERE {where} ORDER BY sort, id", [channel])


def get_category(cat_id):
    return query_one("SELECT * FROM popular_categories WHERE id = %s", [cat_id])


def create_category(channel, name):
    row = query_one("SELECT COALESCE(MAX(sort), 0) + 1 AS s FROM popular_categories WHERE channel = %s", [channel])
    cid = execute("INSERT INTO popular_categories (channel, name, sort, is_active) VALUES (%s,%s,%s,0)", [channel, name, row["s"]])
    execute("INSERT INTO popular_meta (category_id) VALUES (%s)", [cid])
    return cid


def update_category(cat_id, name=None, is_active=None, sort=None):
    fields = {}
    if name is not None:
        fields["name"] = name
    if is_active is not None:
        fields["is_active"] = 1 if is_active else 0
    if sort is not None:
        fields["sort"] = sort
    if fields:
        sets = ", ".join(f"{k} = %s" for k in fields)
        execute(f"UPDATE popular_categories SET {sets} WHERE id = %s", [*fields.values(), cat_id])


def delete_category(cat_id):
    execute("DELETE FROM popular_sets WHERE category_id = %s", [cat_id])
    execute("DELETE FROM popular_excludes WHERE category_id = %s", [cat_id])
    execute("DELETE FROM popular_meta WHERE category_id = %s", [cat_id])
    execute("DELETE FROM popular_categories WHERE id = %s", [cat_id])


def sets_for(cat_id):
    return query(
        """SELECT s.*, m.name AS media_name, m.color, m.logo_url, m.tagline, m.unit_price, m.list_price, m.badge,
                  m.efficiency_auto, m.efficiency_manual
           FROM popular_sets s JOIN media m ON m.id = s.media_id WHERE s.category_id = %s ORDER BY s.rank""", [cat_id])


def sets_summary(channel):
    """{category_id: [media_name by rank]}"""
    rows = query(
        """SELECT s.category_id, s.rank, m.name FROM popular_sets s JOIN media m ON m.id = s.media_id
           JOIN popular_categories c ON c.id = s.category_id WHERE c.channel = %s ORDER BY s.category_id, s.rank""", [channel])
    out = {}
    for r in rows:
        out.setdefault(r["category_id"], []).append(r["name"])
    return out


def excludes_for(cat_id):
    return {r["media_id"] for r in query("SELECT media_id FROM popular_excludes WHERE category_id = %s", [cat_id])}


def meta_for(cat_id):
    return query_one("SELECT * FROM popular_meta WHERE category_id = %s", [cat_id])


def meta_map(channel):
    rows = query(
        """SELECT pm.* FROM popular_meta pm JOIN popular_categories c ON c.id = pm.category_id WHERE c.channel = %s""", [channel])
    return {r["category_id"]: r for r in rows}


def save_sets(cat_id, ranks, notes, excludes, show_weekly, admin_id):
    """ranks: {1: media_id|None, 2:..., 3:...}; notes: {rank: text}; excludes: set(media_id)."""
    execute("DELETE FROM popular_sets WHERE category_id = %s", [cat_id])
    for rank in (1, 2, 3):
        mid = ranks.get(rank)
        if mid:
            execute("INSERT INTO popular_sets (category_id, rank, media_id, note) VALUES (%s,%s,%s,%s)",
                    [cat_id, rank, mid, (notes.get(rank) or "")[:80] or None])
    execute("DELETE FROM popular_excludes WHERE category_id = %s", [cat_id])
    for mid in excludes:
        execute("INSERT INTO popular_excludes (category_id, media_id) VALUES (%s,%s)", [cat_id, mid])
    execute(
        """INSERT INTO popular_meta (category_id, show_weekly_cnt, updated_by) VALUES (%s,%s,%s)
           ON DUPLICATE KEY UPDATE show_weekly_cnt = VALUES(show_weekly_cnt), updated_by = VALUES(updated_by), updated_at = NOW()""",
        [cat_id, 1 if show_weekly else 0, admin_id])


def weekly_counts(channel):
    rows = query(
        """SELECT media_id, COUNT(*) AS n FROM campaigns
           WHERE channel = %s AND created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY) AND status <> 'cancelled' GROUP BY media_id""", [channel])
    return {r["media_id"]: r["n"] for r in rows}
