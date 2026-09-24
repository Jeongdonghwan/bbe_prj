"""주기 작업 실행기 — 크론이 이 파일을 부른다.

    python scripts/cron.py daily     # 매일 새벽 (04:10 권장)
    python scripts/cron.py hourly    # 매시
    python scripts/cron.py <작업명>  # 하나만

앱과 같은 프로세스에 스케줄러를 넣지 않는 이유: 운영 서버가 gunicorn/waitress 워커 여러 개로
뜨면 워커 수만큼 중복 실행된다. 크론이 한 번만 부르는 쪽이 안전하고 로그도 분리된다.
"""
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402


def expire_unpaid():
    """입금 기한이 지난 무통장 주문을 취소하고 크레딧 충전 요청도 정리."""
    from app.services import payment_service
    return payment_service.expire_unpaid()


def refresh_efficiency():
    """매체 효율 재계산 — 어드민 매체 화면이 '새벽 배치로 자동 계산'이라 안내하는 그 작업."""
    from app.services import media_service
    return media_service.refresh_all_efficiency()


def refresh_slots():
    """쇼핑 추적 슬롯의 검색량·권장 수량 갱신 (네이버 검색광고 키가 있을 때만 의미 있음)."""
    from app.services import keyword_service
    return keyword_service.refresh_all_slots()


def close_agency():
    """30일 넘게 방치된 대행 의뢰 자동 마감."""
    from app.models import agency as agency_model
    return agency_model.close_stale(30)


def sync_ranks():
    """순위 추적 보정: 슬롯이 없는 구동 캠페인을 등록하고, 오늘 순위가 빈 건을 채운다.

    콜백이 끝내 실패한 경우의 최종 안전망이다 (docs/RANK_INTEGRATION.md).
    """
    from app.models import campaign as campaign_model
    from app.services import campaign_service, rank_client
    if not rank_client.configured():
        return "순위 서버 미설정 — 건너뜀"
    spawned = 0
    for c in campaign_model.untracked_running():
        if campaign_service.spawn_track(c):
            spawned += 1
    filled = 0
    for c in campaign_model.tracked_without_today_rank():
        if campaign_service.backfill_ranks(c, throttle_min=0):
            filled += 1
    return f"신규 등록 {spawned} · 순위 보정 {filled}"


JOBS = {
    "expire_unpaid": expire_unpaid,
    "refresh_efficiency": refresh_efficiency,
    "refresh_slots": refresh_slots,
    "close_agency": close_agency,
    "sync_ranks": sync_ranks,
}
GROUPS = {
    "daily": ["expire_unpaid", "refresh_efficiency", "refresh_slots", "close_agency"],
    "hourly": ["sync_ranks"],
}


def main():
    names = sys.argv[1:] or ["daily"]
    todo = []
    for n in names:
        todo += GROUPS.get(n, [n])
    unknown = [n for n in todo if n not in JOBS]
    if unknown:
        print("모르는 작업:", ", ".join(unknown))
        print("가능한 값:", ", ".join(list(GROUPS) + list(JOBS)))
        return 2
    app = create_app()
    failed = 0
    for name in todo:
        started = datetime.now()
        with app.app_context():
            try:
                result = JOBS[name]()
                print(f"[{started:%Y-%m-%d %H:%M:%S}] {name}: {result} "
                      f"({(datetime.now() - started).total_seconds():.1f}s)")
            except Exception:
                failed += 1
                print(f"[{started:%Y-%m-%d %H:%M:%S}] {name}: 실패")
                traceback.print_exc()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
