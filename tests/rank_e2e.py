"""순위 추적 연동 end-to-end — 스텁 순위 서버를 띄워 등록·콜백·폴백·삭제를 확인."""
import json
import os
import sys
import threading
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

os.chdir(r"C:\bbe_prj")
sys.path.insert(0, r"C:\bbe_prj")

TOKEN = "stub-partner-token"
SEEN = []
STATE = {"collected_today": False, "next_track": 5001}


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, body):
        raw = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _guard(self):
        if self.headers.get("X-NSR-Token") != TOKEN:
            self._json(401, {"ok": False, "message": "인증 실패"})
            return False
        return True

    def do_POST(self):
        if not self._guard():
            return
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        SEEN.append(("POST", self.path, body))
        if not body.get("keyword") or not body.get("url"):
            return self._json(400, {"ok": False, "message": "검색 키워드를 입력하세요 (100자 이내)."})
        if "noproduct" in body["url"]:
            return self._json(400, {"ok": False, "message": "상품 페이지 주소가 아닙니다."})
        tid = STATE["next_track"]
        if STATE["collected_today"]:
            return self._json(200, {"ok": True, "trackId": tid, "status": "collected", "rank": 7,
                                    "prodNm": "스텁 상품", "date": date.today().isoformat()})
        self._json(200, {"ok": True, "trackId": tid, "status": "queued", "rank": None,
                         "prodNm": None, "date": None})

    def do_GET(self):
        if not self._guard():
            return
        p = urlparse(self.path).path
        SEEN.append(("GET", p, None))
        if p.endswith("/ranks"):
            tid = int(p.split("/")[-2])
            return self._json(200, {"ok": True, "trackId": tid, "prodNm": "스텁 상품", "ranks": [
                {"date": date.today().isoformat(), "rank": 12},
                {"date": (date.today() - timedelta(days=1)).isoformat(), "rank": 19},
                {"date": (date.today() - timedelta(days=400)).isoformat(), "rank": 3},   # 기간 밖
            ]})
        self._json(404, {"ok": False})

    def do_DELETE(self):
        if not self._guard():
            return
        SEEN.append(("DELETE", self.path, None))
        self._json(200, {"ok": True})

    def log_message(self, *a):
        pass


def main():
    srv = HTTPServer(("127.0.0.1", 5097), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    from app import create_app
    from app.db import execute, query_one
    from app.models import campaign as cm
    from app.services import campaign_service as cs

    app = create_app()
    app.config["TESTING"] = True
    app.config["RANK_SERVER_URL"] = "http://127.0.0.1:5097"
    app.config["RANK_API_TOKEN"] = TOKEN
    ok = lambda c, n: print(("PASS " if c else "FAIL ") + n)  # noqa: E731

    with app.app_context():
        m = query_one("SELECT id, unit_price FROM media WHERE channel='store' AND name='타이탄'")
        start = date.today() - timedelta(days=2)
        cid = cm.insert({
            "order_no": "RANKE2E", "user_id": 10, "channel": "store", "media_id": m["id"], "status": "approved",
            "biz_name": "추적 테스트", "target_url": "https://smartstore.naver.com/t/products/555",
            "main_keyword": "추적테스트키워드", "start_date": start, "end_date": start + timedelta(days=9),
            "daily_qty": 300, "total_qty": 3000, "unit_price": m["unit_price"], "paid_amount": 120000,
            "pay_method": "credit"})
        c = cm.get(cid)

        # 1) 등록 (queued)
        tid = cs.spawn_track(c)
        c = cm.get(cid)
        ok(tid == 5001 and c["track_id"] == 5001 and c["track_status"] == "queued", "등록 → trackId %s / %s" % (tid, c["track_status"]))
        ok(SEEN[0][1] == "/partner/slots" and SEEN[0][2]["keyword"] == "추적테스트키워드", "POST /partner/slots 본문")

        # 2) 이미 등록된 캠페인은 다시 등록하지 않는다
        SEEN.clear()
        ok(cs.spawn_track(c) is None and not SEEN, "track_id 있으면 재등록 안 함")

        # 3) 오늘 수집된 키워드면 즉시 순위 기록
        STATE["collected_today"] = True
        execute("UPDATE campaigns SET track_id=NULL, track_status=NULL, rank_start=NULL, rank_now=NULL WHERE id=%s", [cid])
        execute("DELETE FROM campaign_daily WHERE campaign_id=%s", [cid])
        cs.spawn_track(cm.get(cid))
        c = cm.get(cid)
        ok(c["rank_now"] == 7 and c["rank_start"] == 7, "collected 응답의 rank 즉시 기록 (%s)" % c["rank_now"])
        STATE["collected_today"] = False

        # 4) 플레이스 채널은 등록하지 않는다 (파트너 API 는 쇼핑 전용)
        SEEN.clear()
        pc = dict(c, channel="place", track_id=None)
        ok(cs.spawn_track(pc) is None and not SEEN, "쇼핑 외 채널은 등록 안 함")

    # 5) 콜백 수신
    tc = app.test_client()
    body = {"trackId": 5001, "keyword": "추적테스트키워드", "date": date.today().isoformat(), "rank": 4, "prodNm": "스텁 상품"}
    r = tc.post("/api/rank/callback", json=body)
    ok(r.status_code == 401, "토큰 없는 콜백 401")
    r = tc.post("/api/rank/callback", json=body, headers={"X-NSR-Token": "wrong"})
    ok(r.status_code == 401, "틀린 토큰 401")
    r = tc.post("/api/rank/callback", json=body, headers={"X-NSR-Token": TOKEN})
    j = r.get_json()
    ok(r.status_code == 200 and j["applied"] == 1, "정상 콜백 → %s" % j)
    with app.app_context():
        c = cm.get(cid)
        ok(c["rank_now"] == 4 and c["track_status"] == "collected", "순위 반영 rank_now=%s" % c["rank_now"])
    # 같은 (trackId, date) 재전송 — 중복 행이 생기면 안 된다
    tc.post("/api/rank/callback", json=body, headers={"X-NSR-Token": TOKEN})
    with app.app_context():
        n = query_one("SELECT COUNT(*) n FROM campaign_daily WHERE campaign_id=%s AND date=%s", [cid, date.today()])["n"]
        ok(n == 1, "중복 콜백에도 하루 1행 (%d)" % n)
    # 모르는 trackId
    r = tc.post("/api/rank/callback", json=dict(body, trackId=999999), headers={"X-NSR-Token": TOKEN})
    ok(r.status_code == 200 and r.get_json()["matched"] == 0, "남의 슬롯 → 200 matched=0")
    # 구동 기간 밖 날짜
    old_day = (date.today() - timedelta(days=400)).isoformat()
    r = tc.post("/api/rank/callback", json=dict(body, date=old_day), headers={"X-NSR-Token": TOKEN})
    ok(r.get_json()["applied"] == 0, "구동 기간 밖 날짜는 기록 안 함")

    # 6) 폴백 — 오늘 순위를 지우고 화면 진입
    with app.app_context():
        execute("DELETE FROM campaign_daily WHERE campaign_id=%s AND date=%s", [cid, date.today()])
        cs._BACKFILL_AT.clear()
        SEEN.clear()
        c = cm.get(cid)
        ok(cs.backfill_ranks(c) is True, "폴백 실행")
        got = query_one("SELECT `rank` FROM campaign_daily WHERE campaign_id=%s AND date=%s", [cid, date.today()])
        ok(got and got["rank"] == 12, "폴백으로 오늘 순위 채움 (%s)" % (got or {}).get("rank"))
        n_old = query_one("SELECT COUNT(*) n FROM campaign_daily WHERE campaign_id=%s AND date=%s",
                          [cid, date.today() - timedelta(days=400)])["n"]
        ok(n_old == 0, "폴백도 구동 기간 밖은 무시")
        SEEN.clear()
        ok(cs.backfill_ranks(cm.get(cid)) is False and not SEEN, "5분 스로틀 — 연속 호출은 서버를 안 때림")

    # 7) 삭제 가드
    with app.app_context():
        SEEN.clear()
        c = cm.get(cid)
        ok(cs.untrack_if_unused(c) is False and not SEEN, "RANK_UNTRACK_ON_STOP=0 이면 삭제 안 함")
        app.config["RANK_UNTRACK_ON_STOP"] = True
        cid2 = cm.insert({"order_no": "RANKE2E2", "user_id": 10, "channel": "store", "media_id": m["id"],
                          "status": "running", "biz_name": "같은 슬롯", "target_url": "https://x/y",
                          "main_keyword": "k", "start_date": start, "end_date": start + timedelta(days=9),
                          "daily_qty": 100, "total_qty": 1000, "unit_price": 40, "paid_amount": 40000,
                          "pay_method": "credit", "track_id": 5001})
        ok(cs.untrack_if_unused(c) is False and not SEEN, "다른 진행 캠페인이 쓰면 삭제 안 함")
        execute("UPDATE campaigns SET status='done' WHERE id=%s", [cid2])
        ok(cs.untrack_if_unused(cm.get(cid)) is True and SEEN and SEEN[-1][0] == "DELETE", "마지막 캠페인이면 삭제")

        for x in (cid, cid2):
            execute("DELETE FROM campaign_daily WHERE campaign_id=%s", [x])
            execute("DELETE FROM status_log WHERE campaign_id=%s", [x])
            execute("DELETE FROM campaigns WHERE id=%s", [x])
    srv.shutdown()
    print("cleaned")


if __name__ == "__main__":
    main()
