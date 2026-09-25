"""운영 점검 — 권한 경계. 비로그인·남의 자료·일반회원의 어드민 접근이 막히는지."""
import os
import sys

os.chdir(r"C:\bbe_prj")
sys.path.insert(0, r"C:\bbe_prj")

from app import create_app  # noqa: E402
from app.db import query, query_one  # noqa: E402

FAIL = []


def check(cond, name, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (("  → " + str(extra)) if (extra and not cond) else ""))
    if not cond:
        FAIL.append(name)


def main():
    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        aid = query_one("SELECT id FROM users WHERE role='admin' LIMIT 1")["id"]
        users = query("SELECT id FROM users WHERE role<>'admin' AND status='active' ORDER BY id LIMIT 2")
        u1, u2 = users[0]["id"], users[1]["id"]
        camp = query_one("SELECT id, channel FROM campaigns WHERE user_id=%s ORDER BY id DESC LIMIT 1", [u1])

    anon = app.test_client()
    member = app.test_client()
    other = app.test_client()
    with member.session_transaction() as s:
        s["uid"] = u1
    with other.session_transaction() as s:
        s["uid"] = u2

    print("=== 1. 비로그인 차단 (로그인 화면으로) ===")
    for u in ["/my", "/campaign/store", "/campaign/store/new", "/credit/charge", "/tools/keyword",
              "/campaign/store/slots", "/notifications", "/my/posts"]:
        r = anon.get(u)
        check(r.status_code == 302 and "/auth/login" in r.headers.get("Location", ""), f"비로그인 {u}", r.status_code)

    print("\n=== 2. 비로그인 쓰기 차단 ===")
    for u, d in [("/community/anon/write", {"title": "x" * 10, "body": "y" * 20}),
                 ("/popular/review", {"type_id": "1", "campaign_id": "1", "stars": "5", "body": "z" * 20}),
                 ("/my/biz", {"biz_name": "x"})]:
        r = anon.post(u, data=d)
        check(r.status_code == 302 and "/auth/login" in r.headers.get("Location", ""), f"비로그인 POST {u}", r.status_code)

    print("\n=== 3. 공개 화면은 열려 있어야 ===")
    for u in ["/", "/notice", "/popular", "/community/info", "/terms", "/privacy", "/auth/login"]:
        check(anon.get(u).status_code == 200, f"공개 {u}")

    print("\n=== 4. 어드민 진입 ===")
    for u in ["/admin", "/admin/orders", "/admin/credits"]:
        r = anon.get(u)
        check(r.status_code == 302 and "/auth/admin/login" in r.headers.get("Location", ""),
              f"비로그인 → {u} 운영자 로그인으로", r.headers.get("Location"))
    for u in ["/admin", "/admin/orders", "/admin/credits", "/admin/media", "/admin/users"]:
        r = member.get(u)
        check(r.status_code == 403, f"회원 → {u} 403", r.status_code)
    r = member.post("/admin/credits/adjust", data={"user_id": u1, "amount": "999999", "memo": "탈취"})
    check(r.status_code == 403, "회원의 크레딧 조작 차단", r.status_code)
    with app.app_context():
        bal = query_one("SELECT credit_balance FROM users WHERE id=%s", [u1])["credit_balance"]
    check(bal < 900000, "잔액 변화 없음", bal)

    print("\n=== 5. 남의 캠페인 접근 ===")
    if camp:
        r = other.get(f"/campaign/{camp['channel']}/{camp['id']}/drawer")
        check(r.status_code in (403, 404), "남의 캠페인 상세 차단", r.status_code)
        r = other.post(f"/campaign/{camp['channel']}/{camp['id']}/stop")
        check(r.status_code in (403, 404), "남의 캠페인 중단 차단", r.status_code)

    print("\n=== 6. 순위 콜백 토큰 ===")
    r = anon.post("/api/rank/callback", json={"trackId": 1, "date": "2026-09-24", "rank": 3})
    check(r.status_code == 401, "토큰 없는 콜백 401", r.status_code)

    print("\n=== 7. 운영자 로그인 화면 ===")
    h = anon.get("/auth/admin/login").get_data(as_text=True)
    check("운영자" in h and 'name="password"' in h, "운영자 로그인 화면 공개")
    check("카카오" not in h and "회원가입" not in h, "회원 가입 유도 없음")
    for bad in ("https://evil.example.com", "//evil.example.com", "/my"):
        r = anon.get("/auth/admin/login?next=" + bad)
        check(r.status_code == 200 and bad not in r.get_data(as_text=True), f"next={bad} 반영 안 됨")

    print("\n=== 8. 개발용 우회 로그인 (운영에서 꺼져 있어야) ===")
    r = anon.get("/auth/dev-login?as=admin")
    check(r.status_code == 404, "dev-login 404 (DEBUG·DEV_LOGIN 둘 다 꺼짐)", r.status_code)

    print("\n" + ("전부 통과" if not FAIL else "실패 %d건: %s" % (len(FAIL), ", ".join(FAIL))))


if __name__ == "__main__":
    main()
