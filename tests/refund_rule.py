"""회원 취소·중단 환불 규칙 (2026-11-02 JDH). python tests/refund_rule.py

  - 접수한 날(23:59 까지): 전액 환불 취소
  - 접수일 포함 3일: 중단·환불 불가 (서버가 거절)
  - 그 이후: 구동 전이면 전액 취소, 구동 중이면 잔여일분 중단
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


# 1) 판정 함수
with app.app_context():
    c = make("A")
    ok(c is not None, "캠페인 등록")
    created = c["created_at"]
    day0 = created.replace(hour=9, minute=0)
    c9 = {**c, "created_at": day0}
    ok(campaign_service.refund_rule(c9, day0.replace(hour=23, minute=59))[0] == "full", "접수 당일 23:59 → 전액")
    r, unlock = campaign_service.refund_rule(c9, day0 + timedelta(hours=15, minutes=1))
    ok(r == "locked" and unlock == day0.date() + timedelta(days=3), "다음 날 00:01 → 3일 잠금", (r, unlock))
    ok(campaign_service.refund_rule(c9, day0 + timedelta(days=2, hours=10))[0] == "locked", "접수 3일째 → 잠금")
    ok(campaign_service.refund_rule(c9, day0 + timedelta(days=3))[0] == "normal", "접수 4일째 → 가능")
    old = {**c, "created_at": datetime(2026, 10, 1, 9, 0)}
    ok(campaign_service.refund_rule(old, datetime(2026, 10, 1, 15, 0))[0] == "normal", "규칙 전 접수 건은 예전대로")

# 2) 화면 경로 — 잠금 기간에 접수한 것으로 맞춘다 (어제 접수)
campaign_service.REFUND_POLICY_FROM = datetime(2026, 1, 1)   # 배포 당일에도 '어제 접수'가 새 규칙을 타게


def locked_created():
    return datetime.now() - timedelta(days=1)


with app.app_context():
    execute("UPDATE campaigns SET created_at = %s WHERE id = %s", [locked_created(), c["id"]])
    ok(campaign_service.refund_rule(campaign_model.get(c["id"]))[0] == "locked", "준비: 잠금 상태")
user.post(f"/campaign/store/{c['id']}/cancel")
with app.app_context():
    ok(campaign_model.get(c["id"])["status"] == "review", "잠금 기간엔 취소 안 됨")
    # 4일 전 접수 + 구동 전 → 전액 취소
    execute("UPDATE campaigns SET created_at = %s WHERE id = %s", [datetime.now() - timedelta(days=4), c["id"]])
user.post(f"/campaign/store/{c['id']}/cancel")
with app.app_context():
    c2 = campaign_model.get(c["id"])
ok(c2["status"] == "cancelled" and c2["refund_amount"] == c2["paid_amount"], "잠금 후 구동 전 취소 → 전액 환불",
   (c2["status"], c2["refund_amount"], c2["paid_amount"]))

# 3) 구동 중 중단 — 잠금이면 거절, 지나면 잔여일분
with app.app_context():
    d = make("B")
    execute("UPDATE campaigns SET status='running', start_date = DATE_SUB(CURDATE(), INTERVAL 1 DAY), end_date = DATE_ADD(CURDATE(), INTERVAL 8 DAY), "
            "created_at = %s WHERE id = %s", [locked_created(), d["id"]])
user.post(f"/campaign/store/{d['id']}/stop")
with app.app_context():
    ok(campaign_model.get(d["id"])["status"] == "running", "잠금 기간엔 중단 안 됨")
    execute("UPDATE campaigns SET created_at = %s WHERE id = %s", [datetime.now() - timedelta(days=5), d["id"]])
user.post(f"/campaign/store/{d['id']}/stop")
with app.app_context():
    d2 = campaign_model.get(d["id"])
ok(d2["status"] == "stopped" and 0 < d2["refund_amount"] < d2["paid_amount"], "잠금 후 중단 → 잔여일분 환불",
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
