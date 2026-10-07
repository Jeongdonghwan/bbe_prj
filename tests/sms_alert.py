"""운영자 문자 알림 (알리고) — 스텁 서버로 발송 내용 확인. python tests/sms_alert.py"""
import os
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app  # noqa: E402
from app.db import execute, query_one  # noqa: E402
from app.services import sms  # noqa: E402

SENT = []


class Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        SENT.append(dict(urllib.parse.parse_qsl(self.rfile.read(int(self.headers["Content-Length"])).decode())))
        out = b'{"result_code":"1","message":"success","msg_id":"1"}'
        self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 5099), Stub)
threading.Thread(target=srv.serve_forever, daemon=True).start()
sms.SEND_URL = "http://127.0.0.1:5099/send/"

app = create_app(); app.config["TESTING"] = True
fails = []


def ok(c, name):
    print(("PASS " if c else "FAIL ") + name); c or fails.append(name)


def wait():
    for _ in range(40):
        if SENT:
            return
        time.sleep(0.05)


# 설정이 없으면 아무것도 안 보낸다
for k in ("MM_ALIGO_USER_ID", "MM_ALIGO_API_KEY", "MM_ALIGO_SENDER", "MM_ALIGO_ADMIN_PHONES"):
    app.config[k] = ""
with app.app_context():
    ok(sms.notify_admins("x") is False, "미설정 → 발송 안 함")

app.config.update(MM_ALIGO_USER_ID="mmuser", MM_ALIGO_API_KEY="mmkey", MM_ALIGO_SENDER="010-1111-2222",
                  MM_ALIGO_ADMIN_PHONES="010-3333-4444, 010-5555-6666", MM_ALIGO_TEST_MODE="Y")
with app.app_context():
    u = query_one("SELECT id FROM users WHERE role='user' AND status='active' ORDER BY id LIMIT 1")
tc = app.test_client()
with tc.session_transaction() as s:
    s["uid"] = u["id"]
tc.post("/credit/charge", data={"confirm": "1", "amount": "10000", "depositor": "문자테스트"})
wait()
m = SENT[0] if SENT else {}
ok(m.get("userid") == "mmuser" and m.get("key") == "mmkey", "MM_ALIGO_* 계정으로 발송 (raws 의 ALIGO_* 아님)")
ok(m.get("sender") == "01011112222" and m.get("receiver") == "01033334444,01055556666", "발신·수신 번호 정규화, 여러 명")
ok("크레딧 충전 요청" in m.get("msg", "") and m.get("testmode_yn") == "Y", "충전 요청 문구 · 테스트 모드")

# 결제 완료처럼 sms=False 인 알림은 문자 없음
SENT.clear()
with app.test_request_context():
    from app.services.notify_service import notify_admins
    notify_admins("결제 완료 · 테스트", "/admin")
time.sleep(0.3)
ok(not SENT, "sms=False 알림은 문자 안 보냄")

with app.app_context():
    execute("DELETE FROM charge_requests WHERE depositor='문자테스트'")
    execute("DELETE FROM notifications WHERE type='admin' AND (title LIKE %s OR title LIKE %s)", ["%문자테스트%", "결제 완료 · 테스트"])
srv.shutdown()
print("\n" + ("전부 통과" if not fails else f"{len(fails)}건 실패: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
