"""Business constants shared across phases. (No point/prepaid concept — campaigns are paid per order via PG.)"""

# Member tier — assigned by operators (agency cert approval sets 'agency'; 'master' is manual).
GRADE_LABEL = {"biz": "사업자", "agency": "대행사", "master": "총판"}

# Campaign order discount — disabled 2026-08-31 (coupons/discounts may return later)
DISCOUNT_RULES = []
VAT_RATE = 0.10

# Real media catalog (2026-09-21 JDH). name, group, unit price.
MEDIA_CATALOG = {
    "place": [
        ("짱구", "자체 프로그램", 50), ("비비안", "자체 프로그램", 40), ("파도", "자체 프로그램", 45),
        ("고스트", "기성 프로그램", 50), ("허니", "기성 프로그램", 55), ("유플레이스", "기성 프로그램", 50),
        ("탑플레이스", "기성 프로그램", 50),
    ],
    "store": [
        ("실루엣", "자체 · 리워드", 35), ("타이탄", "자체 · 리워드", 40), ("사도", "자체 · 리워드", 35),
        ("그린", "자체 · 리워드", 40), ("말론", "자체 · 리워드", 40), ("디벨롭", "자체 · 리워드", 35),
        ("미라지", "자체 · 리워드", 35), ("락스", "자체 · 리워드", 40), ("에보(EVO)", "자체 · 리워드", 35),
        ("이터널", "자체 · 유입플", 30), ("에로스", "자체 · 유입플", 30), ("싱크", "자체 · 유입플", 35),
        ("탑", "기성", 40), ("네스트", "기성", 40), ("뮤즈", "기성", 40), ("토큰플러스", "기성", 50),
        ("스토어플러스", "기성", 40), ("넥스트", "기성", 50), ("시드", "기성", 50), ("헤드", "기성", 40),
        ("스테이", "기성", 50), ("소보루", "기성", 50), ("딥", "기성", 40), ("덱스", "기성", 40),
        ("가드", "기성", 40), ("일루마", "기성", 50), ("포스", "기성", 40),
    ],
    "coupang": [("탑", "기성", 40), ("베스트", "기성", 50)],
}

MEDIA_SECTIONS = {
    "place": ["자체 프로그램", "기성 프로그램"],
    "store": ["자체 · 리워드", "자체 · 유입플", "기성"],
    "coupang": ["기성"],
}

MEDIA_COLORS = ["#6C5CE7", "#0EA5E9", "#8B5CF6", "#F97316", "#10B981", "#EC4899", "#F59E0B", "#2563EB"]
MEDIA_MIN_DAILY = 100
MEDIA_MAX_DAILY = 2000

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

PAY_METHOD_LABEL = {"card": "카드", "bank": "무통장입금", "credit": "크레딧"}
PAYMENT_STATUS_LABEL = {"pending": "결제 대기", "paid": "결제 완료", "partial_refund": "부분 환불",
                        "refunded": "전액 환불", "cancelled": "취소", "expired": "기한 만료"}
BANK_DUE_DAYS = 3

CUTOFF_TIME = "13:30"
DATE_PRESETS = [10, 20, 30]

# Left panel of the channel campaign wizard (spec 2026-09-21). 2·3 are indented under a group label.
def wizard_steps(channel):
    first = ("플레이스 정보 입력", "플레이스 링크와 이름") if channel == "place" else ("상품 정보 입력", "상품 URL과 이름")
    return [
        {"n": 1, "t": first[0], "d": first[1]},
        {"group": "광고 설정", "items": [
            {"n": 2, "t": "광고 유형", "d": "유형과 단가"},
            {"n": 3, "t": "유입 설정", "d": "키워드와 목표 유입수"},
        ]},
        {"n": 4, "t": "일정 설정", "d": "시작일과 기간"},
        {"n": 5, "t": "최종 확인", "d": "입력 내용 확인"},
    ]

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
