"""Business constants shared across phases. (No point/prepaid concept — campaigns are paid per order via PG.)"""

# Member tier — assigned by operators (agency cert approval sets 'agency'; 'master' is manual).
GRADE_LABEL = {"biz": "사업자", "agency": "대행사", "master": "총판"}

# Campaign order discount — disabled 2026-08-31 (coupons/discounts may return later)
DISCOUNT_RULES = []
VAT_RATE = 0.10

MEDIA_SECTIONS = ["리워드", "유입", "복합"]

CHANNEL_LABEL = {"place": "플레이스", "store": "쇼핑·스토어", "coupang": "쿠팡"}
CHANNEL_CLASS = {"place": "c-place", "store": "c-store", "coupang": "c-coupang"}
STATUS_LABEL = {"pay_wait": "결제 대기", "review": "검수", "approved": "승인", "running": "진행",
                "rejected": "반려", "done": "완료", "stopped": "중단", "cancelled": "취소"}
STATUS_CLASS = {"pay_wait": "s-wait", "review": "s-review", "approved": "s-appr", "running": "s-run",
                "rejected": "s-rej", "done": "s-done", "stopped": "s-stop", "cancelled": "s-wait"}
STATUS_ORDER = ["pay_wait", "review", "approved", "running", "rejected", "done", "stopped", "cancelled"]

# Campaign status transition table (from -> allowed to).
TRANSITIONS = {
    "pay_wait": {"review", "cancelled"},
    "review": {"approved", "rejected"},
    "approved": {"running", "rejected"},
    "running": {"done", "stopped"},
}

PAY_METHOD_LABEL = {"card": "카드", "bank": "무통장입금"}
PAYMENT_STATUS_LABEL = {"pending": "결제 대기", "paid": "결제 완료", "partial_refund": "부분 환불",
                        "refunded": "전액 환불", "cancelled": "취소", "expired": "기한 만료"}
BANK_DUE_DAYS = 3

CUTOFF_TIME = "13:30"
DATE_PRESETS = [3, 5, 7, 10, 14]

# Store tracking slots (2-4-1)
STORE_SLOT_MAX = 10
RECO_PER_1000 = 1.5

# Link whitelist per channel (host suffix match)
URL_WHITELIST = {
    "place": ["m.place.naver.com", "place.naver.com", "map.naver.com", "naver.me", "pcmap.place.naver.com"],
    "store": ["smartstore.naver.com", "brand.naver.com", "shopping.naver.com", "m.smartstore.naver.com"],
    "coupang": ["coupang.com", "www.coupang.com", "m.coupang.com", "link.coupang.com"],
}

PLACE_CATEGORIES = ["병원·의원", "맛집·카페", "학원·교육", "미용·뷰티", "운동", "숙박", "일반 키워드"]



def reco_qty(monthly_volume):
    """Recommended daily qty for store slots: 1.5 per 1,000 daily searches, min 1."""
    return max(1, round(monthly_volume / 30 / 1000 * RECO_PER_1000))
