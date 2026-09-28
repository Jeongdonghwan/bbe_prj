"""방금 등록한 캠페인의 순위가 왜 안 보이는지 단계별로 짚는다."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import create_app
from app.db import query
from app.models import campaign as cm
from app.services import campaign_service as cs
from app.services import rank_client

app = create_app()
with app.app_context():
    print("1) 순위 서버 설정:", rank_client.configured(),
          "|", app.config.get("RANK_SERVER_URL"))
    rows = query("""SELECT * FROM campaigns WHERE channel IN ('store','place')
                    ORDER BY id DESC LIMIT 5""")
    if not rows:
        print("   쇼핑·플레이스 캠페인이 없습니다."); sys.exit()
    for r in rows:
        c = cm.get(r["id"])
        print(f"\n── {c['order_no']} · {c['channel']} · {c['status']} · '{c['main_keyword']}'")
        print(f"   등록 {c['created_at']:%m-%d %H:%M} / 구동 {c['start_date']}~{c['end_date']}")
        print(f"   2) track_id = {c['track_id']}  track_status = {c['track_status']}")
        if not c["track_id"]:
            plat = rank_client.TRACK_PLATFORM.get(c["channel"])
            if not plat:
                print(f"   → {c['channel']} 은 순위 서버에 수집기가 없어 추적하지 않는다 (정상).")
                continue
            print(f"   → 추적이 안 걸렸다. 지금 다시 등록해 본다 (platform={plat}):")
            r = rank_client.register_slot(c["main_keyword"], c["target_url"], plat)
            print("      순위 서버 응답:", r)
            if r.get("ok"):
                print("      → 성공. 이제 걸렸다:", cs.spawn_track(c))
            else:
                print("      → 거부됨. 위 message 가 이유다.")
            continue
        print(f"   3) 기록 구간 = {cs.rank_window(c)}  (이 안의 날짜만 기록된다)")
        daily = query("SELECT date, `rank`, done_qty FROM campaign_daily WHERE campaign_id=%s ORDER BY date DESC LIMIT 5", [c["id"]])
        print(f"   4) 우리 DB 기록 {len(daily)}행:", [(str(d['date']), d['rank']) for d in daily] or "없음")
        print(f"      rank_start={c['rank_start']} rank_now={c['rank_now']} → 화면 상태 '{cs.rank_state(c)}'")
        got = rank_client.slot_ranks(c["track_id"])
        print(f"   5) 순위 서버가 가진 순위:", (got.get("ranks") or "없음") if got.get("ok") else f"조회 실패 {got}")
        if got.get("ok") and got.get("ranks"):
            cs._BACKFILL_AT.pop(c["id"], None)
            print("   6) 폴백 실행:", cs.backfill_ranks(c, throttle_min=0))
            print("      →", query("SELECT date, `rank` FROM campaign_daily WHERE campaign_id=%s ORDER BY date DESC LIMIT 3", [c["id"]]))
        else:
            print("   6) 순위 서버가 아직 이 키워드를 수집하지 않았다 —")
            print("      쇼핑은 매일 11시·17시, 플레이스는 14시에 수집한다.")
            print("      그 전까지는 '순위 조회중'이 맞는 표시다.")
