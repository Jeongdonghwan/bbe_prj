"""캠페인 상태 흐름 단축 + 등록 즉시 순위 추적 검증.

    python tests/status_flow.py

확인하는 것 (2026-09-25 JDH "과정을 줄여라"):
  1. 등록 → 검수. 결제 대기 단계는 크레딧 모델에 없다.
  2. 승인했을 때 시작일이 아직 안 왔으면 "구동 대기", 이미 왔으면 그 자리에서 "진행".
  3. 시작일이 되면 크론(advance_due)이 구동으로, 종료일이 지나면 완료로 알아서 넘긴다.
  4. 운영자가 승인하기 전, 등록되는 순간 순위 추적 슬롯이 생긴다.
"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.db import execute, query, query_one  # noqa: E402
from app.models import campaign as campaign_model  # noqa: E402
from app.services import campaign_service  # noqa: E402

NAMES = ("상태흐름A", "상태흐름B", "추적즉시")
fails = []


def ok(cond, name, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  → {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def register(client, media, start, name, keyword, total):
    client.post("/campaign/store/new", data={
        "media_id": media["id"], "days": "30", "daily_qty": "100", "product_name": name,
        "target_url": f"https://smartstore.naver.com/x/products/{abs(hash(name)) % 10**9}",
        "main_keyword": keyword, "start_date": start.isoformat(), "client_total": str(total),
    }, follow_redirects=True)
    return query_one("SELECT * FROM campaigns WHERE biz_name = %s", [name])


def cleanup(app):
    with app.app_context():
        rows = query("SELECT id, user_id FROM campaigns WHERE biz_name IN %s", [NAMES])
        for r in rows:
            campaign_model.purge(r["id"])
        for r in query("""SELECT l.id FROM credit_ledger l LEFT JOIN campaigns c ON c.id = l.ref_id
                          WHERE l.ref_type = 'campaign' AND c.id IS NULL"""):
            execute("DELETE FROM credit_ledger WHERE id = %s", [r["id"]])
        for uid in {r["user_id"] for r in rows}:
            execute("""UPDATE users u SET credit_balance =
                       COALESCE((SELECT SUM(amount) FROM credit_ledger WHERE user_id = u.id), 0)
                       WHERE u.id = %s""", [uid])


class StubRank(BaseHTTPRequestHandler):
    """순위 서버 대역 — 무엇이 등록됐는지만 받아 적는다."""

    seen = []

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        StubRank.seen.append(json.loads(self.rfile.read(n) or b"{}"))
        body = json.dumps({"ok": True, "trackId": 7001, "status": "queued",
                           "rank": None, "prodNm": None, "date": None}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def main():
    app = create_app()
    app.config["TESTING"] = True
    cleanup(app)

    with app.app_context():
        uid = query_one("SELECT id FROM users WHERE role <> 'admin' AND status = 'active' ORDER BY id LIMIT 1")["id"]
        media = query_one("SELECT id, unit_price FROM media WHERE channel = 'store' AND is_active = 1 ORDER BY sort LIMIT 1")
        start = campaign_service.earliest_start()
        execute("UPDATE users SET credit_balance = credit_balance + %s WHERE id = %s", [20_000_000, uid])
    total = media["unit_price"] * 100 * 30
    user = app.test_client()
    with user.session_transaction() as s:
        s["uid"] = uid

    print("=== 1. 등록 → 검수 (결제 대기 없음) ===")
    with app.app_context():
        a = register(user, media, start, "상태흐름A", "상태흐름A키워드", total)
    ok(a and a["status"] == "review", "등록 직후 검수", (a or {}).get("status"))
    ok(a and a["pay_method"] == "credit", "크레딧 결제로 기록", (a or {}).get("pay_method"))

    print("\n=== 2. 승인 — 시작일 전이면 구동 대기 ===")
    with app.app_context():
        campaign_service.transition(campaign_model.get(a["id"]), "approved", None, "테스트 승인")
        st = campaign_model.get(a["id"])["status"]
    ok(st == "approved", f"시작일 {a['start_date']} 이전이라 구동 대기", st)

    print("\n=== 3. 시작일 도래 → 자동 구동 / 종료일 경과 → 자동 완료 ===")
    with app.app_context():
        execute("UPDATE campaigns SET start_date = CURDATE() WHERE id = %s", [a["id"]])
        started, _ = campaign_service.advance_due()
        st = campaign_model.get(a["id"])["status"]
    ok(st == "running" and started == 1, "시작일 도래 → 진행", st)
    with app.app_context():
        execute("UPDATE campaigns SET end_date = DATE_SUB(CURDATE(), INTERVAL 1 DAY) WHERE id = %s", [a["id"]])
        _, finished = campaign_service.advance_due()
        st = campaign_model.get(a["id"])["status"]
        logs = [r["to_status"] for r in query("SELECT to_status FROM status_log WHERE campaign_id = %s ORDER BY id", [a["id"]])]
    ok(st == "done" and finished == 1, "종료일 경과 → 완료", st)
    ok(logs == ["review", "approved", "running", "done"], "이력 4단계", " → ".join(logs))

    print("\n=== 4. 시작일이 이미 지난 건은 승인 한 번으로 진행까지 ===")
    with app.app_context():
        b = register(user, media, start, "상태흐름B", "상태흐름B키워드", total)
        execute("UPDATE campaigns SET start_date = CURDATE() WHERE id = %s", [b["id"]])
        campaign_service.transition(campaign_model.get(b["id"]), "approved", None, "테스트 승인")
        st = campaign_model.get(b["id"])["status"]
        logs = [r["to_status"] for r in query("SELECT to_status FROM status_log WHERE campaign_id = %s ORDER BY id", [b["id"]])]
    ok(st == "running", "승인 = 진행 (구동 시작 버튼 불필요)", st)
    ok(logs == ["review", "approved", "running"], "승인 이력도 남는다", " → ".join(logs))

    print("\n=== 5. 등록 즉시 순위 추적 ===")
    srv = HTTPServer(("127.0.0.1", 5096), StubRank)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        app2 = create_app()
        app2.config.update(TESTING=True, RANK_SERVER_URL="http://127.0.0.1:5096", RANK_API_TOKEN="tk")
        u2 = app2.test_client()
        with u2.session_transaction() as s:
            s["uid"] = uid
        with app2.app_context():
            c = register(u2, media, start, "추적즉시", "추적즉시키워드", total)
        ok(c and c["status"] == "review" and c["track_id"] == 7001,
           "검수 단계에서 이미 추적 등록", f"status={(c or {}).get('status')} track={(c or {}).get('track_id')}")
        ok(StubRank.seen and StubRank.seen[0].get("keyword") == "추적즉시키워드",
           "순위 서버에 키워드 전달", StubRank.seen)
    finally:
        srv.shutdown()

    cleanup(app)
    print("\n" + ("전부 통과" if not fails else f"{len(fails)}건 실패: " + ", ".join(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
