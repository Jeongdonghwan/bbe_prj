"""어드민 캠페인 로그 엑셀 추출 (2026-09-23 JDH).

시트 3장:
  캠페인   — 1행 = 캠페인 1건. 계정·상품ID(nvMid/스토어 상품번호)·플레이스ID·금액·환불(−).
  일별 로그 — 1행 = 캠페인 × 날짜. 예정 수량과 어드민이 기록한 실작업량·순위.
  주별 정산 — 주(월요일 시작) × 계정 × 채널 × 매체. 이용 일수·수량·금액, 환불은 별도 행에 −로.

일별·주별은 "이용"이 실제로 일어난 날만 센다: 상태가 running/done/stopped 이고, 시작일 이후 ~
min(종료일, 오늘, 중단일) 까지. 검수·승인 대기·반려·취소는 이용 행이 없고 환불 행만 나올 수 있다.
"""
import io
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from ..constants import CHANNEL_LABEL, PAY_METHOD_LABEL, STATUS_LABEL

USED_STATUSES = ("running", "done", "stopped")

# 쇼핑: 네이버 쇼핑 카탈로그/상품 페이지는 nvMid, 스마트스토어·브랜드스토어 주소는 스토어 상품번호.
_SHOP_PATTERNS = (
    (re.compile(r"search\.shopping\.naver\.com/(?:catalog|product)/(\d+)"), "nvMid"),
    (re.compile(r"shopping\.naver\.com/(?:catalog|product)/(\d+)"), "nvMid"),
    (re.compile(r"(?:smartstore|brand|m\.smartstore)\.naver\.com/[^/?#]+/products/(\d+)"), "스토어 상품번호"),
    (re.compile(r"coupang\.com/vp/products/(\d+)"), "쿠팡 상품번호"),
)
_PLACE_PATTERNS = (
    re.compile(r"place\.naver\.com/[a-z]+/(\d{5,})"),          # m.place / pcmap.place: /restaurant/123/home
    re.compile(r"map\.naver\.com/p/(?:entry/)?place/(\d{5,})"),
    re.compile(r"map\.naver\.com/v5/entry/place/(\d{5,})"),
    re.compile(r"[?&]placeId=(\d{5,})"),
    re.compile(r"[?&]id=(\d{5,})"),
)


def shop_product_id(url):
    """(id, kind) — 쇼핑 URL에서 상품 식별자. 없으면 (None, None)."""
    if not url:
        return None, None
    q = parse_qs(urlparse(url).query)
    if q.get("nvMid"):
        return q["nvMid"][0], "nvMid"
    for pat, kind in _SHOP_PATTERNS:
        m = pat.search(url)
        if m:
            return m.group(1), kind
    return None, None


def place_id(url):
    """플레이스 URL에서 플레이스 ID. naver.me 단축 주소는 풀 수 없어 None."""
    if not url:
        return None
    for pat in _PLACE_PATTERNS:
        m = pat.search(url)
        if m:
            return m.group(1)
    return None


def _week_start(d):
    return d - timedelta(days=d.weekday())


def _account(c):
    return c.get("user_biz") or c.get("nickname") or ""


def _used_range(c, today):
    """(first, last) 실제 이용 구간. 없으면 None."""
    if c["status"] not in USED_STATUSES or not c.get("start_date"):
        return None
    first, last = c["start_date"], c["end_date"] or c["start_date"]
    if c["status"] == "stopped" and c.get("updated_at"):
        u = c["updated_at"].date() if isinstance(c["updated_at"], datetime) else c["updated_at"]
        last = min(last, u)
    last = min(last, today)
    return (first, last) if first <= last else None


def _days(first, last):
    d = first
    while d <= last:
        yield d
        d += timedelta(days=1)


def build_workbook(rows, daily, refunds, date_from, date_to, today=None):
    """rows: campaign_model.admin_all 결과. daily: campaign_model.daily_records. refunds: credit_model.campaign_refunds."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    today = today or date.today()
    wb = Workbook()
    head_font = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="EEECFA")
    neg_font = Font(color="C0392B")

    def sheet(title, headers, widths):
        ws = wb.create_sheet(title)
        ws.append(headers)
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        for cell in ws[1]:
            cell.font = head_font
            cell.fill = head_fill
            cell.alignment = Alignment(vertical="center")
        ws.freeze_panes = "A2"
        return ws

    # ---------------------------------------------------------------- 캠페인
    ws = sheet("캠페인",
               ["주문번호", "상태", "채널", "회원", "이메일", "업체(계정)", "상품/업체명", "키워드", "매체",
                "상품ID", "ID 종류", "플레이스ID", "링크", "시작", "종료", "일수", "일 수량", "총 수량", "단가",
                "결제 금액", "환불(−)", "순매출", "결제수단", "시작 순위", "현재 순위", "결제일", "등록일"],
               [16, 9, 10, 12, 22, 16, 22, 14, 10, 16, 14, 14, 44, 11, 11, 6, 8, 9, 7, 12, 11, 12, 10, 8, 8, 17, 17])
    for c in rows:
        pid, kind = shop_product_id(c["target_url"]) if c["channel"] in ("store", "coupang") else (None, None)
        plid = place_id(c["target_url"]) if c["channel"] == "place" else None
        days = (c["end_date"] - c["start_date"]).days + 1 if c.get("start_date") and c.get("end_date") else None
        refund = c.get("refund_amount") or 0
        ws.append([c["order_no"], STATUS_LABEL.get(c["status"], c["status"]), CHANNEL_LABEL.get(c["channel"], c["channel"]),
                   c.get("nickname"), c.get("user_email"), c.get("user_biz"), c.get("product_name") or c.get("biz_name"),
                   c.get("main_keyword"), c.get("media_name"), pid, kind, plid, c["target_url"],
                   c.get("start_date"), c.get("end_date"), days, c.get("daily_qty"), c.get("total_qty"), c.get("unit_price"),
                   c.get("paid_amount"), -refund if refund else 0, (c.get("paid_amount") or 0) - refund,
                   PAY_METHOD_LABEL.get(c.get("pay_method"), c.get("pay_method")), c.get("rank_start"), c.get("rank_now"),
                   c.get("paid_at"), c.get("created_at")])
        if refund:
            ws.cell(row=ws.max_row, column=21).font = neg_font

    # ---------------------------------------------------------------- 일별 로그
    ws = sheet("일별 로그",
               ["날짜", "요일", "주문번호", "회원", "업체(계정)", "채널", "매체", "상품/업체명", "키워드",
                "예정 수량", "기록 수량", "순위", "단가", "예정 금액"],
               [11, 5, 16, 12, 16, 10, 10, 22, 14, 9, 9, 6, 7, 11])
    yoil = "월화수목금토일"
    weekly = defaultdict(lambda: {"campaigns": set(), "days": 0, "qty": 0, "done": 0, "done_seen": False, "amount": 0})
    for c in rows:
        rng = _used_range(c, today)
        if not rng:
            continue
        first, last = max(rng[0], date_from), min(rng[1], date_to)
        if first > last:
            continue
        for d in _days(first, last):
            rec = daily.get((c["id"], d))
            done = rec["done_qty"] if rec and rec.get("done_qty") is not None else None
            ws.append([d, yoil[d.weekday()], c["order_no"], c.get("nickname"), c.get("user_biz"),
                       CHANNEL_LABEL.get(c["channel"], c["channel"]), c.get("media_name"),
                       c.get("product_name") or c.get("biz_name"), c.get("main_keyword"),
                       c["daily_qty"], done, rec["rank"] if rec else None, c["unit_price"], c["daily_qty"] * c["unit_price"]])
            k = (_week_start(d), c["user_id"], _account(c), c["channel"], c["media_id"], c.get("media_name"))
            w = weekly[k]
            w["campaigns"].add(c["order_no"])
            w["days"] += 1
            w["qty"] += c["daily_qty"]
            w["amount"] += c["daily_qty"] * c["unit_price"]
            if done is not None:
                w["done"] += done
                w["done_seen"] = True

    # ---------------------------------------------------------------- 주별 정산
    ws = sheet("주별 정산",
               ["주 시작(월)", "주 종료(일)", "회원", "업체(계정)", "채널", "매체", "항목", "캠페인 수", "캠페인",
                "이용 일수", "이용 수량", "기록 수량", "금액", "비고"],
               [12, 12, 12, 16, 10, 10, 7, 9, 30, 9, 10, 10, 13, 30])
    by_id = {c["id"]: c for c in rows}
    lines = []
    for (wk, uid, acct, ch, mid, mname), w in weekly.items():
        nick = next((c.get("nickname") for c in rows if c["user_id"] == uid), "")
        lines.append((wk, acct, ch, mname, 0,
                      [wk, wk + timedelta(days=6), nick, acct, CHANNEL_LABEL.get(ch, ch), mname, "이용",
                       len(w["campaigns"]), ", ".join(sorted(w["campaigns"])),
                       w["days"], w["qty"], w["done"] if w["done_seen"] else None, w["amount"], None]))
    for r in refunds:
        c = by_id.get(r["campaign_id"])
        if not c:
            continue
        rd = r["created_at"].date() if isinstance(r["created_at"], datetime) else r["created_at"]
        if not (date_from <= rd <= date_to):
            continue
        wk = _week_start(rd)
        per_day = (c["daily_qty"] or 0) * (c["unit_price"] or 0)
        days_eq = -round(r["amount"] / per_day) if per_day else None
        qty_eq = -(r["amount"] // c["unit_price"]) if c.get("unit_price") else None
        lines.append((wk, _account(c), c["channel"], c.get("media_name"), 1,
                      [wk, wk + timedelta(days=6), c.get("nickname"), _account(c), CHANNEL_LABEL.get(c["channel"], c["channel"]),
                       c.get("media_name"), "환불", 1, c["order_no"], days_eq, qty_eq, None, -r["amount"],
                       f"{rd:%Y.%m.%d} {r.get('memo') or ''}".strip()]))
    lines.sort(key=lambda x: (x[0], x[1], x[2], x[3] or "", x[4]), reverse=False)
    for _, _, _, _, kind, vals in lines:
        ws.append(vals)
        if kind == 1:
            for col in (10, 11, 13):
                ws.cell(row=ws.max_row, column=col).font = neg_font
    ws.append([])
    ws.append([f"기간 {date_from:%Y.%m.%d} ~ {date_to:%Y.%m.%d} · 이용 = 구동 중·완료·중단 캠페인의 실제 구동일 기준(오늘까지) · "
               "환불은 크레딧 원장의 환불 시점 주에 − 로 기록 · 기록 수량은 어드민이 입력한 일별 작업량 합(없으면 빈칸)"])

    wb.remove(wb["Sheet"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
