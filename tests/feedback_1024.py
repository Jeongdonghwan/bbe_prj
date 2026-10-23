"""2026-10-24 피드백 묶음 회귀. python tests/feedback_1024.py

  - 인기 트래픽 드로어의 기성 매체 카카오 버튼 주소가 비어 있지 않다 (매크로 import with context)
  - 오늘의 인기 7개 이상은 저장 거절 (예전엔 앞 6개만 말없이 저장)
  - 운영자 로그인은 next 와 상관없이 운영 현황으로
  - 질문답변 비밀문의: 목록 제목 가림 · 남은 못 봄 · 남은 답변 못 담 · 운영 현황 문의 큐에 뜸
  - 익명 게시판 좋아요 버튼 + 토글
  - 전체 캠페인 관리(/campaign/all) · 쿠팡 캠페인 만들기 → 카카오
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from werkzeug.security import generate_password_hash  # noqa: E402

from app import create_app  # noqa: E402
from app.db import execute, query, query_one  # noqa: E402
from app.models import post as post_model  # noqa: E402
from app.models import user as user_model  # noqa: E402

app = create_app(); app.config["TESTING"] = True
app.config["MM_ALIGO_USER_ID"] = ""
fails = []


def ok(c, name, extra=""):
    print(("PASS " if c else "FAIL ") + name + (f"  → {extra}" if extra and not c else ""))
    c or fails.append(name)


def member(email, nick):
    with app.app_context():
        u = user_model.get_by_email(email)
        uid = u["id"] if u else user_model.create_local(email, generate_password_hash("x1234567"), nick, "010-0000-0000", False)
    c = app.test_client()
    with c.session_transaction() as s:
        s["uid"] = uid
    return c, uid


admin = app.test_client()
r = admin.post("/auth/admin/login?next=/admin/operators", data={"email": "admin", "password": "1234"})
ok(r.headers.get("Location", "").endswith("/admin"), "운영자 로그인 → 운영 현황", r.headers.get("Location"))

# 1) 기성 매체 카카오 버튼
with app.app_context():
    ready = query_one("SELECT id FROM media WHERE origin='ready' AND is_active=1 ORDER BY id LIMIT 1")
href = re.findall(r'p-go" href="([^"]*)"', admin.get(f"/popular/drawer/{ready['id']}").get_data(as_text=True))
ok(href and href[0].startswith("http"), "기성 매체 카카오 버튼 주소", href)

# 2) 오늘의 인기 7개 거절
with app.app_context():
    ids = [str(r["id"]) for r in query("SELECT id FROM media WHERE channel='store' AND is_active=1 ORDER BY id LIMIT 7")]
    from datetime import date
    from app.models import daily_pick as pick_model
    before = pick_model.get("store", date.today())
admin.post("/admin/media/picks", data={"channel": "store", "type_ids": ids})
with app.app_context():
    ok(pick_model.get("store", date.today()) == before, "오늘의 인기 7개는 저장 안 됨")

# 3) 비밀문의
a, a_id = member("qa-secret-a@test.local", "비밀A")
b, _ = member("qa-secret-b@test.local", "비밀B")
a.post("/community/qna/write", data={"title": "비밀질문제목XYZ", "body": "비밀 본문입니다 다섯자", "secret": "1"})
with app.app_context():
    pid = query_one("SELECT id FROM posts WHERE title='비밀질문제목XYZ'")["id"]
ok(a.get(f"/community/qna/{pid}").status_code == 200, "작성자는 비밀문의를 본다")
ok(b.get(f"/community/qna/{pid}").status_code == 403, "남은 비밀문의를 못 본다")
ok("비밀질문제목XYZ" not in b.get("/community/qna").get_data(as_text=True), "목록에서 남에게 제목이 가려진다")
ok(b.post(f"/community/qna/{pid}/comment", data={"body": "남이 다는 답"}).status_code == 403, "남은 비밀문의에 답 못 단다")
ok(admin.get(f"/community/qna/{pid}").status_code == 200, "운영팀은 본다")
ok("비밀질문제목XYZ" in admin.get("/admin?tab=ask").get_data(as_text=True), "운영 현황 문의 큐에 뜬다")
admin.post(f"/community/qna/{pid}/comment", data={"body": "운영팀 답변입니다"})
ok("비밀질문제목XYZ" not in admin.get("/admin?tab=ask").get_data(as_text=True), "운영팀이 답하면 큐에서 빠진다")

# 4) 좋아요
with app.app_context():
    anon = query_one("SELECT p.id, p.likes FROM posts p JOIN boards bd ON bd.id=p.board_id WHERE bd.slug='anon' AND p.is_blind=0 ORDER BY p.id DESC LIMIT 1")
ok('id="likeBtn"' in b.get(f"/community/anon/{anon['id']}").get_data(as_text=True), "익명글 상세에 좋아요 버튼")
j1 = b.post(f"/community/anon/{anon['id']}/like").get_json()
j2 = b.post(f"/community/anon/{anon['id']}/like").get_json()
ok(j1["liked"] and not j2["liked"] and j2["likes"] == anon["likes"], "좋아요 토글", (j1, j2))

# 5) 전체 캠페인 관리 · 쿠팡
h = a.get("/campaign/all")
ok(h.status_code == 200 and "전체 캠페인 관리" in h.get_data(as_text=True), "/campaign/all")
r = a.get("/campaign/coupang/new")
ok(r.status_code == 302 and "kakao" in r.headers.get("Location", ""), "쿠팡 캠페인 만들기 → 카카오", r.headers.get("Location"))
ok(a.get("/campaign/store/new").status_code == 200, "쇼핑 위저드는 그대로")

# cleanup
with app.app_context():
    post_model.purge(pid)
    for e in ("qa-secret-a@test.local", "qa-secret-b@test.local"):
        u = user_model.get_by_email(e)
        if u:
            execute("DELETE FROM notifications WHERE user_id = %s", [u["id"]])
            execute("DELETE FROM post_likes WHERE user_id = %s", [u["id"]])
            execute("DELETE FROM nick_registry WHERE user_id = %s", [u["id"]]) if query_one("SHOW TABLES LIKE 'nick_registry'") else None
            try:
                execute("DELETE FROM users WHERE id = %s", [u["id"]])
            except Exception as ex:   # 다른 테이블이 참조하면 남겨 둔다(로컬 테스트 계정)
                print("  (계정 정리 건너뜀:", type(ex).__name__, ")")

print("\n" + ("전부 통과" if not fails else f"{len(fails)}건 실패: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
