"""Insert one running mock campaign per channel (place/store/coupang) for a user.

    python scripts/mock_campaigns.py --email test@naver.com
    python scripts/mock_campaigns.py --user-id 5

Creates campaigns + payments + status logs + 3 days of rank data, all titled 테스트,
so the 캠페인 관리 screens have data for that account. Safe to re-run (adds more rows).
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402

from app.config import Config  # noqa: E402
from app.services.campaign_service import quote  # noqa: E402

URLS = {"place": "https://m.place.naver.com/restaurant/1234567/home",
        "store": "https://smartstore.naver.com/test/products/1",
        "coupang": "https://www.coupang.com/vp/products/1"}
RANKS = {"place": [18, 14, 11], "store": [65, 41, 28], "coupang": [52, 37, 25]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email")
    ap.add_argument("--user-id", type=int)
    args = ap.parse_args()
    if not args.email and not args.user_id:
        ap.error("--email 또는 --user-id 중 하나를 주세요")

    conn = pymysql.connect(host=Config.DB_HOST, port=Config.DB_PORT, user=Config.DB_USER,
                           password=Config.DB_PASSWORD, database=Config.DB_NAME,
                           autocommit=True, cursorclass=pymysql.cursors.DictCursor)
    cur = conn.cursor()
    if args.user_id:
        cur.execute("SELECT id, nickname FROM users WHERE id = %s", (args.user_id,))
    else:
        cur.execute("SELECT id, nickname FROM users WHERE email = %s", (args.email,))
    u = cur.fetchone()
    if not u:
        print("사용자를 찾을 수 없습니다.")
        sys.exit(1)
    uid = u["id"]
    now = datetime.now()
    seq = int(now.timestamp()) % 100_000_000

    for i, ch in enumerate(("place", "store", "coupang")):
        cur.execute("SELECT id, unit_price FROM media WHERE channel = %s AND is_active = 1 ORDER BY sort, id LIMIT 1", (ch,))
        m = cur.fetchone()
        if not m:
            print(f"{ch}: 활성 매체가 없어 건너뜀")
            continue
        daily, days = 100, 10
        start = date.today() - timedelta(days=3)
        end = start + timedelta(days=days - 1)
        q = quote(m["unit_price"], daily, days)
        order_no = f"N{seq + i * 7919:09d}"
        created = now - timedelta(days=4, hours=2 + i)
        ranks = RANKS[ch]
        cur.execute(
            """INSERT INTO campaigns (order_no, user_id, channel, media_id, status, biz_name, product_name, target_url,
               main_keyword, sub_keywords, setting_keywords, keyword_mode, extra, start_date, end_date, daily_qty,
               total_qty, unit_price, discount, vat, paid_amount, pay_method, paid_at, refund_amount,
               rank_start, rank_now, created_at)
               VALUES (%s,%s,%s,%s,'running',%s,%s,%s,%s,%s,%s,'ai',%s,%s,%s,%s,%s,%s,%s,%s,%s,'card',%s,0,%s,%s,%s)""",
            (order_no, uid, ch, m["id"], "테스트", "테스트" if ch != "place" else None, URLS[ch], "테스트",
             json.dumps([]), json.dumps(["테스트"], ensure_ascii=False), json.dumps({}),
             start, end, daily, daily * days, m["unit_price"], q["discount"], q["vat"], q["total"],
             created, ranks[0], ranks[-1], created))
        cid = cur.lastrowid
        cur.execute(
            """INSERT INTO payments (campaign_id, user_id, method, amount, status, pg_provider, pg_tid, paid_at, refund_amount, created_at)
               VALUES (%s,%s,'card',%s,'paid','mock',%s,%s,0,%s)""",
            (cid, uid, q["total"], f"MOCK-{uid}-{seq + i:08d}", created, created))
        logs = [(None, "pay_wait", f"카드 결제 요청 · {q['total']:,}원"),
                ("pay_wait", "review", f"카드 결제 승인 · {q['total']:,}원"),
                ("review", "approved", "운영팀 승인 · 링크·키워드 확인"),
                ("approved", "running", "구동 시작")]
        for k, (fr, to, memo) in enumerate(logs):
            cur.execute("INSERT INTO status_log (campaign_id, from_status, to_status, actor_id, memo, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                        (cid, fr, to, uid if fr is None else 1, memo, created + timedelta(hours=k)))
        for k, r in enumerate(ranks):
            cur.execute("INSERT INTO campaign_daily (campaign_id, date, rank, done_qty) VALUES (%s,%s,%s,%s)",
                        (cid, start + timedelta(days=k), r, daily))
        print(f"{ch}: {order_no} · {q['total']:,}원 · 진행 중 (campaign {cid})")
    conn.close()
    print(f"done — user #{uid} {u['nickname']}")


if __name__ == "__main__":
    main()
