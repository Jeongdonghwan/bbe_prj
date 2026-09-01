"""Seed dummy data for development.

    python scripts/seed.py            # truncate + insert seed rows
    python scripts/seed.py --schema   # apply schema.sql first (no mysql CLI needed)
    python scripts/seed.py --reset    # DROP + recreate database, then seed (dev only)

Seeds: users 4, media 20, boards 4, notices 12, info 12, series 5, banners 3,
nick_words 120, forbidden_words, anon posts 8 (+ a few comments for counts).
"""
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import Config  # noqa: E402

random.seed(42)


def connect(database=None):
    return pymysql.connect(
        host=Config.DB_HOST, port=Config.DB_PORT, user=Config.DB_USER,
        password=Config.DB_PASSWORD, database=database, charset="utf8mb4", autocommit=True,
    )


def apply_schema(reset=False):
    raw = (ROOT / "schema.sql").read_text(encoding="utf-8")
    if Config.DB_NAME != "traffic_hub":
        raw = raw.replace("traffic_hub", Config.DB_NAME)  # schema.sql hardcodes the default name
    sql = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("--"))
    conn = connect()
    with conn.cursor() as cur:
        if reset:
            cur.execute(f"DROP DATABASE IF EXISTS {Config.DB_NAME}")
        for stmt in sql.split(";"):
            s = stmt.strip()
            if s:
                cur.execute(s)
    conn.close()
    print("schema applied")


def para(*ps):
    return "".join(f"<p>{p}</p>" for p in ps)


NOTICES = [("update", f"테스트 {i}", 1 if i == 1 else 0) for i in range(1, 13)]
STORE_NOTICES = [("update", "테스트"), ("update", "테스트")]

INFO = [(["guide", "data", "update"][i % 3], f"테스트 {i}", 1 if i == 1 else 0) for i in range(1, 13)]

SERIES = [f"테스트 {i}" for i in range(1, 6)]

BANNERS = [(f"테스트 {i}", f"테스트 {i}", "/campaign/place/new") for i in range(1, 9)]

MEDIA = {
    "place": [
        ("테스트 1", "리워드", "테스트", "#0891B2", 150, 170, "rec", 82),
        ("테스트 2", "리워드", "테스트", "#7C3AED", 140, None, None, 78),
        ("테스트 3", "유입", "테스트", "#2563EB", 100, None, None, 71),
        ("테스트 4", "유입", "테스트", "#F59E0B", 110, 120, "best", 69),
        ("테스트 5", "유입", "테스트", "#EC4899", 105, None, "new", 66),
        ("테스트 6", "복합", "테스트", "#10B981", 80, None, None, 60),
        ("테스트 7", "복합", "테스트", "#F97316", 85, None, None, 58),
        ("테스트 8", "복합", "테스트", "#6B7280", 75, None, None, 55),
    ],
    "store": [
        ("테스트 9", "리워드", "테스트", "#7C3AED", 160, None, "rec", 80),
        ("테스트 10", "리워드", "테스트", "#0891B2", 155, 175, "best", 76),
        ("테스트 11", "유입", "테스트", "#2563EB", 110, None, None, 70),
        ("테스트 12", "유입", "테스트", "#F59E0B", 115, None, "new", 64),
        ("테스트 13", "복합", "테스트", "#F97316", 90, None, None, 59),
        ("테스트 14", "복합", "테스트", "#6B7280", 80, None, None, 54),
    ],
    "coupang": [
        ("테스트 15", "리워드", "테스트", "#DC2626", 170, None, "rec", 79),
        ("테스트 16", "리워드", "테스트", "#7C3AED", 165, 185, "best", 75),
        ("테스트 17", "유입", "테스트", "#2563EB", 120, None, None, 68),
        ("테스트 18", "유입", "테스트", "#F59E0B", 115, None, "new", 63),
        ("테스트 19", "복합", "테스트", "#F97316", 95, None, None, 57),
        ("테스트 20", "복합", "테스트", "#6B7280", 85, None, None, 52),
    ],
}

ADJ = ["꿈꾸는", "조용한", "말없는", "부지런한", "느긋한", "씩씩한", "수줍은", "용감한", "엉뚱한", "다정한",
       "졸린", "배고픈", "명랑한", "차분한", "재빠른", "느긋한", "호기심많은", "성실한", "부드러운", "똑똑한",
       "장난치는", "진지한", "웃는", "상냥한", "노래하는", "춤추는", "달리는", "걷는", "날아가는", "잠자는",
       "포근한", "기쁜", "씩씩한", "놀란", "당당한", "겸손한", "대담한", "신중한", "활발한", "고요한",
       "따뜻한", "시원한", "반짝이는", "산뜻한", "커다란", "조그만", "둥근", "총총한", "푸른", "붉은",
       "노란", "하얀", "까만", "보라빛", "은빛", "금빛", "새벽의", "한낮의", "저녁의", "한밤의"]
NOUN = ["다람쥐", "펭귄", "고래", "두더지", "수달", "여우", "너구리", "고슴도치", "판다", "코알라",
        "기린", "코끼리", "하마", "얼룩말", "사자", "호랑이", "표범", "치타", "늑대", "곰",
        "토끼", "햄스터", "고양이", "강아지", "부엉이", "올빼미", "참새", "까치", "비둘기", "갈매기",
        "독수리", "매", "앵무새", "공작", "백조", "오리", "거위", "닭", "꿩", "학",
        "거북이", "도마뱀", "카멜레온", "개구리", "두꺼비", "돌고래", "상어", "문어", "오징어", "해마",
        "불가사리", "게", "새우", "달팽이", "나비", "벌", "개미", "무당벌레", "잠자리", "반딧불이"]

FORBIDDEN = [
    ("최저가", None, "block"), ("1위", None, "warn"), ("업계 최고", None, "warn"), ("100% 보장", None, "block"),
    ("완치", "place", "block"), ("부작용 없음", "place", "block"), ("최고의 명의", "place", "block"),
    ("효과 보장", "place", "block"), ("무조건", None, "warn"), ("전국 1등", None, "warn"),
    ("정품 보장", "store", "warn"), ("가짜", "store", "warn"), ("로켓 최저가", "coupang", "block"),
    ("공식 파트너", None, "warn"), ("네이버 공식", None, "block"),
    ("최상급", None, "warn"), ("유일한", None, "warn"), ("특효", "place", "block"), ("환급 보장", None, "block"),
    ("절대", None, "warn"),
]

ANON_POSTS = [(f"{ADJ[i]} {NOUN[i]}", ["place", "store", "coupang", "tool", None][i % 5], f"테스트 {i + 1}", (i * 3) % 10) for i in range(8)]


SAMPLE_CAMPAIGNS = [
    (2, "place", "테스트 1", "running", "테스트 1", "테스트", 200, 4, 10, "card", [27, 25, 21, 16, 12]),
    (2, "place", "테스트 2", "running", "테스트 2", "테스트", 300, 3, 10, "card", [41, 38, 35, 33]),
    (2, "place", "테스트 3", "review", "테스트 3", "테스트", 100, -2, 10, "card", []),
    (2, "place", "테스트 1", "pay_wait", "테스트 4", "테스트", 150, -2, 5, "bank", []),
    (2, "place", "테스트 4", "rejected", "테스트 5", "테스트", 200, -1, 7, "card", []),
    (2, "place", "테스트 6", "done", "테스트 6", "테스트", 100, 20, 10, "card", [38, 30, 22, 15, 9, 6]),
    (2, "place", "테스트 7", "stopped", "테스트 7", "테스트", 100, 14, 10, "card", [19, 20, 21]),
    (2, "store", "테스트 9", "running", "테스트 8", "테스트", 60, 2, 10, "card", [74, 40, 20, 8]),
    (2, "coupang", "테스트 15", "review", "테스트 9", "테스트", 80, -3, 7, "bank", []),
]


QNA_POSTS = [(f"{ADJ[i + 10]} {NOUN[i + 10]}", ["place", "store", "coupang", "tool"][i % 4], f"테스트 {i + 1}", ["테스트"] if i % 2 == 0 else [], i % 2 == 0) for i in range(5)]
AGENCY_REQUESTS = [
    (2, "place", "테스트", "100_300", "테스트", "테스트", "010-1111-2222", "open"),
    (3, "store", "테스트", "30_100", "테스트", "테스트", None, "open"),
    (2, "place", "테스트", "o300", "테스트", "테스트", "테스트", "matched"),
    (3, "coupang", "테스트", "tbd", "테스트", "테스트", None, "open"),
    (2, "place", "테스트", "u30", "테스트", "테스트", None, "closed"),
]


def seed_community(cur, now):
    """Anon + QnA posts with per-post nicknames (post_nicks), comments, likes, agency requests/proposals."""
    def nick_for(post_id, user_id, used):
        n = f"{random.choice(ADJ)} {random.choice(NOUN)}"
        while n in used:
            n = f"{random.choice(ADJ)} {random.choice(NOUN)}"
        used.add(n)
        cur.execute("INSERT IGNORE INTO post_nicks (post_id, user_id, nick) VALUES (%s,%s,%s)", (post_id, user_id, n))
        return n

    cur.execute("SELECT id, slug FROM boards")
    boards = {r[1]: r[0] for r in cur.fetchall()}
    for i, (nick, tag, title, n_comments) in enumerate(ANON_POSTS):
        author = 2 + i % 3
        likes = [42, 11, 25, 7, 18, 4, 6, 9][i]
        cur.execute(
            """INSERT INTO posts (board_id, user_id, anon_nick, channel_tag, title, body, views, likes, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (boards["anon"], author, nick, tag, title, "테스트",
             random.randint(30, 1200), likes, now - timedelta(hours=i * 5 + 1)))
        pid = cur.lastrowid
        cur.execute("INSERT IGNORE INTO post_nicks (post_id, user_id, nick) VALUES (%s,%s,%s)", (pid, author, nick))
        used, nicks = {nick}, {author: nick}
        for k in range(n_comments):
            uid = [2, 3, 4][k % 3]
            if uid not in nicks:
                nicks[uid] = nick_for(pid, uid, used)
            cur.execute("INSERT INTO comments (post_id, user_id, anon_nick, body, created_at) VALUES (%s,%s,%s,%s,%s)",
                        (pid, uid, nicks[uid], "테스트", now - timedelta(hours=i * 5, minutes=k * 7)))
        for uid in ([2, 3, 4] * 20)[:min(likes, 3)]:
            cur.execute("INSERT IGNORE INTO post_likes (post_id, user_id) VALUES (%s,%s)", (pid, uid))
    for i, (nick, tag, title, answers, admin_answer) in enumerate(QNA_POSTS):
        author = 2 + i % 3
        cur.execute(
            """INSERT INTO posts (board_id, user_id, anon_nick, channel_tag, title, body, views, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (boards["qna"], author, nick, tag, title, "테스트", random.randint(50, 500), now - timedelta(hours=i * 9 + 1)))
        pid = cur.lastrowid
        cur.execute("INSERT IGNORE INTO post_nicks (post_id, user_id, nick) VALUES (%s,%s,%s)", (pid, author, nick))
        used = {nick}
        for k, body in enumerate(answers):
            uid = 1 if (admin_answer and k == 0) else (3 if author != 3 else 4)
            n = "운영팀" if uid == 1 else nick_for(pid, uid, used)
            cur.execute("INSERT INTO comments (post_id, user_id, anon_nick, body, created_at) VALUES (%s,%s,%s,%s,%s)",
                        (pid, uid, n, body, now - timedelta(hours=i * 9, minutes=30 + k * 20)))
    for i, (uid, ch, ind, bud, region, body, contact, status) in enumerate(AGENCY_REQUESTS):
        cur.execute(
            """INSERT INTO agency_requests (user_id, anon_nick, channel, industry, budget, region, body, contact, status, views, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (uid, f"{random.choice(ADJ)} {random.choice(NOUN)}", ch, ind, bud, region, body, contact, status, random.randint(20, 160),
             now - timedelta(hours=i * 7 + 1)))
        rid = cur.lastrowid
        if i in (0, 2):
            cur.execute("INSERT INTO agency_proposals (request_id, proposer_id, budget_plan, plan, duration, status) VALUES (%s,1,%s,%s,%s,%s)",
                        (rid, "테스트", "테스트", "테스트",
                         "accepted" if i == 2 else "sent"))
            pid_ = cur.lastrowid
            cur.execute("INSERT INTO agency_proposals (request_id, proposer_id, budget_plan, plan, duration, status) VALUES (%s,4,%s,%s,%s,%s)",
                        (rid, "테스트", "테스트", "테스트", "rejected" if i == 2 else "sent"))
            if i == 2:
                cur.execute("UPDATE agency_requests SET accepted_proposal_id = %s WHERE id = %s", (pid_, rid))
    cur.execute("INSERT INTO agency_applies (user_id, biz_no, biz_cert_url, status, reviewed_by) VALUES (4, '123-45-67890', NULL, 'approved', 1)")
    cur.execute("INSERT INTO agency_applies (user_id, biz_no, biz_cert_url, status) VALUES (3, '987-65-43210', NULL, 'pending')")
    cur.execute("INSERT INTO notifications (user_id, type, title, link) VALUES (2, 'comment', '테스트', '/community/anon/1')")


def seed_campaigns(cur, now):
    """Sample orders for user 2 so the manage screen has data. Amounts follow campaign_service.quote."""
    import json
    from datetime import date
    from app.services.campaign_service import quote
    from app.constants import reco_qty
    cur.execute("SELECT id, name, unit_price FROM media")
    media = {r[1]: (r[0], r[2]) for r in cur.fetchall()}
    urls = {"place": "https://m.place.naver.com/restaurant/1234567/home", "store": "https://smartstore.naver.com/aura/products/1",
            "coupang": "https://www.coupang.com/vp/products/1"}
    for i, (uid, ch, mname, st, biz, kw, daily, ago, days, pm, ranks) in enumerate(SAMPLE_CAMPAIGNS):
        mid, price = media[mname]
        start = date.today() - timedelta(days=ago)
        end = start + timedelta(days=days - 1)
        q = quote(price, daily, days)
        order_no = f"N{581520800 + i * 7919:09d}"
        paid = st not in ("pay_wait", "cancelled")
        created = now - timedelta(days=max(ago, 0) + 2, hours=3)
        refund = q["total"] if st == "rejected" else (int(round(q["total"] * 4 / days)) if st == "stopped" else 0)
        memo = None
        if i == 0:
            memo = "테스트"
        cur.execute(
            """INSERT INTO campaigns (order_no, user_id, channel, media_id, status, biz_name, product_name, target_url, main_keyword,
               sub_keywords, setting_keywords, keyword_mode, extra, start_date, end_date, daily_qty, total_qty, unit_price, discount, vat,
               paid_amount, pay_method, paid_at, refund_amount, rank_start, rank_now, reject_reason, admin_memo, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'ai',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (order_no, uid, ch, mid, st, biz, biz if ch != "place" else None, urls[ch], kw, json.dumps([]),
             json.dumps([kw, kw + " 추천", kw + " 후기"], ensure_ascii=False),
             json.dumps({"category": "맛집·카페"} if ch == "place" else {}),
             start, end, daily, daily * days, price, q["discount"], q["vat"], q["total"], pm,
             created if paid else None, refund, ranks[0] if ranks else None, ranks[-1] if ranks else None,
             "테스트" if st == "rejected" else None, memo, created))
        cid = cur.lastrowid
        pstatus = {"pay_wait": "pending", "rejected": "refunded", "stopped": "partial_refund"}.get(st, "paid")
        cur.execute(
            """INSERT INTO payments (campaign_id, user_id, method, amount, status, pg_provider, pg_tid, depositor, bank_due_at, paid_at, refund_amount, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (cid, uid, pm, q["total"], pstatus, "mock" if pm == "card" else None,
             f"MOCK-SEED{i:04d}" if paid and pm == "card" else None,
             "일산갈비" if pm == "bank" else None, now + timedelta(days=3) if pm == "bank" else None,
             created if paid else None, refund, created))
        logs = [(None, "pay_wait", ("카드 결제 요청" if pm == "card" else "무통장 입금 대기") + f" · {q['total']:,}원")]
        if paid:
            logs.append(("pay_wait", "review", ("카드 결제 승인" if pm == "card" else "입금 확인") + f" · {q['total']:,}원"))
        if st in ("approved", "running", "done", "stopped"):
            logs.append(("review", "approved", "운영팀 승인 · 링크·키워드 확인"))
        if st in ("running", "done", "stopped"):
            logs.append(("approved", "running", "구동 시작"))
        if st == "done":
            logs.append(("running", "done", f"구동 완료 · 누적 {daily * days:,}건"))
        if st == "stopped":
            logs.append(("running", "stopped", "사용자 중단 요청 · 6/10일 진행 · 잔여 4일분 환불"))
            logs.append(("stopped", "stopped", f"부분 환불 {refund:,}원 (카드 취소) · 중단"))
        if st == "rejected":
            logs.append(("review", "rejected", "반려 · 테스트"))
            logs.append(("rejected", "rejected", f"전액 환불 {refund:,}원 (카드 취소) · 반려"))
        for k, (f, t, m) in enumerate(logs):
            cur.execute("INSERT INTO status_log (campaign_id, from_status, to_status, actor_id, memo, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                        (cid, f, t, 1 if f else uid, m, created + timedelta(hours=k)))
        for k, r in enumerate(ranks):
            cur.execute("INSERT INTO campaign_daily (campaign_id, date, rank, done_qty) VALUES (%s,%s,%s,%s)",
                        (cid, start + timedelta(days=k), r, daily))
    for kw, pc, mo, sn in [("테스트 1", 9100, 39200, "테스트"), ("테스트 2", 14000, 98000, None),
                           ("테스트 3", 2100, 7700, None)]:
        cur.execute("INSERT INTO store_slots (user_id, keyword, store_name, pc_cnt, mo_cnt, reco_qty, fetched_at) VALUES (2,%s,%s,%s,%s,%s,NOW())",
                    (kw, sn, pc, mo, reco_qty(pc + mo)))


POPULAR = {
    "place": [("추천", [("테스트 1", "테스트"), ("테스트 2", "테스트"), ("테스트 3", "테스트")])],
    "store": [("추천", [("테스트 9", "테스트"), ("테스트 10", "테스트"), ("테스트 11", "테스트")])],
    "coupang": [("추천", [("테스트 15", "테스트"), ("테스트 16", "테스트"), ("테스트 17", "테스트")])]}


def seed_popular(cur):
    cur.execute("SELECT id, name FROM media")
    media = {r[1]: r[0] for r in cur.fetchall()}
    for channel, cats in POPULAR.items():
        for i, (name, tops) in enumerate(cats):
            cur.execute("INSERT INTO popular_categories (channel, name, sort, is_active) VALUES (%s,%s,%s,%s)", (channel, name, i, 1 if tops else 0))
            cid = cur.lastrowid
            for rank, (mname, note) in enumerate(tops, 1):
                cur.execute("INSERT INTO popular_sets (category_id, rank, media_id, note) VALUES (%s,%s,%s,%s)", (cid, rank, media[mname], note))
            cur.execute("INSERT INTO popular_meta (category_id, show_weekly_cnt, updated_by) VALUES (%s,1,1)", (cid,))
            for rank, (mname, _note) in enumerate(tops, 1):
                for j in range(2):
                    uid = 2 + (rank + j) % 3
                    nick = f"{random.choice(ADJ)} {random.choice(NOUN)}"
                    cur.execute("INSERT IGNORE INTO media_nicks (media_id, user_id, nick) VALUES (%s,%s,%s)", (media[mname], uid, nick))
                    cur.execute("INSERT INTO media_comments (media_id, user_id, anon_nick, body) VALUES (%s,%s,%s,%s)",
                                (media[mname], uid, nick, "테스트"))
    cur.execute("INSERT INTO settings (k, v) VALUES ('bank_due_days','3')")


def seed():
    conn = connect(Config.DB_NAME)
    cur = conn.cursor()
    now = datetime.now()

    cur.execute("SET FOREIGN_KEY_CHECKS=0")
    for t in ("comments", "posts", "boards", "contents", "banners", "media", "nick_words", "forbidden_words",
              "admin_log", "campaign_daily", "status_log", "payments", "campaigns", "store_slots",
              "popular_sets", "popular_excludes", "popular_meta", "popular_categories", "settings",
              "post_nicks", "post_likes", "media_nicks", "media_comments", "reports", "notifications", "agency_proposals", "agency_applies", "agency_requests", "series_reads", "users"):
        cur.execute(f"TRUNCATE TABLE {t}")

    # users
    cur.executemany(
        "INSERT INTO users (kakao_id, nickname, phone, role) VALUES (%s,%s,%s,%s)",
        [("admin-0001", "운영팀", "010-0000-0000", "admin"),
         ("kakao-1001", "일산갈비", "010-1111-2222", "user"),
         ("kakao-1002", "강남치과", "010-3333-4444", "user"),
         ("kakao-1003", "스토어사장", "010-5555-6666", "user")],
    )
    admin_id = 1

    # media
    rows = []
    for channel, items in MEDIA.items():
        for i, (name, grp, tag, color, price, lst, badge, eff) in enumerate(items):
            lvl = "best" if eff >= 75 else ("good" if eff >= 60 else "normal")
            rows.append((channel, grp, name, tag, color, price, lst, 3, 50, 500, eff, badge, lvl, i,
                         "테스트"))
    cur.executemany(
        """INSERT INTO media (channel, group_name, name, tagline, color, unit_price, list_price, min_days,
           min_daily, max_daily, efficiency_auto, badge, eff_level, sort, description)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", rows)
    cur.execute("UPDATE media SET eff_note = '테스트'")

    # contents: notices / info / series
    rows = []
    for i, (cat, title, pinned) in enumerate(NOTICES):
        body = para(f"<b>{title}</b>", "운영팀에서 안내드립니다. 자세한 내용은 카카오 바로상담으로 문의해주세요.",
                    "감사합니다.")
        rows.append(("notice", cat, None, title, body, now - timedelta(days=i + 1, hours=3), pinned, admin_id))
    for i, (cat, title, pinned) in enumerate(INFO):
        body = ("<h2>요약</h2>" + para(f"{title}에 대해 정리했습니다.")
                + "<h2>본문</h2>" + para("첫 번째 항목. " * 20, "두 번째 항목. " * 20)
                + "<ul><li>체크 항목 1</li><li>체크 항목 2</li><li>체크 항목 3</li></ul>")
        rows.append(("info", cat, None, title, body, now - timedelta(days=i * 2 + 1), pinned, admin_id))
    cur.executemany(
        """INSERT INTO contents (board, category, series_no, title, body, publish_at, is_pinned, author_id, status, views)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'published',FLOOR(RAND()*900)+20)""", rows)
    cur.executemany(
        """INSERT INTO contents (board, channel, category, title, body, publish_at, is_pinned, author_id, status, show_dashboard)
           VALUES ('notice','store',%s,%s,%s,%s,0,%s,'published',0)""",
        [(cat, t, para(t), now - timedelta(days=i + 1), admin_id) for i, (cat, t) in enumerate(STORE_NOTICES)])
    rows = []
    for i, title in enumerate(SERIES):
        length = [900, 1100, 2800, 2400, 3900][i]
        body = f"<h2>{i + 1}편. {title}</h2>" + para(*(["처음 시작하는 분을 위한 설명입니다. " * 10] * (length // 400)))
        rows.append(("series", "series", i + 1, title, body, now - timedelta(days=30 - i), 0, admin_id))
    cur.executemany(
        """INSERT INTO contents (board, category, series_no, title, body, publish_at, is_pinned, author_id, status, views)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'published',FLOOR(RAND()*300)+10)""", rows)

    # banners
    cur.executemany(
        "INSERT INTO banners (subtitle, title, link, image_url, sort, is_active) VALUES (%s,%s,%s,%s,%s,1)",
        [(sub, title, link, f"/static/uploads/banners/t{i + 1}.png", i) for i, (sub, title, link) in enumerate(BANNERS)],
    )

    # nick words
    cur.executemany("INSERT INTO nick_words (kind, word) VALUES (%s,%s)",
                    [("adj", w) for w in ADJ] + [("noun", w) for w in NOUN])

    # forbidden words
    cur.executemany("INSERT INTO forbidden_words (word, channel, severity) VALUES (%s,%s,%s)", FORBIDDEN)

    # boards + anon posts (dashboard widget)
    cur.executemany(
        "INSERT INTO boards (slug, name, is_anon, write_role) VALUES (%s,%s,%s,%s)",
        [("anon", "익명 게시판", 1, "user"), ("qna", "질문답변", 1, "user"),
         ("info", "마케팅 정보", 0, "admin"), ("agency", "대행의뢰", 1, "user")],
    )
    cur.execute("UPDATE users SET is_agency = 1, grade = 'agency', biz_name = '스토어마케팅랩', biz_no = '123-45-67890' WHERE id = 4")
    seed_community(cur, now)

    seed_campaigns(cur, now)
    seed_popular(cur)
    cur.execute("SET FOREIGN_KEY_CHECKS=1")
    conn.close()
    print("seed done: users 4, media 20, notices 12, info 12, series 5, banners 3, nick_words 120, "
          f"forbidden_words {len(FORBIDDEN)}, anon posts {len(ANON_POSTS)}, campaigns {len(SAMPLE_CAMPAIGNS)}, store slots 3, popular categories {sum(len(v) for v in POPULAR.values())}")


if __name__ == "__main__":
    if "--reset" in sys.argv:
        apply_schema(reset=True)
    elif "--schema" in sys.argv:
        apply_schema()
    seed()
