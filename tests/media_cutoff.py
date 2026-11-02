"""매체별 접수 마감 (2026-11-02 JDH). python tests/media_cutoff.py

  - 마감 시각부터 자정까지 그 매체는 위저드에서 회색·선택 불가, 서버도 접수 거절
  - 마감 전이거나 마감이 없는 매체는 그대로
  - 주말 칸이 비면 평일 시각을 쓴다
"""
import os
import sys
from datetime import datetime, time, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app  # noqa: E402
from app.db import execute, query_one  # noqa: E402
from app.models import media as media_model  # noqa: E402

app = create_app(); app.config["TESTING"] = True
fails = []


def ok(c, name, extra=""):
    print(("PASS " if c else "FAIL ") + name + (f"  → {extra}" if extra and not c else ""))
    c or fails.append(name)


# 판정 함수
m = {"cutoff_time": timedelta(hours=17), "cutoff_weekend": None}
ok(not media_model.is_closed(m, datetime(2026, 11, 2, 16, 59)), "월 16:59 → 열림")
ok(media_model.is_closed(m, datetime(2026, 11, 2, 17, 0)), "월 17:00 → 마감")
ok(media_model.is_closed(m, datetime(2026, 11, 2, 23, 59)), "월 23:59 → 마감")
ok(not media_model.is_closed(m, datetime(2026, 11, 3, 0, 0)), "다음 날 00:00 → 다시 열림")
m2 = {"cutoff_time": timedelta(hours=17), "cutoff_weekend": timedelta(hours=10)}
ok(media_model.is_closed(m2, datetime(2026, 11, 7, 10, 30)), "토 10:30 (주말 10시 마감) → 마감")
ok(not media_model.is_closed(m2, datetime(2026, 11, 6, 10, 30)), "금 10:30 (평일 17시) → 열림")
ok(media_model.is_closed(m, datetime(2026, 11, 7, 17, 30)), "주말 칸 비면 평일 시각 → 토 17:30 마감")
ok(not media_model.is_closed({"cutoff_time": None, "cutoff_weekend": None}), "마감 없음 → 항상 열림")

# 화면·서버
with app.app_context():
    uid = query_one("SELECT id FROM users WHERE role <> 'admin' AND status = 'active' ORDER BY id LIMIT 1")["id"]
    md = query_one("SELECT id, name, unit_price, cutoff_time, cutoff_weekend FROM media WHERE channel='store' AND origin='own' AND is_active=1 ORDER BY sort LIMIT 1")
    past = (datetime.now() - timedelta(minutes=1)).time().replace(second=0, microsecond=0)
    if datetime.now().time() < time(0, 2):
        print("자정 직후라 화면 검사는 건너뜀")
        sys.exit(1 if fails else 0)
    execute("UPDATE media SET cutoff_time = %s, cutoff_weekend = %s WHERE id = %s", [past, past, md["id"]])
c = app.test_client()
with c.session_transaction() as s:
    s["uid"] = uid
try:
    h = c.get("/campaign/store/new").get_data(as_text=True)
    i = h.index(f'data-id="{md["id"]}"')
    card = h[h.rfind("<button", 0, i):h.index("</button>", i)]
    ok("w-closed" in card and "disabled" in card and "오늘 접수 마감" in card, "마감된 매체 카드는 회색·선택 불가", card[:160])
    from app.services import campaign_service
    r = c.post("/campaign/store/new", data={"confirm": "1", "media_id": md["id"], "days": "10", "daily_qty": "100",
                                           "target_url": "https://smartstore.naver.com/x/products/99887766", "main_keyword": "마감검사",
                                           "start_date": campaign_service.earliest_start().isoformat(),
                                           "client_total": str(md["unit_price"] * 1000)}, follow_redirects=True)
    with app.app_context():
        made = query_one("SELECT id FROM campaigns WHERE main_keyword = '마감검사'")
    ok(made is None and "접수가 마감" in r.get_data(as_text=True), "마감된 매체 접수는 서버가 거절")
finally:
    with app.app_context():
        execute("UPDATE media SET cutoff_time = %s, cutoff_weekend = %s WHERE id = %s", [md["cutoff_time"], md["cutoff_weekend"], md["id"]])
        if made:
            from app.models import campaign as cm
            cm.purge(made["id"])
print("\n" + ("전부 통과" if not fails else f"{len(fails)}건 실패: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
