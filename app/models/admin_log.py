"""admin_log table — every admin write goes through log()."""
from ..db import execute, query


def log(admin_id, action, target_type=None, target_id=None, summary=None):
    return execute(
        "INSERT INTO admin_log (admin_id, action, target_type, target_id, summary) VALUES (%s,%s,%s,%s,%s)",
        [admin_id, action, target_type, target_id, (summary or "")[:300]])


def recent(limit=10):
    return query(
        """SELECT l.*, u.nickname AS admin_name,
                  c.biz_name AS c_biz, c.main_keyword AS c_kw, c.channel AS c_channel, m.name AS c_media
           FROM admin_log l LEFT JOIN users u ON u.id = l.admin_id
           LEFT JOIN campaigns c ON l.target_type = 'campaign' AND c.id = l.target_id
           LEFT JOIN media m ON m.id = c.media_id
           ORDER BY l.created_at DESC, l.id DESC LIMIT %s""", [limit])
