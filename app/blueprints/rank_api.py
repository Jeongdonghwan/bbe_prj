"""순위 서버 콜백 수신 — POST /api/rank/callback.

순위 서버(rank.mbizsquare.com)가 쇼핑 수집을 마치면 파트너 슬롯마다 이 주소로 POST 한다.
로그인 없이 들어오므로 X-NSR-Token 으로만 검증하고, 본문은 신뢰하지 않는다.

콜백 계약 (rankserver/partner.py `_partner_after_result`):
  헤더  X-NSR-Token: <RANK_API_TOKEN 과 같은 값>
  본문  {"trackId": int, "keyword": str, "date": "YYYY-MM-DD", "rank": int|null, "prodNm": str|null}

같은 (trackId, date) 가 여러 번 온다 — 하루 두 번(11시·17시) 수집하고 재시도도 있다.
그래서 upsert 로만 쓰고, 모르는 trackId 는 200 으로 조용히 넘긴다(순위 서버가 여러 파트너
사이트에 같은 payload 를 뿌리므로 남의 슬롯이 오는 게 정상이다).
"""
import hmac
from datetime import date

from flask import Blueprint, current_app, jsonify, request

from ..models import campaign as campaign_model
from ..services import campaign_service

bp = Blueprint("rank_api", __name__, url_prefix="/api/rank")


def _token_ok():
    expected = current_app.config.get("RANK_API_TOKEN") or ""
    given = request.headers.get("X-NSR-Token") or ""
    return bool(expected) and hmac.compare_digest(expected, given)


@bp.post("/callback")
def callback():
    if not _token_ok():
        return jsonify(ok=False, message="unauthorized"), 401
    body = request.get_json(silent=True) or {}
    try:
        track_id = int(body.get("trackId"))
        day = date.fromisoformat(str(body.get("date")))
    except (TypeError, ValueError):
        return jsonify(ok=False, message="trackId/date required"), 400
    rank = body.get("rank")
    if rank is not None:
        try:
            rank = int(rank)
        except (TypeError, ValueError):
            rank = None

    rows = campaign_model.by_track(track_id)
    if not rows:
        return jsonify(ok=True, matched=0)          # 남의 슬롯 — 조용히 200
    applied = 0
    for c in rows:
        # 등록일 ~ 종료일 밖의 날짜는 기록하지 않는다 (슬롯은 캠페인보다 오래 산다).
        # 시작일 전은 기록한다 — 그게 유입 전 기준 순위다.
        if not campaign_service.in_rank_window(c, day):
            continue
        if rank is None:                            # 300위 밖 — 순위는 남기지 않고 상태만 갱신
            continue
        campaign_service.apply_rank(c["id"], day, rank)
        applied += 1
    campaign_model.mark_tracked(track_id, "collected" if rank is not None else "not_found")
    current_app.logger.info("rank callback track=%s date=%s rank=%s → %d건", track_id, day, rank, applied)
    return jsonify(ok=True, matched=len(rows), applied=applied)
