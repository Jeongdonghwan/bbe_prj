"""사업자등록증 업로드 + 운영자 알림 (2026-10-07). python tests/admin_notify.py"""
import io
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image  # noqa: E402

from app import create_app  # noqa: E402
from app.db import execute, query, query_one  # noqa: E402

app = create_app(); app.config["TESTING"] = True
fails = []


def ok(c, name):
    print(("PASS " if c else "FAIL ") + name)
    c or fails.append(name)


def png():
    b = io.BytesIO(); Image.new("RGB", (20, 10), "white").save(b, "PNG"); return io.BytesIO(b.getvalue())


with app.app_context():
    admin = query_one("SELECT id FROM users WHERE role='admin' AND status='active' ORDER BY id LIMIT 1")
    start = query_one("SELECT COALESCE(MAX(id),0) m FROM notifications")["m"]

# 국세청 상태조회 — 스텁 서버로 응답 형식을 흉내 낸다 (실제 키 없이)
import json, threading  # noqa: E401,E402
from http.server import BaseHTTPRequestHandler, HTTPServer  # noqa: E402
from app.services import nts  # noqa: E402
CODES = {"2208162517": "01", "1248100998": "03"}   # 나머지는 미등록


class Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        b_no = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["b_no"][0]
        out = json.dumps({"data": [{"b_no": b_no, "b_stt_cd": CODES.get(b_no, "")}]}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 5098), Stub)
threading.Thread(target=srv.serve_forever, daemon=True).start()
nts.URL = "http://127.0.0.1:5098/status"
app.config["DATA_GO_KR_KEY"] = "stub+key/="
tc0 = app.test_client()
ok(tc0.get("/auth/biz-check?b_no=220-81-62517").get_json()["ok"] is True, "진위확인: 계속사업자 통과")
ok(tc0.get("/auth/biz-check?b_no=124-81-00998").get_json()["ok"] is False, "진위확인: 폐업자 거절")
ok(tc0.get("/auth/biz-check?b_no=120-81-47521").get_json()["label"] == "국세청에 등록되지 않은 번호", "진위확인: 미등록")
nts.URL = "http://127.0.0.1:1/down"; nts._CACHE.clear()
ok(tc0.get("/auth/biz-check?b_no=220-81-62517").get_json()["ok"] is True, "국세청 장애 → 막지 않음")
nts.URL = "http://127.0.0.1:5098/status"; nts._CACHE.clear()

email = f"certtest{int(time.time())}@example.com"
tc = app.test_client()
form = {"email": email, "password": "password123", "password2": "password123", "nickname": "인증테스트",
        "phone": "010-1234-5678", "agree_terms": "1", "agree_privacy": "1",
        "biz_name": "인증테스트상사", "biz_no": "2208162517"}
# 상호·사업자번호는 필수, 번호는 검증번호까지 본다
for bad, name in (({"biz_name": ""}, "상호 없음 → 거절"), ({"biz_no": "123-45-67890"}, "검증번호 틀림 → 거절"),
                  ({"biz_no": "124-81-00998"}, "폐업 사업자 → 가입 거절")):
    r = tc.post("/auth/register", data={**form, **bad}, content_type="multipart/form-data")
    with app.app_context():
        ok(r.status_code == 400 and not query_one("SELECT id FROM users WHERE email=%s", [email]), name)
# 잘못된 파일이면 회원이 만들어지지 않는다
r = tc.post("/auth/register", data={**form, "biz_cert": (io.BytesIO(b"nope"), "x.jpg")}, content_type="multipart/form-data")
with app.app_context():
    ok(r.status_code == 400 and not query_one("SELECT id FROM users WHERE email=%s", [email]), "잘못된 이미지 → 가입 거절")
r = tc.post("/auth/register", data={**form, "biz_cert": (png(), "cert.png")}, content_type="multipart/form-data")
with app.app_context():
    u = query_one("SELECT * FROM users WHERE email=%s", [email])
    ok(r.status_code == 302 and u and u["biz_cert_status"] == "pending" and u["biz_cert_file"], "가입 + 등록증 → pending")
    ok(u["biz_name"] == "인증테스트상사" and u["biz_no"] == "220-81-62517", "상호·사업자번호 저장 (하이픈 정규화)")
    titles = [n["title"] for n in query("SELECT title FROM notifications WHERE id > %s AND user_id = %s", [start, admin["id"]])]
    ok(any("신규 회원가입" in t for t in titles) and any("사업자 인증 요청" in t for t in titles), "운영자 알림: 가입·인증")

# 충전 요청 알림
r = tc.post("/credit/charge", data={"confirm": "1", "amount": "10000", "depositor": "홍길동"})
with app.app_context():
    ok(query_one("SELECT 1 x FROM notifications WHERE id > %s AND user_id=%s AND title LIKE %s",
                 [start, admin["id"], "크레딧 충전 요청%"]) is not None, "운영자 알림: 충전 요청")

# 어드민: 원본 보기 · 승인
at = app.test_client()
with at.session_transaction() as s:
    s["uid"] = admin["id"]
r = at.get(f"/admin/users/{u['id']}/biz-cert")
ok(r.status_code == 200 and r.mimetype == "image/png", "어드민 원본 보기")
r.close()   # send_file 이 파일을 잡고 있다 (Windows 에선 지우기 전에 닫아야 함)
ok(tc.get(f"/admin/users/{u['id']}/biz-cert").status_code in (302, 403), "회원은 원본 못 봄")
ok(b"/biz-cert" in at.get(f"/admin/users/{u['id']}/drawer").data, "드로어에 등록증 섹션")
ok("인증 대기" in at.get("/admin/users?cert=pending").get_data(as_text=True), "인증 대기 탭")
at.post(f"/admin/users/{u['id']}/biz-cert", data={"action": "approve"})
with app.app_context():
    ok(query_one("SELECT biz_cert_status s FROM users WHERE id=%s", [u["id"]])["s"] == "approved", "승인")
    # 정리
    from app.services import biz_cert
    os.remove(biz_cert.path(u["biz_cert_file"]))
    execute("DELETE FROM notifications WHERE user_id=%s OR id > %s AND (title LIKE %s OR title LIKE %s)",
            [u["id"], start, "%인증테스트%", "%certtest%"])
    execute("DELETE FROM charge_requests WHERE user_id=%s", [u["id"]])
    execute("DELETE FROM admin_log WHERE target_id=%s AND action LIKE 'biz_cert%%'", [u["id"]])
    execute("DELETE FROM users WHERE id=%s", [u["id"]])

print("\n" + ("전부 통과" if not fails else f"{len(fails)}건 실패: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
