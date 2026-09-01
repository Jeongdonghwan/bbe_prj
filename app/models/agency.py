"""agency_requests / agency_proposals / agency_applies."""
from ..db import execute, query, query_one

BUDGET_LABEL = {"u30": "30만 이하", "30_100": "30~100만", "100_300": "100~300만", "o300": "300만 이상", "tbd": "미정"}
STATUS_LABEL = {"open": "모집 중", "matched": "매칭 완료", "closed": "마감"}
STATUS_PILL = {"open": "p-recruit", "matched": "p-match", "closed": "p-close"}
CHANNEL_LABEL = {"place": "플레이스", "store": "쇼핑·스토어", "coupang": "쿠팡", "multi": "복수 채널"}

COLS = """r.*, (SELECT COUNT(*) FROM agency_proposals p WHERE p.request_id = r.id) AS proposal_cnt"""


def list_requests(status=None, channel=None, user_id=None, page=1, per_page=20, q=None):
    where, params = ["1=1"], []
    if status:
        where.append("r.status = %s"); params.append(status)
    if channel:
        where.append("r.channel = %s"); params.append(channel)
    if user_id:
        where.append("r.user_id = %s"); params.append(user_id)
    if q:
        where.append("(r.industry LIKE %s OR r.region LIKE %s OR r.body LIKE %s)"); params += [f"%{q}%"] * 3
    w = " AND ".join(where)
    rows = query(f"SELECT {COLS} FROM agency_requests r WHERE {w} ORDER BY r.created_at DESC, r.id DESC LIMIT %s OFFSET %s",
                 params + [per_page, (page - 1) * per_page])
    total = query_one(f"SELECT COUNT(*) AS n FROM agency_requests r WHERE {w}", params)["n"]
    return rows, total


def get_request(req_id):
    return query_one(f"SELECT {COLS} FROM agency_requests r WHERE r.id = %s", [req_id])


def create_request(user_id, anon_nick, channel, industry, budget, region, body, contact):
    return execute(
        """INSERT INTO agency_requests (user_id, anon_nick, channel, industry, budget, region, body, contact)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""", [user_id, anon_nick, channel, industry, budget, region, body, contact])


def add_view(req_id):
    execute("UPDATE agency_requests SET views = views + 1 WHERE id = %s", [req_id])


def set_status(req_id, status, accepted_proposal_id=None):
    if status == "matched":
        execute("UPDATE agency_requests SET status = 'matched', accepted_proposal_id = %s WHERE id = %s", [accepted_proposal_id, req_id])
    elif status == "closed":
        execute("UPDATE agency_requests SET status = 'closed', closed_at = NOW() WHERE id = %s", [req_id])
    else:
        execute("UPDATE agency_requests SET status = 'open', accepted_proposal_id = NULL, closed_at = NULL WHERE id = %s", [req_id])


def close_stale(days=30):
    """Open requests without any activity for `days` -> closed. Returns count."""
    rows = query("SELECT id FROM agency_requests WHERE status = 'open' AND created_at < DATE_SUB(NOW(), INTERVAL %s DAY)", [days])
    for r in rows:
        set_status(r["id"], "closed")
    return len(rows)


# ---- proposals -----------------------------------------------------------
def list_proposals(req_id):
    return query(
        """SELECT p.*, u.nickname AS proposer_name, u.role AS proposer_role, u.biz_name AS proposer_biz
           FROM agency_proposals p JOIN users u ON u.id = p.proposer_id WHERE p.request_id = %s ORDER BY p.created_at""", [req_id])


def get_proposal(pid):
    return query_one("SELECT * FROM agency_proposals WHERE id = %s", [pid])


def my_proposal(req_id, user_id):
    return query_one("SELECT * FROM agency_proposals WHERE request_id = %s AND proposer_id = %s", [req_id, user_id])


def create_proposal(req_id, proposer_id, budget_plan, plan, duration):
    return execute("INSERT INTO agency_proposals (request_id, proposer_id, budget_plan, plan, duration) VALUES (%s,%s,%s,%s,%s)",
                   [req_id, proposer_id, budget_plan, plan, duration])


def accept_proposal(req_id, pid):
    execute("UPDATE agency_proposals SET status = 'rejected' WHERE request_id = %s AND id <> %s", [req_id, pid])
    execute("UPDATE agency_proposals SET status = 'accepted' WHERE id = %s", [pid])
    set_status(req_id, "matched", pid)


def list_all_proposals(page=1, per_page=20):
    rows = query(
        """SELECT p.*, u.nickname AS proposer_name, r.industry, r.region, r.status AS req_status, r.anon_nick
           FROM agency_proposals p JOIN users u ON u.id = p.proposer_id JOIN agency_requests r ON r.id = p.request_id
           ORDER BY p.created_at DESC LIMIT %s OFFSET %s""", [per_page, (page - 1) * per_page])
    total = query_one("SELECT COUNT(*) AS n FROM agency_proposals")["n"]
    return rows, total


# ---- applies (agency certification) --------------------------------------
def my_apply(user_id):
    return query_one("SELECT * FROM agency_applies WHERE user_id = %s ORDER BY id DESC LIMIT 1", [user_id])


def create_apply(user_id, biz_no, cert_url):
    return execute("INSERT INTO agency_applies (user_id, biz_no, biz_cert_url) VALUES (%s,%s,%s)", [user_id, biz_no, cert_url])


def list_applies(status=None, page=1, per_page=20):
    where, params = ("WHERE a.status = %s", [status]) if status else ("", [])
    rows = query(
        f"""SELECT a.*, u.nickname, u.biz_name, u.phone, u.is_agency FROM agency_applies a JOIN users u ON u.id = a.user_id
            {where} ORDER BY a.created_at DESC LIMIT %s OFFSET %s""", params + [per_page, (page - 1) * per_page])
    total = query_one(f"SELECT COUNT(*) AS n FROM agency_applies a {where}", params)["n"]
    return rows, total


def review_apply(apply_id, approve, admin_id):
    a = query_one("SELECT * FROM agency_applies WHERE id = %s", [apply_id])
    if not a:
        return None
    execute("UPDATE agency_applies SET status = %s, reviewed_by = %s WHERE id = %s", ["approved" if approve else "rejected", admin_id, apply_id])
    execute("UPDATE users SET is_agency = %s WHERE id = %s", [1 if approve else 0, a["user_id"]])
    if approve:
        execute("UPDATE users SET grade = 'agency' WHERE id = %s AND grade = 'biz'", [a["user_id"]])
    return a


def pending_applies_count():
    return query_one("SELECT COUNT(*) AS n FROM agency_applies WHERE status = 'pending'")["n"]
