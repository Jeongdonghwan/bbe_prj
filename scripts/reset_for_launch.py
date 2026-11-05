"""실운영 전 테스트 데이터 초기화 (2026-11-05 JDH).

    python scripts/reset_for_launch.py          # 지울 개수를 보여주고, yes 를 입력하면 백업(JSON) 뒤 삭제
    python scripts/reset_for_launch.py --yes    # 묻지 않고 바로 백업 뒤 삭제

지우는 것
  1. 캠페인 전부 (+ 일자별 순위·상태 이력·후기·삭제 이력)
  2. 트래픽 상품(매체)의 테스트 문구: 유형 설명(description)·운영팀 한줄평(op_note)만 비움
  3. 계정별 단가 전부 → 매체 기본 단가로
  4. 공지사항·마케팅 정보·입문 시리즈 글 전부 (+ 시리즈 읽음 기록)
  5. 익명 게시판·질문답변 글 전부 (+ 댓글·좋아요·신고·글별 닉네임)
  6. 크레딧: 충전 요청·원장 전부 + 모든 회원 잔액 0 (2026-11-05 JDH 추가)
  7. 결제 내역(레거시 payments) 전부
  8. 운영 현황: 운영자 처리 기록(admin_log)·알림(notifications) 전부
남기는 것: 회원·운영자 계정, 매체 단가·설정, 배너·띠배너, 오늘의 인기·주간 추천 설정, 사이트 설정.

--yes 를 주면 지우기 전에 해당 행을 instance/reset_backup_<시각>.json 에 통째로 저장한다 (되돌리기용).
순위 서버의 추적 슬롯은 건드리지 않는다(RANK_UNTRACK_ON_STOP 정책) — 지운 캠페인 슬롯은 순위 서버에 남는다.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.db import get_db, query  # noqa: E402

# (이름, 백업·삭제 대상 SELECT, DELETE 문) — 순서대로 지운다 (자식 → 부모)
CAMPAIGN_IDS = "SELECT id FROM campaigns"
POST_IDS = "SELECT p.id FROM posts p JOIN boards b ON b.id = p.board_id WHERE b.slug IN ('anon', 'qna')"
COMMENT_IDS = f"SELECT id FROM comments WHERE post_id IN ({POST_IDS})"
STEPS = [
    # 1) 캠페인
    ("일자별 순위", f"SELECT * FROM campaign_daily WHERE campaign_id IN ({CAMPAIGN_IDS})", f"DELETE FROM campaign_daily WHERE campaign_id IN (SELECT id FROM ({CAMPAIGN_IDS}) x)"),
    ("상태 이력", f"SELECT * FROM status_log WHERE campaign_id IN ({CAMPAIGN_IDS})", f"DELETE FROM status_log WHERE campaign_id IN (SELECT id FROM ({CAMPAIGN_IDS}) x)"),
    ("결제 내역(레거시)", "SELECT * FROM payments", "DELETE FROM payments"),
    ("후기", "SELECT * FROM reviews", "DELETE FROM reviews"),
    ("캠페인", "SELECT * FROM campaigns", "DELETE FROM campaigns"),
    ("주문 삭제 이력", "SELECT * FROM deleted_orders", "DELETE FROM deleted_orders"),
    # 3) 계정별 단가
    ("계정별 단가", "SELECT * FROM user_media_prices", "DELETE FROM user_media_prices"),
    # 4) 공지·정보·시리즈
    ("시리즈 읽음 기록", "SELECT * FROM series_reads", "DELETE FROM series_reads"),
    ("공지·마케팅 정보·입문 시리즈", "SELECT * FROM contents WHERE board IN ('notice', 'info', 'series')",
     "DELETE FROM contents WHERE board IN ('notice', 'info', 'series')"),
    # 5) 익명 게시판·질문답변
    ("댓글 신고", f"SELECT * FROM reports WHERE target_type = 'comment' AND target_id IN ({COMMENT_IDS})",
     f"DELETE FROM reports WHERE target_type = 'comment' AND target_id IN (SELECT id FROM ({COMMENT_IDS}) x)"),
    ("글 신고", f"SELECT * FROM reports WHERE target_type = 'post' AND target_id IN ({POST_IDS})",
     f"DELETE FROM reports WHERE target_type = 'post' AND target_id IN (SELECT id FROM ({POST_IDS}) x)"),
    ("댓글", f"SELECT * FROM comments WHERE post_id IN ({POST_IDS})", f"DELETE FROM comments WHERE post_id IN (SELECT id FROM ({POST_IDS}) x)"),
    ("좋아요", f"SELECT * FROM post_likes WHERE post_id IN ({POST_IDS})", f"DELETE FROM post_likes WHERE post_id IN (SELECT id FROM ({POST_IDS}) x)"),
    ("글별 닉네임", f"SELECT * FROM post_nicks WHERE post_id IN ({POST_IDS})", f"DELETE FROM post_nicks WHERE post_id IN (SELECT id FROM ({POST_IDS}) x)"),
    ("익명·질문답변 글", POST_IDS.replace("SELECT p.id", "SELECT p.*"),
     "DELETE p FROM posts p JOIN boards b ON b.id = p.board_id WHERE b.slug IN ('anon', 'qna')"),
    # 6) 크레딧 — 잔액은 아래에서 0 으로
    ("크레딧 충전 요청", "SELECT * FROM charge_requests", "DELETE FROM charge_requests"),
    ("크레딧 원장", "SELECT * FROM credit_ledger", "DELETE FROM credit_ledger"),
    # 8) 운영 현황
    ("운영자 처리 기록", "SELECT * FROM admin_log", "DELETE FROM admin_log"),
    ("알림", "SELECT * FROM notifications", "DELETE FROM notifications"),
]
BALANCE_SELECT = "SELECT id, nickname, credit_balance FROM users WHERE credit_balance <> 0"
BALANCE_UPDATE = "UPDATE users SET credit_balance = 0"
# 2) 매체 테스트 문구 — 행은 남기고 두 칸만 비운다 (백업은 id·이름·두 칸)
MEDIA_SELECT = "SELECT id, channel, name, description, op_note FROM media WHERE description IS NOT NULL OR op_note IS NOT NULL"
MEDIA_UPDATE = "UPDATE media SET description = NULL, op_note = NULL"


def _json(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return str(v)


def main():
    go = "--yes" in sys.argv
    app = create_app()
    with app.app_context():
        backup, total = {}, 0
        print("=== 실운영 초기화 " + ("(실제 삭제)" if go else "(드라이런 — 지우지 않음)") + " ===")
        for name, sel, _ in STEPS:
            rows = query(sel)
            backup[name] = rows
            total += len(rows)
            print(f"  {name:<22} {len(rows):>6}건")
        media = query(MEDIA_SELECT)
        backup["매체 설명·한줄평(비우기 전 값)"] = media
        print(f"  {'매체 설명·한줄평 비우기':<22} {len(media):>6}개 매체")
        bal = query(BALANCE_SELECT)
        backup["회원 크레딧 잔액(0 으로 만들기 전)"] = bal
        print(f"  {'크레딧 잔액 0 으로':<22} {len(bal):>6}명 (합계 {sum(int(b['credit_balance']) for b in bal):,}원)")
        print("  남김: 회원·운영자 계정 · 매체 단가·설정 · 배너·띠배너 · 오늘의 인기·주간 추천 · 사이트 설정")
        if not go:
            # 터미널에서 실행했으면 그 자리에서 확인을 받는다 (--yes 를 따로 붙이는 게 헷갈렸다, 2026-11-05)
            if sys.stdin.isatty():
                ans = input("\n위 내용을 지우려면 yes 를 입력하고 Enter (그 밖의 입력은 취소): ").strip().lower()
                if ans != "yes":
                    print("취소했습니다. 아무것도 지우지 않았습니다.")
                    return 0
            else:
                print("\n실제로 지우려면: python scripts/reset_for_launch.py --yes")
                return 0

        out = ROOT / "instance" / f"reset_backup_{datetime.now():%Y%m%d_%H%M%S}.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(backup, ensure_ascii=False, default=_json, indent=0), encoding="utf-8")
        print(f"\n백업 저장: {out} ({out.stat().st_size // 1024} KB)")

        db = get_db()
        try:
            with db.cursor() as cur:
                for name, _, sql in STEPS:
                    cur.execute(sql)
                cur.execute(MEDIA_UPDATE)
                cur.execute(BALANCE_UPDATE)
                cur.execute("UPDATE media SET review_cnt = 0, rating_avg = 0")   # 후기를 지웠으니 집계도 0
            db.commit()
        except Exception:
            db.rollback()
            print("실패 — 아무것도 지우지 않고 되돌렸습니다.")
            raise
        print(f"완료 — {total}건 삭제, 매체 {len(media)}개 설명·한줄평 비움, 회원 {len(bal)}명 크레딧 잔액 0.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
