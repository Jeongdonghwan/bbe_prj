"""Campaign orders: quote, create (campaign + payment in one transaction), transition (state table + status_log)."""
import math
import secrets
import threading
import time
from datetime import date, datetime, timedelta

from ..constants import DISCOUNT_RULES, TRANSITIONS, VAT_RATE
from ..models import campaign as campaign_model
from ..models import media as media_model
from . import payment_service


class CampaignError(Exception):
    pass


# ---- quote ---------------------------------------------------------------
def quote(unit_price, daily_qty, days):
    order = int(unit_price) * int(daily_qty) * int(days)
    discount = 0
    for minimum, rate in DISCOUNT_RULES:
        if order >= minimum:
            discount = int(round(order * rate))
            break
    supply = order - discount
    vat = int(round(supply * VAT_RATE))
    return {"order": order, "discount": discount, "supply": supply, "vat": vat, "total": supply + vat,
            "days": int(days), "daily_qty": int(daily_qty), "unit_price": int(unit_price)}


def days_between(start, end):
    return (end - start).days + 1


# ---- create ----------------------------------------------------------------
def new_order_no():
    for _ in range(20):
        no = "N" + "".join(str(secrets.randbelow(10)) for _ in range(9))
        if not campaign_model.order_no_exists(no):
            return no
    raise CampaignError("order_no allocation failed")


def create(user, media, form, method, depositor=None):
    """form: validated dict from blueprint (biz_name, product_name, target_url, main_keyword, sub_keywords,
    setting_keywords, keyword_mode, extra, start_date, end_date, daily_qty, warn_words)."""
    days = days_between(form["start_date"], form["end_date"])
    q = quote(media["unit_price"], form["daily_qty"], days)
    cid = campaign_model.insert({
        "order_no": new_order_no(), "user_id": user["id"], "channel": media["channel"], "media_id": media["id"],
        "status": "pay_wait",
        "biz_name": form["biz_name"], "product_name": form.get("product_name"), "target_url": form["target_url"],
        "nv_mid": form.get("nv_mid"),
        "main_keyword": form["main_keyword"], "sub_keywords": form.get("sub_keywords") or [],
        "setting_keywords": form.get("setting_keywords") or [], "keyword_mode": form.get("keyword_mode", "ai"),
        "extra": form.get("extra") or {},
        "start_date": form["start_date"], "end_date": form["end_date"],
        "daily_qty": form["daily_qty"], "total_qty": form["daily_qty"] * days,
        "unit_price": media["unit_price"], "discount": q["discount"], "vat": q["vat"], "paid_amount": q["total"],
        "pay_method": method, "warn_words": form.get("warn_words"),
    })
    campaign = campaign_model.get(cid)
    payment_service.create(campaign, user, method, depositor)
    return campaign


def earliest_start(now=None):
    """접수는 24시간, 구동은 익일부터. 마감 시각 이후 접수는 익익일.

    마감은 평일 ORDER_CUTOFF(16:00), 주말(토·일) ORDER_CUTOFF_WEEKEND(10:00) — 2026-09-30 JDH.
    판정은 이 함수 한 곳. 화면 문구는 constants.ORDER_CUTOFF_LABEL 을 쓴다.
    """
    from ..constants import order_cutoff_for
    now = now or datetime.now()
    return now.date() + timedelta(days=1 if now.strftime("%H:%M") < order_cutoff_for(now.date()) else 2)


def create_with_credit(user, media, form):
    """Credit model (2026-09-16): cost = 단가×일수량×일수, VAT 없음(충전 시 부과).
    Spends credit atomically, then creates the campaign already in review."""
    from . import credit_service
    days = days_between(form["start_date"], form["end_date"])
    cost = int(media["unit_price"]) * int(form["daily_qty"]) * days
    cid = campaign_model.insert({
        "order_no": new_order_no(), "user_id": user["id"], "channel": media["channel"], "media_id": media["id"],
        "status": "review",
        "biz_name": form["biz_name"], "product_name": form.get("product_name"), "target_url": form["target_url"],
        "nv_mid": form.get("nv_mid"),
        "main_keyword": form["main_keyword"], "sub_keywords": form.get("sub_keywords") or [],
        "setting_keywords": form.get("setting_keywords") or [], "keyword_mode": form.get("keyword_mode", "manual"),
        "extra": form.get("extra") or {},
        "start_date": form["start_date"], "end_date": form["end_date"],
        "daily_qty": form["daily_qty"], "total_qty": form["daily_qty"] * days,
        "unit_price": media["unit_price"], "discount": 0, "vat": 0, "paid_amount": cost,
        "pay_method": "credit", "paid_at": datetime.now(), "warn_words": form.get("warn_words"),
    })
    try:
        credit_service.spend(user["id"], cost, cid, f"광고비 · {media['name']} {days}일")
    except credit_service.CreditError:
        campaign_model.delete(cid)
        raise CampaignError("크레딧 잔액이 부족합니다. 충전 후 다시 시도해주세요.")
    campaign_model.add_log(cid, None, "review", user["id"], f"크레딧 결제 {cost:,}원 · 검수 대기")
    # 추적 스레드는 자기 커넥션으로 이 캠페인을 다시 읽는다 — 커밋 전에는 그 행이 안 보인다.
    from ..db import commit as db_commit
    db_commit()
    spawn_track_async(cid)  # 등록 즉시 순위 추적 시작 (검수 결과를 기다리지 않는다)
    return campaign_model.get(cid)


def update_pending(campaign, media, form, depositor=None):
    """Edit an unpaid (pay_wait) order in place; recomputes amount and payment."""
    from ..models import payment as payment_model
    if campaign["status"] != "pay_wait":
        raise CampaignError("결제 대기 상태에서만 수정할 수 있습니다.")
    days = days_between(form["start_date"], form["end_date"])
    q = quote(media["unit_price"], form["daily_qty"], days)
    campaign_model.update(campaign["id"], {
        "media_id": media["id"], "biz_name": form["biz_name"], "product_name": form.get("product_name"),
        "target_url": form["target_url"], "main_keyword": form["main_keyword"],
        "sub_keywords": form.get("sub_keywords") or [], "setting_keywords": form.get("setting_keywords") or [],
        "keyword_mode": form.get("keyword_mode", "ai"), "extra": form.get("extra") or {},
        "start_date": form["start_date"], "end_date": form["end_date"],
        "daily_qty": form["daily_qty"], "total_qty": form["daily_qty"] * days,
        "unit_price": media["unit_price"], "discount": q["discount"], "vat": q["vat"], "paid_amount": q["total"],
        "warn_words": form.get("warn_words"),
    })
    p = payment_model.get_for_campaign(campaign["id"])
    if p and p["status"] == "pending":
        fields = {"amount": q["total"]}
        if p["method"] == "bank" and depositor:
            fields["depositor"] = depositor
        payment_model.update(p["id"], fields)
    campaign_model.add_log(campaign["id"], "pay_wait", "pay_wait", campaign["user_id"], f"주문 수정 · {q['total']:,}원")
    return campaign_model.get(campaign["id"])


# ---- transition ----------------------------------------------------------
def transition(campaign, to_status, actor_id=None, memo=None):
    """The only way to change campaigns.status. Validates the table, writes status_log, handles refunds."""
    frm = campaign["status"]
    if to_status not in TRANSITIONS.get(frm, set()):
        raise CampaignError(f"허용되지 않는 상태 변경: {frm} → {to_status}")
    campaign_model.set_status(campaign["id"], to_status)
    campaign_model.add_log(campaign["id"], frm, to_status, actor_id, memo)
    _notify_status(campaign, frm, to_status, memo)
    if to_status in ("approved", "running"):
        spawn_track_async(campaign["id"])
    elif to_status in ("done", "stopped", "cancelled", "rejected"):
        untrack_if_unused(campaign)
    return campaign_model.get(campaign["id"])


def advance_due(actor_id=None):
    """종료일이 지난 구동건을 완료로 넘긴다 (크론). approved 로 남은 옛 주문도 함께 정리.

    지금은 승인하면 곧장 running 이라 앞쪽 루프는 옛 주문 전용이다. 뒤쪽 루프가 본론 —
    운영자가 매일 "완료"를 누르지 않아도 종료일이 지나면 알아서 닫힌다.
    """
    started = finished = 0
    for c in campaign_model.due_to_start():
        try:
            transition(c, "running", actor_id, "시작일 도래 · 자동 구동")
            started += 1
        except CampaignError:
            pass
    for c in campaign_model.due_to_finish():
        try:
            transition(c, "done", actor_id,
                       f"종료일 경과 · 자동 완료 (누적 {campaign_model.total_done_qty(c['id']):,}건)")
            finished += 1
        except CampaignError:
            pass
    return started, finished


# ---- 순위 자동 추적 (docs/RANK_INTEGRATION.md 2단계) ------------------------
def spawn_track(campaign):
    """순위 서버에 추적 슬롯을 만든다.

    쇼핑·스토어와 플레이스만. 쿠팡은 순위 서버에 수집기가 없다. 실패해도 상태 전이는 그대로 간다.
    """
    from . import rank_client
    platform = rank_client.TRACK_PLATFORM.get(campaign["channel"])
    if not platform or campaign.get("track_id"):
        return None
    r = rank_client.register_slot(campaign.get("main_keyword"), campaign.get("target_url"), platform)
    if not r.get("ok"):
        # 조용히 실패하면 순위가 왜 안 뜨는지 알 길이 없다. 사유를 남긴다.
        from flask import current_app
        current_app.logger.warning(
            "spawn_track 실패 %s %s '%s' %s — %s", campaign.get("order_no"), platform,
            campaign.get("main_keyword"), campaign.get("target_url"), r.get("message") or "응답 없음")
        return None
    # 슬롯은 같은 키워드·상품이면 재사용되므로 응답의 status 는 남의(옛) 수집 결과일 수 있다.
    # 이 캠페인 구간 안의 수집이 있을 때만 그 결과를 쓰고, 아니면 "수집 전(queued)"으로 둔다.
    status = "queued"
    if r.get("status") == "collected" and r.get("date"):
        try:
            day = date.fromisoformat(r["date"])
        except (ValueError, TypeError):
            day = None
        if day and in_rank_window(campaign, day):
            apply_rank(campaign["id"], day, r.get("rank"))
            status = "collected" if r.get("rank") is not None else "not_found"
    campaign_model.update(campaign["id"], {"track_id": r["trackId"], "track_status": status})
    apply_prod_name(campaign, r.get("prodNm"))   # 이미 아는 상품이면 이름이 바로 온다
    return r["trackId"]


WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


def apply_prod_name(campaign, prod_nm):
    """순위 서버가 준 실제 상품·업체명을 표시명으로 반영한다.

    등록 화면에서 이름을 받지 않으므로(2026-09-28) 이게 유일한 이름 출처다.
    product_name = 수집된 진짜 이름(없으면 아직 모른다는 뜻), biz_name = 목록 표시명.
    표시명이 아직 키워드 대체값일 때만 바꾼다 — 사람이 고쳐 둔 이름은 건드리지 않는다.
    """
    name = " ".join((prod_nm or "").split())[:120]
    if not name or campaign.get("product_name") == name:
        return False
    fields = {"product_name": name}
    if not campaign.get("biz_name") or campaign["biz_name"] == campaign.get("main_keyword"):
        fields["biz_name"] = name[:80]
    campaign_model.update(campaign["id"], fields)
    return True


def backfill_names(limit=100):
    """이름이 아직 안 들어온 추적 캠페인의 상품·업체명을 순위 서버에서 가져온다 (크론)."""
    from . import rank_client
    if not rank_client.configured():
        return 0
    filled = 0
    for c in campaign_model.tracked_without_name(limit):
        r = rank_client.slot_ranks(c["track_id"])
        if r.get("ok") and apply_prod_name(c, r.get("prodNm")):
            filled += 1
    return filled


# 순위 서버가 다루는 채널. 쿠팡은 수집기가 없다.
TRACKABLE = ("store", "place")
# 아직 이름·순위가 들어올 여지가 있는 상태. 끝난 건은 영원히 "수집중"으로 두지 않는다.
PENDING_STATUSES = ("review", "approved", "running")


def name_state(campaign):
    """표시명이 수집된 진짜 이름인지, 아직 키워드로 버티는 중인지.

    "named"      순위 서버가 준 이름이 들어와 있다
    "collecting" 들어올 예정 — 화면에 "수집중"을 띄운다
    "keyword"    들어올 일이 없다 (쿠팡, 또는 이미 끝난 건) — 키워드를 그대로 보여준다

    track_id 유무로 판정하지 않는다. 추적 등록은 요청 밖 스레드에서 돌아서 등록 직후에는
    비어 있고, 그 순간 화면에 키워드가 그대로 노출되는 게 이 판정의 옛 버그였다.
    """
    if campaign.get("product_name"):
        return "named"
    if campaign.get("channel") in TRACKABLE and campaign.get("status") in PENDING_STATUSES:
        return "collecting"
    return "keyword"


def rank_state(campaign):
    """순위 칸이 어떤 상태인지 한 곳에서 판정한다 — 화면마다 다르게 보이지 않게.

    "waiting"  순위 서버가 아직 수집 전 (조회중 스피너)
    "out"      수집은 됐는데 300위 밖
    "ranked"   순위가 있다
    "none"     추적을 걸지 않았다 (쿠팡, 또는 순위 서버 미설정)
    """
    if campaign.get("rank_now"):
        return "ranked"
    if campaign.get("track_status") == "not_found":
        return "out"
    # name_state 와 같은 이유로 track_id 를 보지 않는다 (등록 직후엔 아직 비어 있다).
    if campaign.get("channel") in TRACKABLE and campaign.get("status") in PENDING_STATUSES:
        return "waiting"
    return "none"


def rank_sheet(campaign):
    """순위 보고서(_ranks.html)에 넘길 값 — 사용자 화면과 어드민이 같은 표를 쓴다.

    쿠팡은 순위 서버에 수집기가 없어 빈 표를 돌려준다.
    """
    if campaign["channel"] == "coupang":
        return {"days": [], "today_rank": None, "delta": None}
    backfill_ranks(campaign)        # 콜백을 놓쳤으면 순위 서버에서 보정 (5분 스로틀)
    c = campaign_model.get(campaign["id"])
    # 행이 있으면 그날 수집이 된 것이다 — rank NULL 이면 300위 밖, 행이 없으면 아직 수집 전.
    rankmap = {d["date"]: d["rank"] for d in campaign_model.list_daily(c["id"])}
    live = c["channel"] in TRACKABLE and c["status"] in PENDING_STATUSES   # 아직 수집이 들어올 수 있나
    # 구동 전 기준 순위도 기록되므로 시작일보다 이른 기록이 있으면 거기서부터 보여준다.
    first = min([c["start_date"], *rankmap]) if rankmap else c["start_date"]
    days, cur, today = [], min(date.today(), c["end_date"]), date.today()

    def state(d):
        if d in rankmap:
            return "ranked" if rankmap[d] is not None else "out"
        return "pending" if (d == today and live) else "missed"   # 오늘은 조회중, 지난날은 수집 누락

    while cur >= first:
        days.append({"date": cur, "rank": rankmap.get(cur), "state": state(cur)})
        cur -= timedelta(days=1)
    today_rank = rankmap.get(today)
    delta = (c["rank_start"] - today_rank) if (c["rank_start"] and today_rank) else None
    # 시작 순위 칸: 기준값이 없을 때 "순위 밖"은 수집이 한 번이라도 됐을 때만 맞는 말이다.
    start_state = "ranked" if c["rank_start"] else ("out" if rankmap else ("pending" if live else "none"))
    return {"c": c, "days": days, "today_rank": today_rank, "today_state": state(today), "delta": delta,
            "start_state": start_state}


def backfill_nv_mid(limit=100):
    """비어 있는 nvMid 를 순위 서버 미리보기로 메운다 (크론).

    등록 화면의 미리보기는 사용자가 주소를 붙여넣은 그 순간에만 돈다 — 토큰이 없었거나,
    네이버가 상품 페이지를 막았거나(429), 미리보기가 끝나기 전에 제출하면 빈 채로 저장된다.
    순위 서버는 매일 수집한 검색결과에서 진짜 nvMid 를 찾아줄 수 있으므로 나중에 채워진다.
    """
    from . import rank_client
    if not rank_client.configured():
        return 0
    filled = 0
    for c in campaign_model.store_without_nv_mid(limit):
        r = rank_client.product_preview(c["target_url"])
        nv = str(r.get("nvMid") or "")
        # 경로에서 주워온 스토어 상품번호는 nvMid 가 아니다 — 그건 이미 별도 열로 뽑고 있다.
        if not r.get("ok") or not nv.isdigit() or r.get("nvMidSource") == "path":
            continue
        campaign_model.update(c["id"], {"nv_mid": nv[:20]})
        filled += 1
    return filled


def refresh_ranks_async(campaigns, limit=5):
    """목록을 열었을 때 순위가 비어 있는 건을 뒤에서 당겨온다.

    콜백이 늦거나 막혀도 사용자가 화면을 보는 것만으로 다음 새로고침에는 순위가 차 있다.
    응답을 막지 않으려고 스레드로 돌리고, backfill_ranks 의 5분 스로틀이 걸려 있어
    새로고침을 연타해도 순위 서버를 계속 때리지 않는다.
    """
    from flask import current_app, has_request_context
    if not has_request_context():
        return
    targets = [c["id"] for c in campaigns
               if c.get("track_id") and not c.get("rank_now")
               and c.get("status") in PENDING_STATUSES][:limit]
    if not targets:
        return
    app = current_app._get_current_object()

    def run():
        with app.app_context():
            for cid in targets:
                try:
                    c = campaign_model.get(cid)
                    if c:
                        backfill_ranks(c)
                except Exception:
                    app.logger.exception("순위 보정 실패 campaign=%s", cid)

    threading.Thread(target=run, name="rank-refresh", daemon=True).start()


def spawn_track_async(campaign_id):
    """추적 등록을 요청 밖으로 뺀다 — 사용자를 순위 서버 응답까지 기다리게 하지 않는다.

    순위 서버는 슬롯을 만들면서 상품·플레이스 페이지를 직접 읽어보기 때문에 몇 초씩 걸린다
    (네이버가 데이터센터 IP 를 막아 타임아웃까지 가는 일도 있다). 캠페인 저장은 이미 끝났으니
    붙잡아 둘 이유가 없다. 실패해도 cron 의 sync_ranks 가 검수 단계부터 다시 줍는다.
    """
    from flask import current_app, has_request_context
    app = current_app._get_current_object()
    # 크론·CLI 는 기다리는 사람이 없고, 데몬 스레드는 프로세스가 끝나면 잘려나간다 → 그대로 동기.
    if app.config.get("TESTING") or not has_request_context():
        return spawn_track(campaign_model.get(campaign_id))

    def run():
        with app.app_context():
            try:
                # 부른 쪽이 아직 커밋 전일 수 있다. 몇 번 기다려 보고 그래도 없으면 남긴다
                # (그런 건은 크론 sync_ranks 가 줍는다).
                for wait in (0, 0.3, 1.0, 3.0):
                    if wait:
                        time.sleep(wait)
                    c = campaign_model.get(campaign_id)
                    if c:
                        spawn_track(c)
                        return
                app.logger.warning("추적 등록 건너뜀 — 캠페인 %s 을 찾지 못했다", campaign_id)
            except Exception:
                app.logger.exception("추적 등록 실패 campaign=%s", campaign_id)

    threading.Thread(target=run, name=f"spawn-track-{campaign_id}", daemon=True).start()
    return None


def untrack_if_unused(campaign):
    """같은 track_id 를 쓰는 다른 진행 캠페인이 없을 때만 추적을 끊는다.

    순위 서버의 파트너 슬롯은 `partner:bbe` 공용 계정이라 우리가 지우면 트리플업 쪽
    추적도 끊긴다. 그래서 기본은 끄고(RANK_UNTRACK_ON_STOP), 켠 경우에만 삭제한다.
    """
    from flask import current_app

    from . import rank_client
    tid = campaign.get("track_id")
    if not tid or not current_app.config.get("RANK_UNTRACK_ON_STOP"):
        return False
    if campaign_model.count_active_by_track(tid, exclude_id=campaign["id"]):
        return False
    return bool(rank_client.untrack(tid).get("ok"))


_BACKFILL_AT = {}          # {campaign_id: datetime} — 프로세스 내 5분 스로틀


def backfill_ranks(campaign, throttle_min=5):
    """순위 화면 진입 시 오늘 순위가 없으면 순위 서버에서 직접 가져와 채운다.

    콜백은 재시도해도 끝내 실패할 수 있어서(배포 중이었다거나) 이 경로가 최종 보정이다.
    같은 캠페인을 연달아 열어도 서버를 계속 때리지 않도록 스로틀을 건다.
    """
    from . import rank_client
    tid = campaign.get("track_id")
    if not tid or campaign["status"] not in ("review", "approved", "running", "done"):
        return False
    if campaign_model.daily_rank(campaign["id"], date.today()):
        return False
    last = _BACKFILL_AT.get(campaign["id"])
    if last and (datetime.now() - last).total_seconds() < throttle_min * 60:
        return False
    _BACKFILL_AT[campaign["id"]] = datetime.now()
    r = rank_client.slot_ranks(tid)
    if not r.get("ok"):
        return False
    apply_prod_name(campaign, r.get("prodNm"))   # 순위를 가져오는 김에 이름도 채운다
    n = 0
    for row in r.get("ranks") or []:
        try:
            day = date.fromisoformat(str(row.get("date")))
        except (TypeError, ValueError):
            continue
        if not in_rank_window(campaign, day):
            continue
        prev = campaign_model.daily_rank(campaign["id"], day)
        if prev and prev["rank"] is not None:
            continue                       # 이미 순위가 있는 날 — 300위 밖(NULL) 행만 다시 볼 여지가 있다
        rk = row.get("rank")
        if prev and rk is None:
            continue
        apply_rank(campaign["id"], day, int(rk) if rk is not None else None)
        n += 1
    today = campaign_model.daily_rank(campaign["id"], date.today())
    if today:
        # 폴백으로 받아왔어도 "수집됨"이다 — 콜백만 이 값을 갱신하면 상태가 어긋난다.
        campaign_model.mark_tracked(campaign["id"], "collected" if today["rank"] is not None else "not_found")
    return bool(n)


def rank_window(campaign):
    """순위를 기록해도 되는 날짜 구간 (등록일 ~ 종료일).

    추적은 등록 즉시 시작하므로 **시작일 전 순위도 남긴다** — 그게 유입 전 기준값이고,
    일찍 추적을 거는 이유 자체다. 다만 파트너 슬롯은 캠페인보다 오래 살고 track_id 를
    다른 건과 공유하기도 해서, 등록 전 날짜는 남의 기간이라 버린다.
    """
    created = campaign.get("created_at")
    first = created.date() if hasattr(created, "date") else created
    start = campaign.get("start_date")
    if start and (first is None or start < first):
        first = start
    return first, campaign.get("end_date")


def in_rank_window(campaign, day):
    first, last = rank_window(campaign)
    return not ((first and day < first) or (last and day > last))


def apply_rank(campaign_id, day, rank):
    """콜백·폴백이 받은 순위를 기록. 어드민 수동 입력(record_rank)과 같은 자리에 쓴다.

    rank=None 은 "수집했는데 300위 밖"이다. 이것도 그날 행으로 남긴다(rank NULL) — 행이 없으면
    "아직 수집 전"이고 행이 있으면 "수집됨"이라는 뜻이 되어, 화면이 둘을 구분할 수 있다
    (2026-09-30 JDH "아직 순위체크가 안 된 당일 건이 왜 순위 밖이라고 나오냐").
    이미 순위가 있는 날을 NULL 로 덮지는 않는다(하루 두 번 수집 중 한 번만 잡혀도 순위는 순위다).
    """
    c = campaign_model.get(campaign_id)
    if not c:
        return None
    prev = campaign_model.daily_rank(campaign_id, day)
    if prev:
        done = prev["done_qty"]
    elif c["start_date"] and day < c["start_date"]:
        done = 0                       # 구동 전 기준 순위 — 작업한 건 없다
    else:
        done = c["daily_qty"]
    if rank is None:
        if not prev:
            campaign_model.upsert_daily(campaign_id, day, None, done)
        return None
    campaign_model.upsert_daily(campaign_id, day, rank, done)
    fields = {}
    # 늦게 도착한 옛 날짜가 "현재 순위"를 덮어쓰지 않게 — 가장 최근 날짜만 rank_now.
    latest = campaign_model.latest_ranked_date(campaign_id)
    if latest is None or day >= latest:
        fields["rank_now"] = rank
    # 기준 순위는 가장 이른 기록(대개 구동 전)이라, 순서와 무관하게 다시 읽어 맞춘다.
    first = campaign_model.first_rank(campaign_id)
    if first is not None and first != c["rank_start"]:
        fields["rank_start"] = first
    if fields:
        campaign_model.update(campaign_id, fields)
    return rank


_NOTIFY_TITLES = {
    "review": "결제가 확인되어 검수를 시작합니다", "approved": "검수를 통과했습니다 · 곧 구동 시작",
    "running": "검수를 통과했습니다 · 시작일부터 구동됩니다",
    "rejected": "검수 반려 — 결제 금액이 환불됩니다", "done": "캠페인이 완료되었습니다", "stopped": "캠페인이 중단되었습니다 · 잔여일분 환불",
    "cancelled": "주문이 취소되었습니다",
}


def _notify_status(campaign, frm, to_status, memo):
    from . import notify_service
    title = _NOTIFY_TITLES.get(to_status)
    if not title:
        return
    ntype = "payment" if (frm == "pay_wait" and to_status == "review") else "campaign"
    notify_service.push(campaign["user_id"], ntype, f"[{campaign['order_no']}] {title}",
                        f"/campaign/{campaign['channel']}?open={campaign['id']}")


def reject(campaign, admin_id, reason):
    if not reason:
        raise CampaignError("반려 사유는 필수입니다.")
    campaign_model.update(campaign["id"], {"reject_reason": reason})
    c = transition(campaign, "rejected", admin_id, f"반려 · {reason}")
    payment_service.refund(c, c["paid_amount"] - c["refund_amount"], admin_id, f"반려 · {reason}")
    return campaign_model.get(c["id"])


def stop(campaign, actor_id, reason="사용자 중단 요청"):
    """running -> stopped, refund remaining days pro-rata."""
    if campaign["status"] != "running":
        raise CampaignError("진행 중인 캠페인만 중단할 수 있습니다.")
    today = date.today()
    total_days = days_between(campaign["start_date"], campaign["end_date"])
    elapsed = max(0, min(total_days, (today - campaign["start_date"]).days + 1))
    remaining = total_days - elapsed
    amount = int(round(campaign["paid_amount"] * remaining / total_days)) if remaining > 0 else 0
    c = transition(campaign, "stopped", actor_id, f"{reason} · {elapsed}/{total_days}일 진행 · 잔여 {remaining}일분 환불")
    if amount > 0:
        payment_service.refund(c, amount, actor_id, f"중단 · 잔여 {remaining}일분")
    return campaign_model.get(c["id"])


def cancel(campaign, actor_id, reason="사용자 취소"):
    if campaign["status"] != "pay_wait":
        raise CampaignError("결제 대기 상태에서만 취소할 수 있습니다.")
    payment_service.cancel_pending(campaign, actor_id, reason)
    return transition(campaign, "cancelled", actor_id, reason)


def record_rank(campaign, day, rank, done_qty, actor_id=None):
    if campaign["status"] not in ("running", "approved", "done"):
        raise CampaignError("진행 중인 캠페인만 순위를 입력할 수 있습니다.")
    campaign_model.upsert_daily(campaign["id"], day, rank, done_qty)
    fields = {"rank_now": rank}
    if campaign["rank_start"] is None:
        fields["rank_start"] = rank
    campaign_model.update(campaign["id"], fields)
    return campaign_model.get(campaign["id"])


# ---- progress helpers (templates) -----------------------------------------
def progress(campaign, today=None):
    """{'total', 'elapsed', 'pct', 'label', 'sub', 'cls'} for the manage table progress cell."""
    today = today or date.today()
    total = days_between(campaign["start_date"], campaign["end_date"])
    st = campaign["status"]
    # 승인 직후에도 상태는 running 이지만 시작일 전이면 "MM.DD 시작" 으로 보여준다.
    if st in ("pay_wait", "review", "approved") or (st == "running" and today < campaign["start_date"]):
        return {"cls": "wait", "pct": 0, "label": f"{campaign['start_date']:%m.%d} 시작", "sub": f"{total}일", "total": total, "elapsed": 0}
    if st == "rejected":
        return {"cls": "rej", "pct": 0, "label": (campaign.get("reject_reason") or "반려"), "sub": "전액 환불", "total": total, "elapsed": 0}
    if st == "cancelled":
        return {"cls": "rej", "pct": 0, "label": "취소됨", "sub": "", "total": total, "elapsed": 0}
    elapsed = max(0, min(total, (today - campaign["start_date"]).days + 1))
    if st == "done":
        elapsed = total
    pct = int(elapsed / total * 100) if total else 0
    sub = f"{campaign['end_date']:%m.%d} 종료"
    if st == "stopped":
        sub = f"{total - elapsed}일분 환불" if campaign["refund_amount"] else "중단"
    return {"cls": "done" if st in ("done", "stopped") else "", "pct": pct, "label": f"{elapsed} / {total}일", "sub": sub,
            "total": total, "elapsed": elapsed}


def day_index(campaign, today=None):
    today = today or date.today()
    return max(0, (today - campaign["start_date"]).days + 1)
