"""회원 취소·중단 환불 규칙 (2026-11-02 JDH). python tests/refund_rule.py

  - 구동 시작 전(시작일 전날 23:59 까지, 승인 여부 무관): 전액 환불 취소
  - 구동 시작일부터 3일: 중단·환불 불가 (서버가 거절, 안내는 팝업)
  - 그 이후: 잔여일분 환불하고 중단
  - 위저드 최소 기간 3일 · 매체 섹션으로 자체/기성 구분
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app  # noqa: E402
from app.db import execute, query, query_one  # noqa: E402
from app.models import campaign as campaign_model  # noqa: E402
from app.services import campaign_service  # noqa: E402

app = create_app(); app.config["TESTING"] = True
app.config["MM_ALIGO_USER_ID"] = ""
NAME = "환불규칙테스트"
fails = []


def ok(c, name, extra=""):
    print(("PASS " if c else "FAIL ") + name + (f"  → {extra}" if extra and not c else ""))
    c or fails.append(name)


def cleanup():
    with app.app_context():
        for r in query("SELECT id FROM campaigns WHERE biz_name LIKE %s", [NAME + "%"]):
            campaign_model.purge(r["id"])


cleanup()
with app.app_context():
    uid = query_one("SELECT id FROM users WHERE role <> 'admin' AND status = 'active' ORDER BY id LIMIT 1")["id"]
    media = query_one("SELECT id, unit_price FROM media WHERE channel = 'store' AND is_active = 1 AND origin = 'own' ORDER BY sort LIMIT 1")
    start = campaign_service.earliest_start()
    execute("UPDATE users SET credit_balance = credit_balance + 10000000 WHERE id = %s", [uid])
    bal0 = query_one("SELECT credit_balance FROM users WHERE id = %s", [uid])["credit_balance"]
user = app.test_client()
with user.session_transaction() as s:
    s["uid"] = uid


def make(suffix, days=10):
    user.post("/campaign/store/new", data={
        "confirm": "1", "media_id": media["id"], "days": str(days), "daily_qty": "100", "product_name": NAME + suffix,
        "target_url": f"https://smartstore.naver.com/x/products/{abs(hash(suffix)) % 10**9}",
        "main_keyword": NAME + suffix, "start_date": start.isoformat(),
        "client_total": str(media["unit_price"] * 100 * days)})
    with app.app_context():
        return query_one("SELECT * FROM campaigns WHERE biz_name = %s", [NAME + suffix])


# 1) 판정 함수 — 구동 시작일 기준 (2026-11-03 JDH)
from datetime import date as _d  # noqa: E402
with app.app_context():
    c = make("A")
    ok(c is not None, "캠페인 등록")
    base = {**c, "created_at": datetime(2026, 11, 2, 10, 0)}
    # 예 1) 11/2 승인 · 11/3 구동 → 11/2 23:59 까지 전액, 11/3~11/5 잠금, 11/6 부터 중단
    e1 = {**base, "status": "running", "start_date": _d(2026, 11, 3)}
    ok(campaign_service.refund_rule(e1, datetime(2026, 11, 2, 23, 59))[0] == "full", "예1) 11/2 23:59 → 전액 취소")
    r, unlock = campaign_service.refund_rule(e1, datetime(2026, 11, 3, 0, 1))
    ok(r == "locked" and unlock == _d(2026, 11, 6), "예1) 구동일 11/3 → 잠금, 11/6 부터", (r, unlock))
    ok(campaign_service.refund_rule(e1, datetime(2026, 11, 5, 23, 0))[0] == "locked", "예1) 11/5 → 아직 잠금")
    ok(campaign_service.refund_rule(e1, datetime(2026, 11, 6, 0, 0))[0] == "normal", "예1) 11/6 → 중단 가능")
    # 예 2) 11/2 신청 · 11/3 승인 · 11/4 구동 → 11/3 23:59 까지 전액
    e2 = {**base, "status": "running", "start_date": _d(2026, 11, 4)}
    ok(campaign_service.refund_rule(e2, datetime(2026, 11, 3, 23, 59))[0] == "full", "예2) 승인 다음 날이라도 구동 전날 23:59 → 전액")
    ok(campaign_service.refund_rule(e2, datetime(2026, 11, 4, 9, 0))[0] == "locked", "예2) 구동일 11/4 → 잠금")
    ok(campaign_service.refund_rule({**base, "status": "review", "start_date": _d(2026, 11, 3)}, datetime(2026, 11, 5))[0] == "full",
       "검수 중(한 번도 안 돎)이면 시작일이 지나도 전액")
    old = {**c, "created_at": datetime(2026, 10, 1, 9, 0)}
    ok(campaign_service.refund_rule(old, datetime(2026, 10, 1, 15, 0))[0] == "normal", "규칙 전 접수 건은 예전대로")

campaign_service.REFUND_POLICY_FROM = datetime(2026, 1, 1)   # 화면 검사는 오늘 만든 캠페인으로

# 2) 승인 뒤(정상·시작 전) 하루 지나도 구동 전이면 전액 취소 — 화면 경로
admin = app.test_client()
admin.post("/auth/admin/login", data={"email": "admin", "password": "1234"})
admin.post(f"/admin/orders/{c['id']}/action", data={"action": "approve"})
with app.app_context():
    execute("UPDATE campaigns SET created_at = %s WHERE id = %s", [datetime.now() - timedelta(days=1), c["id"]])
    ok(campaign_model.get(c["id"])["status"] == "running", "준비: 어제 접수·승인, 내일 구동")
user.post(f"/campaign/store/{c['id']}/cancel")
with app.app_context():
    c2 = campaign_model.get(c["id"])
ok(c2["status"] == "cancelled" and c2["refund_amount"] == c2["paid_amount"], "구동 전이면 승인 뒤에도 전액 취소",
   (c2["status"], c2["refund_amount"], c2["paid_amount"]))

# 3) 구동 중 중단 — 시작일부터 3일은 거절(팝업), 지나면 잔여일분
with app.app_context():
    d = make("B")
    execute("UPDATE campaigns SET status='running', start_date = DATE_SUB(CURDATE(), INTERVAL 1 DAY), "
            "end_date = DATE_ADD(CURDATE(), INTERVAL 8 DAY) WHERE id = %s", [d["id"]])
h = user.post(f"/campaign/store/{d['id']}/stop", follow_redirects=True).get_data(as_text=True)
with app.app_context():
    ok(campaign_model.get(d["id"])["status"] == "running", "구동 2일째 → 중단 안 됨")
ok('id="flashPop"' in h and "최소 작업일수는 3일" in h, "잠금 안내는 팝업")
with app.app_context():
    execute("UPDATE campaigns SET start_date = DATE_SUB(CURDATE(), INTERVAL 3 DAY) WHERE id = %s", [d["id"]])
user.post(f"/campaign/store/{d['id']}/stop")
with app.app_context():
    d2 = campaign_model.get(d["id"])
ok(d2["status"] == "stopped" and 0 < d2["refund_amount"] < d2["paid_amount"], "구동 4일째 중단 → 잔여일분 환불",
   (d2["status"], d2["refund_amount"]))

# 4) 최소 기간 3일
with app.app_context():
    e = make("C", days=2)
ok(e is None, "2일짜리는 접수 안 됨 (최소 작업일수 3일)")

# 5) 매체 섹션 → 자체/기성
from app.constants import section_kind  # noqa: E402
ok(section_kind("자체 · 리워드") == ("own", "reward") and section_kind("자체 · 유입플") == ("own", "inflow")
   and section_kind("자체 프로그램") == ("own", None) and section_kind("기성") == ("ready", None), "섹션 → 자체/기성 구분")

cleanup()
with app.app_context():
    for r in query("""SELECT l.id FROM credit_ledger l LEFT JOIN campaigns c ON c.id = l.ref_id
                      WHERE l.ref_type = 'campaign' AND c.id IS NULL"""):
        execute("DELETE FROM credit_ledger WHERE id = %s", [r["id"]])
    execute("UPDATE users u SET credit_balance = COALESCE((SELECT SUM(amount) FROM credit_ledger WHERE user_id = u.id), 0) WHERE u.id = %s", [uid])
print("\n" + ("전부 통과" if not fails else f"{len(fails)}건 실패: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
