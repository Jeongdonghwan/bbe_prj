"""banners table."""
from ..db import query


def list_active_banners(limit=8, zone="grid"):
    return query(
        """SELECT id, title, subtitle, link, image_url, sort FROM banners
           WHERE is_active = 1 AND image_url IS NOT NULL AND zone = %s
             AND (start_at IS NULL OR start_at <= NOW())
             AND (end_at IS NULL OR end_at >= NOW())
           ORDER BY sort ASC, id ASC LIMIT %s""",
        [zone, limit],
    )


# ---- admin ---------------------------------------------------------------
def list_all():
    return query("SELECT * FROM banners ORDER BY sort, id")


def get(banner_id):
    from ..db import query_one
    return query_one("SELECT * FROM banners WHERE id = %s", [banner_id])


def save(banner_id, fields):
    from ..db import execute
    if banner_id:
        sets = ", ".join(f"{k} = %s" for k in fields)
        execute(f"UPDATE banners SET {sets} WHERE id = %s", [*fields.values(), banner_id])
        return banner_id
    cols = ", ".join(fields); ph = ", ".join(["%s"] * len(fields))
    return execute(f"INSERT INTO banners ({cols}) VALUES ({ph})", list(fields.values()))


def delete(banner_id):
    from ..db import execute
    execute("DELETE FROM banners WHERE id = %s", [banner_id])
