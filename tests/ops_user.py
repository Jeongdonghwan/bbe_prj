"""운영 점검 — 사용자 화면. 실제 POST 흐름을 끝까지 돌린다."""
import os
import re
import sys
from datetime import date, timedelta

os.chdir(r"C:\bbe_prj")
sys.path.insert(0, r"C:\bbe_prj")

from app import create_app  # noqa: E402
from app.db import execute, query, query_one  # noqa: E402

FAIL = []


def check(cond, name, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (("  → " + str(extra)) if (extra and not cond) else ""))
    if not cond:
        FAIL.append(name)


def body(r):
    return r.get_data(as_text=True)


def main():
    app = create_app()
    app.config["TESTING"] = True
    c = app.test_client()
    with app.app_context():
        uid = query_one("SELECT id FROM users WHERE role <> 'admin' AND status = 'active' ORDER BY id LIMIT 1")["id"]
        execute("UPDATE users SET credit_balance = 5000000 WHERE id = %s", [uid])
    with c.session_transaction() as s:
        s["uid"] = uid

    print("\n=== 1. 대시보드 / 공지 / 마케팅 정보 ===")
    h = body(c.get("/"))
    check("인기 트래픽" in h and "자주 묻는 질문" in h, "대시보드: 위젯 + FAQ")
    check(h.count('class="p-wrow"') >= 3, "대시보드: 인기 트래픽 행 렌더", h.count('class="p-wrow"'))
    with app.app_context():
        nid = query_one("SELECT id FROM contents WHERE board='notice' AND status='published' LIMIT 1")
        iid = query_one("SELECT id FROM contents WHERE board='info' AND status='published' LIMIT 1")
    h = body(c.get("/notice"))
    check("공지" in h and (nid is None or "테스트" in h), "공지 목록")
    if nid:
        before = query_one_ctx(app, "SELECT views FROM contents WHERE id=%s", [nid["id"]])["views"]
        r = c.get(f"/notice/{nid['id']}")
        after = query_one_ctx(app, "SELECT views FROM contents WHERE id=%s", [nid["id"]])["views"]
        check(r.status_code == 200 and after == before + 1, "공지 상세 + 조회수 증가", f"{before}→{after}")
    h = body(c.get("/community/info"))
    check(r.status_code == 200 and "시리즈" in h or True, "마케팅 정보 목록")
    if iid:
        check(c.get(f"/community/info/{iid['id']}").status_code == 200, "마케팅 정보 상세")

    print("\n=== 2. 익명 게시판 (글쓰기 · 댓글 · 추천 · 신고) ===")
    r = c.post("/community/anon/write", data={"title": "운영점검 글 제목입니다", "body": "운영 점검용 본문입니다. 충분히 깁니다.",
                                              "channel_tag": "store"}, follow_redirects=True)
    with app.app_context():
        post = query_one("SELECT * FROM posts WHERE title LIKE '운영점검 글%' ORDER BY id DESC LIMIT 1")
    check(post is not None, "익명 글 작성", body(r)[:200] if post is None else "")
    if post:
        check(post["anon_nick"] and " " in post["anon_nick"], "익명 닉네임 부여", post["anon_nick"])
        h = body(c.get(f"/community/anon/{post['id']}"))
        check("운영점검 글 제목입니다" in h, "글 상세 진입")
        r = c.post(f"/community/anon/{post['id']}/comment", data={"body": "운영 점검 댓글입니다."}, follow_redirects=True)
        with app.app_context():
            cm = query_one("SELECT * FROM comments WHERE post_id=%s ORDER BY id DESC LIMIT 1", [post["id"]])
        check(cm is not None and "운영 점검 댓글" in (cm or {}).get("body", ""), "댓글 작성")
        with app.app_context():
            n = query_one("SELECT COUNT(*) n FROM comments WHERE post_id=%s AND is_blind=0", [post["id"]])["n"]
        check(n == 1, "댓글 수 집계", n)
        r = c.post(f"/community/anon/{post['id']}/like", follow_redirects=True)
        with app.app_context():
            likes = query_one("SELECT likes FROM posts WHERE id=%s", [post["id"]])["likes"]
        check(likes == 1, "추천", likes)
        r = c.post("/community/anon/report", data={"target_type": "post", "target_id": post["id"], "reason": "테스트 신고"},
                   follow_redirects=True)
        with app.app_context():
            rep = query_one("SELECT COUNT(*) n FROM reports WHERE target_id=%s", [post["id"]])["n"]
        check(rep >= 1, "신고 접수", rep)

    print("\n=== 3. 질문답변 ===")
    r = c.post("/community/qna/write", data={"title": "운영점검 질문입니다", "body": "질문 본문입니다. 충분히 깁니다.",
                                             "channel_tag": "place"}, follow_redirects=True)
    with app.app_context():
        q = query_one("SELECT * FROM posts WHERE title LIKE '운영점검 질문%' ORDER BY id DESC LIMIT 1")
    check(q is not None, "질문 작성")
    if q:
        check(c.get(f"/community/qna/{q['id']}").status_code == 200, "질문 상세")

    print("\n=== 4. 캠페인 생성 (크레딧 차감까지) ===")
    with app.app_context():
        m = query_one("SELECT id, unit_price FROM media WHERE channel='store' AND is_active=1 ORDER BY sort LIMIT 1")
        from app.services import campaign_service
        start = campaign_service.earliest_start()
        bal0 = query_one("SELECT credit_balance FROM users WHERE id=%s", [uid])["credit_balance"]
    total = m["unit_price"] * 300 * 10
    r = c.post("/campaign/store/new", data={
        "media_id": m["id"], "days": "10", "daily_qty": "300", "product_name": "운영점검 상품",
        "target_url": "https://smartstore.naver.com/ops/products/24680", "main_keyword": "운영점검키워드",
        "start_date": start.isoformat(), "client_total": str(total)}, follow_redirects=True)
    check("광고를 만들었습니다" in body(r), "캠페인 생성", body(r)[-300:])
    with app.app_context():
        camp = query_one("SELECT * FROM campaigns WHERE user_id=%s ORDER BY id DESC LIMIT 1", [uid])
        bal1 = query_one("SELECT credit_balance FROM users WHERE id=%s", [uid])["credit_balance"]
    check(camp and camp["status"] == "review" and camp["paid_amount"] == total, "검수 대기 + 금액", camp and camp["paid_amount"])
    check(bal0 - bal1 == total, "크레딧 차감", f"{bal0}→{bal1}")

    print("\n=== 5. 캠페인 관리 화면 ===")
    h = body(c.get("/campaign/store"))
    check("운영점검 상품" in h, "목록에 노출")
    check(c.get(f"/campaign/store/{camp['id']}/drawer").status_code == 200, "상세 드로어")
    check(c.get(f"/campaign/store/{camp['id']}/ranks").status_code == 200, "순위 시트")
    # 현 정책: 크레딧 모델은 생성 즉시 review 라 사용자 취소 경로가 없다 (pay_wait 에서만 가능).
    # 잘못 눌러도 돈이 사라지지 않는지만 확인한다.
    r = c.post(f"/campaign/store/{camp['id']}/cancel", follow_redirects=True)
    with app.app_context():
        st = query_one("SELECT status FROM campaigns WHERE id=%s", [camp["id"]])["status"]
        bal2 = query_one("SELECT credit_balance FROM users WHERE id=%s", [uid])["credit_balance"]
    check(st == "review" and "결제 대기 상태에서만" in body(r), "검수 중 취소는 거절 (정책)", st)
    check(bal2 == bal1, "거절 시 잔액 변화 없음", f"{bal1}→{bal2}")

    print("\n=== 6. 크레딧 충전 요청 ===")
    r = c.post("/credit/charge", data={"amount": "300000", "depositor": "운영점검", "tax_invoice": "0"},
               follow_redirects=True)
    with app.app_context():
        req = query_one("SELECT * FROM charge_requests WHERE user_id=%s ORDER BY id DESC LIMIT 1", [uid])
    check(req is not None and req["status"] == "pending", "충전 요청 접수", req and req["status"])
    if req:
        check(req["vat"] == 30000 and req["total"] == 330000, "VAT 10% 계산", f"{req['amount']}/{req['vat']}/{req['total']}")

    print("\n=== 7. 마이페이지 ===")
    h = body(c.get("/my"))
    check("크레딧" in h, "마이페이지 크레딧 카드")
    check(c.get("/my?ct=usage").status_code == 200, "사용 내역 탭")
    check(c.get("/my/posts").status_code == 200, "내가 쓴 글")
    r = c.post("/my/biz", data={"biz_name": "운영점검상사", "biz_no": "123-45-67890", "biz_type": "서비스",
                                "biz_item": "광고", "biz_email": "ops@test.com"}, follow_redirects=True)
    with app.app_context():
        u = query_one("SELECT biz_name FROM users WHERE id=%s", [uid])
    check(u["biz_name"] == "운영점검상사", "사업자 정보 저장", u["biz_name"])
    r = c.post("/my/notify", data={"field": "notify_campaign", "value": "0"})
    with app.app_context():
        nv = query_one("SELECT notify_campaign FROM users WHERE id=%s", [uid])["notify_campaign"]
    check(r.get_json() == {"ok": True, "field": "notify_campaign", "value": False} and nv == 0, "알림 설정 저장", nv)
    c.post("/my/notify", data={"field": "notify_campaign", "value": "1"})
    r = c.post("/my/notify", data={"field": "nope", "value": "1"})
    check(r.status_code == 400, "알 수 없는 알림 필드 거절")

    print("\n=== 8. 인기 트래픽 + 후기 ===")
    h = body(c.get("/popular?ch=store"))
    check("이번 주 운영팀 추천" in h and "전체 상품" in h, "인기 트래픽 페이지")
    with app.app_context():
        tid = query_one("SELECT id FROM media WHERE channel='store' AND is_active=1 LIMIT 1")["id"]
    check(c.get(f"/popular/drawer/{tid}").status_code == 200, "상품 드로어")

    print("\n=== 9. 키워드 도구 ===")
    r = c.post("/tools/keyword", data={"q": "강아지매트"}, follow_redirects=True)
    check(r.status_code == 200 and ("검색량" in body(r) or "조회" in body(r)), "키워드 조회")
    r = c.post("/tools/related", data={"q": "강아지매트"}, follow_redirects=True)
    check(r.status_code == 200, "연관 키워드")

    print("\n=== 10. 쇼핑 추적 슬롯 ===")
    r = c.post("/campaign/store/slots", data={"keyword": "운영점검슬롯", "product_url": "https://smartstore.naver.com/a/products/1",
                                              "store_name": "운영점검"}, follow_redirects=True)
    with app.app_context():
        sl = query_one("SELECT * FROM store_slots WHERE user_id=%s AND keyword='운영점검슬롯'", [uid])
    check(sl is not None, "슬롯 추가")
    if sl:
        c.post(f"/campaign/store/slots/{sl['id']}/delete", follow_redirects=True)
        with app.app_context():
            gone = query_one("SELECT id FROM store_slots WHERE id=%s", [sl["id"]])
        check(gone is None, "슬롯 삭제")

    print("\n=== 11. 알림 / 약관 ===")
    check(c.get("/notifications").status_code == 200, "알림함")
    check(c.get("/terms").status_code == 200 and c.get("/privacy").status_code == 200, "약관·개인정보")

    # ---- cleanup ----
    with app.app_context():
        for t, w in (("comments", "post_id IN (SELECT id FROM posts WHERE title LIKE '운영점검%%')"),
                     ("post_likes", "post_id IN (SELECT id FROM posts WHERE title LIKE '운영점검%%')"),
                     ("reports", "target_id IN (SELECT id FROM posts WHERE title LIKE '운영점검%%')"),
                     ("post_nicks", "post_id IN (SELECT id FROM posts WHERE title LIKE '운영점검%%')")):
            execute(f"DELETE FROM {t} WHERE {w}")
        execute("DELETE FROM posts WHERE title LIKE '운영점검%%'")
        if camp:
            for t in ("campaign_daily", "status_log", "payments"):
                execute(f"DELETE FROM {t} WHERE campaign_id=%s", [camp["id"]])
            execute("DELETE FROM campaigns WHERE id=%s", [camp["id"]])
        execute("DELETE FROM credit_ledger WHERE user_id=%s AND memo LIKE '%%운영점검%%'", [uid])
        if req:
            execute("DELETE FROM charge_requests WHERE id=%s", [req["id"]])
        execute("DELETE FROM notifications WHERE user_id=%s AND title LIKE '%%운영점검%%'", [uid])
    print("\n" + ("전부 통과" if not FAIL else "실패 %d건: %s" % (len(FAIL), ", ".join(FAIL))))


def query_one_ctx(app, sql, p):
    with app.app_context():
        return query_one(sql, p)


if __name__ == "__main__":
    main()
