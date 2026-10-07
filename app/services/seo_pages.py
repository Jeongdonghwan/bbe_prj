"""SEO 기본 페이지 (/learn/<slug>/) — 판매자·사업자 의도 키워드 (2026-10-07, docs/SEO_PLAN.md).

타깃은 손님이 아니라 **마케팅을 직접 하려는 사장님·판매자**다. 그래서 페이지 주제(주소·제목·h1)는
"치과 마케팅", "강남 치과 마케팅", "스마트스토어 리뷰 늘리기" 같은 판매자 검색어이고,
손님 검색량(data/seo/place·biz·store.json)은 페이지 안의 **근거 데이터**로만 쓴다
("우리 상권 손님이 한 달에 몇 번 찾는지"). 판매자 키워드 검색량은 data/seo/seller.json.

페이지 종류 (registry 가 slug → 빌더를 정한다):
  bizhub     /learn/치과-마케팅/                업종 허브
  bizangle   /learn/치과-리뷰-관리/             업종 × 각도
  regionbiz  /learn/강남-치과-마케팅/            지역 × 업종 (손님 검색량 실측)
  regionhub  /learn/강남-마케팅/                지역 허브
  topic      /learn/스마트스토어-리뷰-늘리기/      플랫폼 × 각도
  storecat   /learn/스마트스토어-무선청소기-판매/   쇼핑 카테고리

문장은 **문장 단위 뱅크**에서 slug 해시로 고른다 — 문단 하나가 여러 뱅크의 문장 조합이라 같은
묶음 안의 페이지끼리도 겹치는 부분이 적다. 여기에 페이지마다 다른 실측 숫자 문장이 붙는다.
원칙: 순위·노출 '보장' 류 표현 금지(오히려 경계), 가짜 리뷰·어뷰징 권유 금지, 키워드 반복 금지.
scripts/seo_check.py --learn 이 금지어·유사도(3-gram Jaccard ≤ 35%)·글자수·title/description 을 검사한다.
"""
import hashlib
import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent.parent / "data" / "seo"
MAX_REGIONBIZ = 520     # 지역×업종 페이지 상한 — 손님 검색량 큰 순


# ================================================================== helpers
def _h(*parts):
    return int(hashlib.md5("|".join(map(str, parts)).encode()).hexdigest(), 16)


def pick(bank, key, salt=""):
    return bank[_h(key, salt) % len(bank)]


def sample(pool, key, n, salt=""):
    return sorted(pool, key=lambda x: _h(key, salt, x if isinstance(x, str) else x[0]))[:n]


def para(banks, key, salt, v):
    """문단 = 뱅크마다 한 문장씩 (각자 다른 해시). 문장 조합이 페이지마다 달라진다."""
    return " ".join(pick(b, key, f"{salt}{i}").format(**v) for i, b in enumerate(banks))


def fmt(n):
    return f"{int(n):,}"


def jo(word, pair):
    """받침에 맞는 조사. pair='은는' / '을를' / '이가' / '과와'."""
    w = word.strip("'\" ")
    last = w[-1] if w else "a"
    if "가" <= last <= "힣":
        has = (ord(last) - 0xAC00) % 28 != 0
    else:
        has = last.lower() in "lmnr0136789"
    return pair[0] if has else pair[1]


def fit_desc(text):
    """description 80~160자에 맞춘다."""
    tail = " 대행사 없이 직접 운영하려는 사업자를 위해 순서·비용·주의점을 정리했습니다."
    if len(text) < 80:
        text = text + tail
    return text if len(text) <= 160 else text[:157].rstrip() + "…"


@lru_cache(maxsize=1)
def _load():
    out = {}
    for name in ("place", "biz", "store", "seller"):
        p = DATA / f"{name}.json"
        out[name] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"meta": {}, "rows": []}
    return out


def meta():
    return _load()["place"].get("meta", {})


def seller_vol(kw):
    """판매자 키워드 월간 검색량 (data/seo/seller.json, 공백 무시). 없으면 None."""
    return _load()["seller"]["rows"].get(kw.replace(" ", "")) if isinstance(_load()["seller"]["rows"], dict) else None


# ================================================================== 공통 문장 뱅크
GROUP_NOTE = {
    "병원·의원": ["의료기관은 의료법상 광고 규정을 따릅니다. 치료 효과 보장, 다른 의료기관과의 비교, 환자 치료 경험담을 광고에 쓰는 것은 제한되고, 일정 매체 광고는 사전 심의 대상입니다.",
                "병의원 홍보 문구는 '효과를 단정하지 않는다'가 기본입니다. 플레이스 소개·블로그·리뷰 답글까지 같은 기준으로 점검하세요.",
                "진료과목·진료시간·의료진 정보가 정확한지가 병의원 플레이스에서 가장 중요합니다. 체험기 형식의 홍보는 의료광고 규정에 걸릴 수 있습니다."],
    "뷰티": ["시술 전후 사진은 클릭을 좌우하지만 과한 보정이나 효과 단정은 불만 리뷰로 돌아옵니다. 가격표를 명확히 올려 두면 문의 단계 이탈이 줄어듭니다.",
           "뷰티 업종은 '오늘 예약 가능'이 보이는 곳으로 손님이 몰리는 경향이 있습니다. 예약 가능 시간을 플레이스 예약과 맞춰 두세요.",
           "재방문 주기가 짧은 업종이라 신규 유입만큼 단골 관리(리뷰 답글, 소식 알림)가 매출에 중요합니다."],
    "운동": ["운동 시설은 체험·상담 예약 동선이 핵심입니다. 회원권 가격대를 공개하는 편이 상담 전환에 유리한 경우가 많습니다.",
           "기구·샤워실·주차 사진을 충분히 올리세요. 처음 찾는 사람은 분위기를 사진으로 판단합니다.",
           "새해·여름 전처럼 수요가 몰리는 시기가 분명한 업종입니다. 성수기 4~6주 전부터 순위를 관리하세요."],
    "교육": ["학원·교습소는 학원법상 교습비 게시 의무가 있습니다. 과목·대상·시간표를 명확히 적어 두면 학부모 문의가 짧아집니다.",
           "교육 업종은 학기 시작 전후로 검색이 몰립니다. 방학·개학 시즌 한두 달 전부터 준비하는 게 효율적입니다.",
           "수강 후기는 학부모가 가장 많이 보는 정보입니다. 실제 수강생 후기를 쌓되 대가를 조건으로 한 후기는 피하세요."],
    "음식점": ["음식점은 메뉴 사진·가격·웨이팅·주차 정보가 결정적입니다. 리뷰 이벤트는 대가를 조건으로 좋은 평가를 요구하지 않도록 주의하세요.",
            "점심·저녁 시간대에 검색이 몰립니다. 영업시간과 브레이크타임을 정확히 표시하지 않으면 헛걸음 리뷰가 쌓입니다.",
            "음식점은 사진 리뷰의 영향이 큽니다. 대표 메뉴 사진을 매장에서 직접 찍어 올리고, 계절 메뉴는 소식으로 알리세요."],
    "생활 서비스": ["생활 서비스는 견적 문의가 곧 매출입니다. 대표 작업 사례와 대략적인 가격 범위를 올려 두면 문의 품질이 좋아집니다.",
               "출장·방문형 서비스라면 서비스 가능 지역을 명확히 적으세요. 지역 키워드와 실제 서비스 범위가 맞아야 헛문의가 줄어듭니다.",
               "작업 전후 사진과 작업 기간을 함께 보여주면 신뢰가 쌓입니다. 견적 응답 속도도 전환율을 크게 좌우합니다."],
    "전문 서비스": ["변호사·세무사 등 전문직은 직역별 광고 규정이 있습니다. 승소율·결과 보장 같은 표현은 피하고 전문 분야를 구체적으로 적으세요.",
               "전문 서비스는 상담 예약 전환이 목표입니다. 상담 가능 시간과 방문·전화·온라인 상담 여부를 명확히 표시하세요.",
               "전문직 마케팅은 신뢰가 전부입니다. 과장된 실적 대신 다루는 사건·업무 유형과 절차를 설명하는 글이 문의로 이어집니다."],
}

CAUTION = [
    ["'상위노출 보장', '1위 보장'을 내거는 업체는 경계하세요.", "보장을 약속하는 업체일수록 계약 조건을 꼼꼼히 확인해야 합니다.",
     "검색 순위를 보장할 수 있는 곳은 없습니다.", "순위 보장을 앞세우는 영업은 일단 의심하는 게 맞습니다."],
    ["순위는 네이버가 정하고 매일 바뀝니다.", "노출 순서는 검색엔진의 판단이라 외부에서 고정할 수 없습니다.",
     "같은 키워드도 시간대·위치에 따라 순위가 달라 보입니다.", "알고리즘은 공개되지 않고 수시로 바뀝니다."],
    ["가짜 리뷰나 대가성 리뷰는 정책 위반이라 적발 시 리뷰 삭제·노출 제한이 있을 수 있습니다.",
     "리뷰를 사거나 지인을 동원하는 방식은 길게 보면 손해입니다.",
     "실제 고객 경험이 쌓이는 구조를 만드는 것이 유일하게 오래가는 방법입니다.",
     "키워드를 소개글에 반복해 넣는 방식도 효과가 없고 신뢰만 깎습니다."],
]

MEASURE = [
    ["무엇을 바꿨는지와 그 뒤 순위가 어떻게 됐는지를 같은 표에 적어 두세요.", "변경 사항과 결과를 날짜별로 기록하는 습관이 셀프 운영의 핵심입니다.",
     "시작 전 순위를 기준값으로 남겨 두지 않으면 효과를 판단할 수 없습니다.", "매일 같은 시각에 순위를 확인해야 비교가 됩니다."],
    ["최소 1~2주의 추이를 보고 판단하세요.", "하루 이틀 변화로 결론 내리면 잘못 판단하기 쉽습니다.",
     "단기 급등보다 2주 이상 유지되는지가 중요합니다.", "주 단위로 묶어서 보면 일시적인 흔들림이 걸러집니다."],
    ["순위보다 전화·예약·문의 수가 더 정확한 성과 지표입니다.", "결국 봐야 할 것은 순위가 아니라 문의와 매출입니다.",
     "마이마케팅은 캠페인을 등록하는 순간부터 일자별 순위를 자동으로 기록합니다.", "순위와 문의 수를 나란히 놓고 보면 무엇이 효과였는지 보입니다."],
]

COST = [
    ["유입 캠페인 비용은 1회 단가 × 일일 유입수 × 일수가 전부입니다.", "셀프 운영 비용은 단가와 수량, 기간으로 정해집니다.",
     "월 고정비나 세팅비 없이 쓴 만큼만 계산됩니다.", "비용 구조가 단순해야 효과가 없을 때 바로 멈출 수 있습니다."],
    ["마이마케팅 {plat} 매체는 1회 {pmin}원부터라, 하루 100회씩 10일이면 {ex10}원부터입니다.",
     "{plat} 기준 최저 단가 {pmin}원으로 계산하면 일 100회 × 10일에 {ex10}원입니다.",
     "예를 들어 {plat} 매체 최저 단가({pmin}원)로 100회씩 10일 진행하면 {ex10}원이 듭니다."],
    ["처음에는 최소 수량·최소 기간으로 시작해 반응을 보고 늘리세요.", "작게 시작해서 문의 수 변화를 확인한 뒤 늘리는 것이 안전합니다.",
     "메인 키워드 하나로 시작하고, 효과가 확인되면 연관 키워드로 넓히세요.", "예산보다 먼저 정할 것은 무엇으로 효과를 판단할지입니다."],
]

# ================================================================== 각도별 뱅크 (업종 × 각도, 플랫폼 × 각도에 공용)
# {plat} = 플레이스/스마트스토어/쿠팡, {subj} = 업종명 또는 '상품'
ANGLES = {
    "홍보-방법": {
        "label": "홍보 방법", "plats": ["플레이스"],
        "intro": [["{subj} 홍보는 손님이 실제로 찾는 곳에 정확한 정보를 올려 두는 것에서 시작합니다.",
                   "{subj} 홍보의 출발점은 광고비가 아니라 손님이 검색했을 때 보이는 첫 화면입니다.",
                   "{subj} 사장님이 직접 할 수 있는 홍보는 생각보다 많습니다.",
                   "대행사에 맡기기 전에 {subj} 홍보에서 무엇이 효과가 있는지부터 알아 두면 비용을 크게 줄일 수 있습니다."],
                  ["네이버 지도·플레이스, 블로그 후기, 리뷰 관리가 세 축입니다.",
                   "손님은 대부분 지도 앱에서 업체를 비교하고 결정합니다.",
                   "검색 → 플레이스 → 리뷰 확인 → 전화·예약이 가장 흔한 흐름입니다.",
                   "온라인에서 처음 보이는 정보가 곧 첫인상입니다."]],
        "steps": ["플레이스 기본 정보(영업시간·메뉴·가격·사진) 빠짐없이 채우기", "대표 사진을 가장 잘 팔리는 서비스로 교체하기",
                  "리뷰에 빠짐없이 답글 달기", "소식 탭을 2주에 한 번 업데이트하기", "단골 고객에게 리뷰 작성 안내하기(대가 조건 없이)",
                  "블로그·SNS에 실제 작업·메뉴 사진 올리기", "경쟁 업체 상위 3곳과 정보 충실도 비교하기",
                  "전화·예약 버튼이 실제로 응대 가능한지 점검하기", "검색 키워드별 순위를 매일 같은 시각에 기록하기",
                  "기본기가 갖춰진 뒤 필요할 때만 유입 캠페인 쓰기"],
        "faq": [("{subj} 홍보, 무엇부터 해야 하나요?", ["플레이스 기본 정보를 빠짐없이 채우는 것이 가장 싸고 효과가 큽니다. 그다음 리뷰 답글, 소식 업데이트 순서로 하세요.",
                                                "돈을 쓰기 전에 무료로 할 수 있는 것(정보 정비·리뷰 관리·사진 교체)부터 하세요. 대부분의 업체가 여기서 차이가 납니다."]),
                ("블로그 체험단은 효과가 있나요?", ["후기 콘텐츠가 쌓인다는 장점이 있지만, 대가를 받은 글은 그 사실을 표시해야 합니다. 표시 없는 후기는 표시광고법 위반이 될 수 있습니다.",
                                          "효과는 업종마다 다릅니다. 진행한다면 협찬 표시를 반드시 하고, 실제 방문 경험이 담긴 글인지 확인하세요."])],
    },
    "플레이스-상위노출": {
        "label": "플레이스 상위노출", "plats": ["플레이스"],
        "intro": [["{subj} 플레이스 상위노출은 정보 품질, 손님 반응, 꾸준한 관리가 함께 쌓인 결과입니다.",
                   "플레이스 순위를 올리는 지름길은 없지만, 순위가 오르는 업체들의 공통점은 분명합니다.",
                   "{subj} 플레이스 순위는 '얼마나 정확하고 활발한 업체인가'를 네이버가 판단한 결과입니다.",
                   "상위노출을 원한다면 먼저 우리 업체가 지금 몇 위인지, 어떤 키워드에서 보이는지부터 확인하세요."],
                  ["어느 업체도 순위를 보장할 수는 없습니다.", "순위는 매일 오르내리므로 추이로 봐야 합니다.",
                   "같은 상권 경쟁 업체와의 비교가 출발점입니다.", "기본기가 갖춰진 업체만 유입 효과가 오래갑니다."]],
        "steps": ["업체명은 실제 상호 그대로 — 지역명·키워드를 억지로 넣지 않기", "업체 소개에 주요 서비스와 지역을 자연스럽게 한두 번",
                  "카테고리를 실제 업종과 정확히 맞추기", "사진 수·최신성을 경쟁 업체 이상으로", "리뷰 답글로 활발한 업체라는 신호 주기",
                  "저장하기·길찾기·전화 같은 실제 손님 행동이 늘도록 정보 정비", "키워드별 순위를 매일 기록해 기준값 만들기",
                  "정보 정비 후 2주 추이를 보고 유입 캠페인 여부 결정하기", "캠페인은 최소 수량·최소 기간으로 시작하기", "순위와 함께 전화·예약 수 변화를 기록하기"],
        "faq": [("플레이스 상위노출을 보장받을 수 있나요?", ["아니요. 순위는 네이버가 정하며 누구도 보장할 수 없습니다. 보장을 내거는 업체는 오히려 조심하세요.",
                                                  "보장은 불가능합니다. 대신 일자별 순위를 기록하면서 무엇이 효과가 있었는지 직접 확인하는 방식이 가장 안전합니다."]),
                ("유입 캠페인만 하면 순위가 오르나요?", ["정보가 빈약한 상태라면 효과가 오래가지 않습니다. 정보 정비가 먼저이고 캠페인은 노출을 앞당기는 보조 수단입니다.",
                                              "보장할 수 없습니다. 유입은 여러 신호 중 하나일 뿐이고, 업체 정보 품질과 실제 손님 반응이 함께 갖춰져야 순위가 유지됩니다."])],
    },
    "리뷰-관리": {
        "label": "리뷰 관리", "plats": ["플레이스"],
        "intro": [["{subj} 손님은 리뷰를 보고 결정합니다.", "{subj} 업종에서 리뷰는 사진 다음으로 많이 보는 정보입니다.",
                   "리뷰 관리는 {subj} 마케팅에서 비용이 가장 적게 드는 영역입니다.", "좋은 리뷰를 늘리는 방법은 결국 좋은 경험을 남기고 작성을 부탁하는 것입니다."],
                  ["리뷰 수보다 최근성·답글 여부가 신뢰를 좌우합니다.", "불만 리뷰에 대한 답글이 오히려 신뢰를 만들기도 합니다.",
                   "가짜 리뷰는 적발되면 손실이 훨씬 큽니다.", "영수증 리뷰 안내만 꾸준히 해도 리뷰 수가 눈에 띄게 늘어납니다."]],
        "steps": ["결제·퇴장 동선에 영수증 리뷰 안내문 두기", "모든 리뷰에 48시간 안에 답글 달기", "불만 리뷰는 사실 확인 후 개선 내용을 답글로 남기기",
                  "리뷰에 자주 나오는 단어를 업체 소개·메뉴 설명에 반영하기", "사진 리뷰를 부탁할 때 대가를 조건으로 걸지 않기",
                  "별점 조건 이벤트·지인 동원 리뷰는 하지 않기", "월별 리뷰 수와 평균 평점을 기록하기", "리뷰 답글에 키워드를 반복해 넣지 않기",
                  "재방문 손님에게 소식·쿠폰으로 관계 이어가기", "리뷰에서 나온 불편 사항을 실제로 고치고 공지하기"],
        "faq": [("리뷰 이벤트를 해도 되나요?", ["실제 방문 고객에게 리뷰를 안내하는 것은 괜찮지만, 대가를 조건으로 좋은 평가를 요구하거나 가짜 리뷰를 쓰는 것은 정책 위반입니다.",
                                        "작성 자체를 부탁하는 것은 문제없습니다. 별점 조건 보상, 구매 리뷰, 지인 동원은 피하세요."]),
                ("악성 리뷰는 어떻게 대응하나요?", ["감정적으로 반박하기보다 사실 관계를 정중히 설명하고 개선 내용을 남기세요. 명백한 허위라면 네이버 신고 절차를 이용합니다.",
                                          "답글은 다른 손님이 읽는다는 생각으로 쓰세요. 차분한 대응 자체가 신뢰가 됩니다."])],
    },
    "네이버-광고": {
        "label": "네이버 광고", "plats": ["플레이스"],
        "intro": [["{subj} 네이버 광고는 검색광고(파워링크), 플레이스 광고, 유입 캠페인처럼 성격이 다른 선택지가 있습니다.",
                   "네이버에서 {subj} 손님을 만나는 유료 방법은 크게 세 가지입니다.",
                   "{subj} 사장님이 광고비를 쓰기 전에 알아야 할 것은 광고마다 과금 방식과 노출 위치가 다르다는 점입니다.",
                   "광고는 '어디에 보이고, 무엇에 돈을 내는가'로 비교해야 합니다."],
                  ["검색광고는 클릭당 과금, 플레이스 광고는 플레이스 영역 노출, 유입 캠페인은 유입 수량 기준입니다.",
                   "광고마다 장단점이 있어 업종·예산에 따라 조합이 달라집니다.", "광고 전 기본 정보 정비가 안 돼 있으면 클릭 후 이탈이 늘어납니다.",
                   "광고는 기본기를 대신하지 못하고 앞당겨 줄 뿐입니다."]],
        "steps": ["검색광고 키워드 도구로 '{subj}' 관련 검색량 먼저 확인하기", "광고 랜딩(플레이스·홈페이지) 정보 정비하기",
                  "일 예산 상한을 정하고 작게 시작하기", "광고 문구에 과장·보장 표현 쓰지 않기", "업종 광고 규정(의료·법률 등) 확인하기",
                  "광고별 클릭·전화·예약 수를 따로 기록하기", "2주 단위로 효율 낮은 키워드 정리하기", "유입 캠페인은 순위 추적과 함께 쓰기",
                  "경쟁 업체가 어떤 키워드에 광고하는지 확인하기", "광고를 끈 뒤의 변화도 기록해 실제 효과 판단하기"],
        "faq": [("검색광고와 플레이스 광고, 무엇이 먼저인가요?", ["손님이 지도에서 결정하는 업종이라면 플레이스 정보 정비와 플레이스 노출이 먼저인 경우가 많습니다. 검색광고는 키워드별 클릭 비용을 확인한 뒤 작게 시작하세요.",
                                                     "업종마다 다릅니다. 지역 기반 업종은 플레이스, 넓은 지역에서 찾는 서비스는 검색광고의 비중이 큽니다."]),
                ("광고비는 얼마부터 시작하나요?", ["정해진 최소 금액보다 '효과를 판단할 수 있는 최소 기간'이 중요합니다. 2주 정도 작게 운영해 문의 수를 보고 늘리세요.",
                                         "작게 시작하세요. 일 예산 상한을 두고 2주 결과로 판단하는 게 안전합니다."])],
    },
    "마케팅-비용": {
        "label": "마케팅 비용", "plats": ["플레이스"],
        "intro": [["{subj} 마케팅 비용은 '무엇을, 얼마나, 얼마 동안' 하느냐로 정해집니다.",
                   "대행사 견적만 보면 {subj} 마케팅 비용이 막연하지만, 항목별로 나누면 계산이 됩니다.",
                   "{subj} 사장님들이 가장 많이 묻는 것이 비용입니다.", "마케팅 비용은 고정비와 변동비로 나눠 보면 판단이 쉬워집니다."],
                  ["월 고정 계약은 무엇을 하는지 보이지 않는 경우가 많습니다.", "셀프 운영은 단가가 공개돼 있어 비교가 쉽습니다.",
                   "효과가 없을 때 바로 멈출 수 있는지도 비용의 일부입니다.", "가장 비싼 비용은 효과 없는 계약을 계속하는 것입니다."]],
        "steps": ["무료로 할 수 있는 것(정보 정비·리뷰 관리) 먼저 하기", "유료 수단별 과금 방식(클릭·노출·유입) 비교하기",
                  "월 고정 계약이라면 작업 내역과 순위 기록 공유 여부 확인하기", "예산 상한을 정하고 2주 단위로 점검하기",
                  "비용 대비 문의·예약 수를 기록하기", "세팅비·위약금 조건 확인하기", "같은 예산으로 셀프 운영했을 때와 비교하기",
                  "성수기·비수기 예산을 다르게 잡기", "효과 없는 채널은 바로 정리하기", "부가세 포함 여부 확인하기"],
        "faq": [("월 마케팅 대행 비용은 보통 얼마인가요?", ["업체·범위에 따라 편차가 큽니다. 금액보다 '무엇을 하는지'와 '결과를 어떻게 공유하는지'를 먼저 확인하세요.",
                                               "정가가 없는 시장이라 비교가 어렵습니다. 작업 항목별 단가를 요청하고, 셀프로 했을 때의 비용과 비교해 보세요."]),
                ("셀프 운영 비용은 어떻게 계산하나요?", ["유입 캠페인은 1회 단가 × 일일 유입수 × 일수입니다. 플레이스 기준 1회 {pmin}원부터, 100회 × 10일이면 {ex10}원입니다.",
                                              "단가 × 수량 × 기간입니다. 예를 들어 {plat} 최저 단가 {pmin}원으로 100회씩 10일이면 {ex10}원입니다."])],
    },
    "키워드-찾기": {
        "label": "키워드 찾기", "plats": ["플레이스"],
        "intro": [["{subj} 마케팅의 시작은 손님이 실제로 어떤 말로 검색하는지 아는 것입니다.",
                   "같은 {subj}라도 손님은 지역명, 역 이름, 세부 서비스명으로 다양하게 검색합니다.",
                   "키워드를 잘못 고르면 순위가 올라도 문의가 늘지 않습니다.", "{subj} 키워드는 검색량과 전환 의도를 함께 봐야 합니다."],
                  ["검색량이 크다고 무조건 좋은 키워드는 아닙니다.", "롱테일 키워드는 경쟁이 덜하고 의도가 분명합니다.",
                   "네이버 검색광고 키워드 도구나 마이마케팅 키워드 조회로 무료 확인할 수 있습니다.", "메인 키워드 하나와 연관 키워드 몇 개로 묶어 관리하세요."]],
        "steps": ["'지역 + {subj}' 형태 기본 키워드 검색량 확인하기", "역 이름·동 이름 조합 키워드 확인하기", "세부 서비스명 키워드 찾기",
                  "모바일·PC 비중 확인하기", "경쟁 정도가 낮은 연관 키워드 골라 두기", "키워드별 현재 순위 기록하기",
                  "키워드를 소개글에 반복해 넣지 않기", "계절·시기별 검색량 변화 확인하기", "문의 손님에게 어떻게 찾았는지 물어보기",
                  "메인 1개 + 연관 3~5개로 관리 목록 만들기"],
        "faq": [("키워드 검색량은 어디서 보나요?", ["네이버 검색광고의 키워드 도구에서 월간 검색량을 볼 수 있습니다. 마이마케팅 키워드 조회에서도 로그인 후 하루 30회 무료로 확인할 수 있습니다.",
                                          "마이마케팅 키워드 조회(무료, 하루 30회)나 네이버 검색광고 키워드 도구를 쓰세요."]),
                ("검색량이 적은 키워드는 버려야 하나요?", ["아닙니다. 검색량이 적은 대신 의도가 분명해 전환이 잘 되는 경우가 많습니다. 여러 개를 묶어 관리하세요.",
                                              "롱테일은 하나하나는 작아도 합치면 큽니다. 경쟁이 덜해 순위 관리도 쉽습니다."])],
    },
}

# 플랫폼 × 각도 주제 페이지 (판매자 검색어 그대로)
TOPICS = [
    ("플레이스", "상위노출", "플레이스-상위노출"), ("플레이스", "순위 올리기", "플레이스-상위노출"), ("플레이스", "리뷰 늘리기", "리뷰-관리"),
    ("플레이스", "광고", "네이버-광고"), ("플레이스", "마케팅", "홍보-방법"), ("플레이스", "키워드 설정", "키워드-찾기"),
    ("플레이스", "리워드", "마케팅-비용"), ("플레이스", "마케팅 비용", "마케팅-비용"),
    ("스마트스토어", "상위노출", "플레이스-상위노출"), ("스마트스토어", "순위 올리기", "플레이스-상위노출"), ("스마트스토어", "리뷰 늘리기", "리뷰-관리"),
    ("스마트스토어", "광고", "네이버-광고"), ("스마트스토어", "마케팅", "홍보-방법"), ("스마트스토어", "키워드 찾기", "키워드-찾기"),
    ("스마트스토어", "트래픽", "마케팅-비용"), ("스마트스토어", "유입 늘리기", "홍보-방법"),
    ("쿠팡", "상위노출", "플레이스-상위노출"), ("쿠팡", "리뷰 늘리기", "리뷰-관리"), ("쿠팡", "광고", "네이버-광고"), ("쿠팡", "판매 늘리기", "홍보-방법"),
]
PLAT_CH = {"플레이스": "place", "스마트스토어": "store", "쿠팡": "coupang"}
PLAT_NOTE = {
    "플레이스": ["플레이스는 지도 검색에서 업체를 고르는 손님을 만나는 채널입니다. 업체 정보·사진·리뷰·소식이 순위와 전환을 함께 좌우합니다.",
             "네이버 플레이스는 지역 기반 업종의 첫 화면입니다. 정보가 정확하고 활발한 업체가 손님의 선택을 받습니다."],
    "스마트스토어": ["스마트스토어는 상품명·카테고리·속성·리뷰·가격이 쇼핑 검색 노출에 함께 작용합니다. 상품 정보가 정확할수록 검색에 잘 걸립니다.",
               "쇼핑 검색은 상품 단위로 경쟁합니다. 같은 상품을 파는 판매자와 상품명·썸네일·리뷰·배송 조건을 비교해 보세요."],
    "쿠팡": ["쿠팡은 판매량·리뷰·가격·배송 조건이 노출에 크게 작용하는 채널입니다. 로켓배송 여부에 따라 경쟁 구도가 달라집니다.",
           "쿠팡 검색은 상품 상세 정보와 리뷰, 가격 경쟁력이 함께 평가됩니다. 같은 상품의 경쟁 판매자 조건을 먼저 비교하세요."],
}


# ================================================================== 해석·실수·이유 뱅크 (본문 분량과 페이지별 차이를 만든다)
INTERPRET = {
    "tier": {
        "high": ["월 1만 회가 넘는 큰 수요라 상위권 경쟁이 치열합니다. 메인 키워드 하나에 매달리기보다 연관 키워드로 접점을 넓히는 쪽이 현실적입니다.",
                 "수요가 큰 만큼 이미 꾸준히 관리하는 경쟁 업체가 많습니다. 기본 정보 품질에서 뒤처지면 광고비를 써도 효율이 떨어집니다.",
                 "이 정도 규모는 하루 이틀 변화로 판단하면 안 됩니다. 2주 단위로 순위와 문의를 함께 기록하세요."],
        "mid": ["월 수천 회 규모는 관리만 꾸준하면 자리를 잡을 수 있는 구간입니다. 경쟁 업체 상위 3곳의 사진 수·리뷰 수·소식 주기부터 비교해 보세요.",
                "중간 규모 수요는 기본 정보 정비와 리뷰 관리의 차이가 순위에 잘 드러납니다. 비용을 쓰기 전에 무료로 할 수 있는 것부터 하세요.",
                "이 구간에서는 메인 키워드와 '지역+세부 서비스' 같은 롱테일을 함께 챙기는 것이 효율적입니다."],
        "low": ["검색량이 크지 않은 대신 찾는 사람의 의도가 분명합니다. 기본 정보를 꼼꼼히 채우는 것만으로도 상위에 오르는 경우가 많습니다.",
                "작은 수요는 큰 예산이 필요 없습니다. 정보 정비, 리뷰 답글, 소식 업데이트만 꾸준히 해도 변화가 보이는 구간입니다.",
                "검색량이 적을수록 역 이름·동 이름처럼 다른 표현으로 찾는 손님이 많습니다. 연관 키워드를 함께 확인하세요."],
    },
    "mobile": {
        "very": ["검색의 대부분이 휴대폰에서 일어납니다. 지도 화면의 첫 사진, 전화·길찾기 버튼, 영업시간 표시가 곧 전환율입니다.",
                 "모바일 비중이 매우 높아 PC 화면보다 휴대폰 화면 점검이 우선입니다. 직접 검색해서 우리 업체가 어떻게 보이는지 확인하세요."],
        "high": ["대부분 휴대폰으로 찾지만 PC 검색도 무시할 수준은 아닙니다. 비교 검색하는 손님을 위해 가격·서비스 설명을 충실히 적어 두세요.",
                 "모바일이 중심이지만 PC에서 꼼꼼히 비교하는 손님도 있습니다. 상세 설명과 사진을 함께 챙기세요."],
        "pc": ["PC 비중이 상대적으로 높아 사무실이나 집에서 비교해 보고 결정하는 수요가 섞여 있습니다. 상세 정보와 가격 안내가 중요합니다.",
               "PC 검색이 적지 않다는 건 천천히 비교하는 손님이 많다는 뜻입니다. 후기와 상세 설명이 결정을 돕습니다."],
    },
    "comp": {
        "높음": ["검색광고 경쟁 정도가 '높음'이라 이 키워드에 돈을 쓰는 업체가 많다는 뜻입니다. 유료 노출보다 무료로 할 수 있는 기본기에서 차이를 만드는 게 먼저입니다.",
                "경쟁 정도가 높은 키워드는 클릭 단가도 높아지기 쉽습니다. 롱테일 키워드를 함께 운영하면 비용 대비 효율이 좋아집니다."],
        "중간": ["경쟁 정도가 '중간'이라 꾸준히 관리하면 노출 기회를 만들 수 있는 키워드입니다.",
                "경쟁이 아주 치열하지는 않습니다. 기본 정보와 리뷰 관리만 앞서도 차이가 납니다."],
        "낮음": ["경쟁 정도가 '낮음'이라 지금 관리를 시작하면 비교적 빨리 자리를 잡을 수 있는 키워드입니다.",
                "경쟁이 적은 키워드는 작은 노력으로도 순위 변화가 잘 보입니다. 기록을 남기며 시작해 보세요."],
    },
}

MISTAKES = [
    ("업체명에 키워드 넣기", ["업체명에 지역명이나 업종 키워드를 덧붙이면 실제 상호와 달라져 신뢰가 떨어지고, 정책상 수정 요청을 받을 수도 있습니다.",
                       "상호 뒤에 키워드를 붙이는 방식은 효과보다 위험이 큽니다. 키워드는 소개 문구에 자연스럽게 녹이세요."]),
    ("영업시간 방치", ["영업시간·휴무일이 실제와 다르면 헛걸음한 손님의 불만 리뷰로 바로 이어집니다.",
                   "임시 휴무나 시간 변경을 반영하지 않는 것은 가장 흔하면서도 손해가 큰 실수입니다."]),
    ("리뷰 답글 없음", ["답글이 없는 업체는 손님 입장에서 관리가 안 되는 곳으로 보입니다. 짧아도 모든 리뷰에 답하세요.",
                    "불만 리뷰를 방치하면 같은 내용을 본 다른 손님도 발길을 돌립니다."]),
    ("오래된 사진", ["몇 년 전 사진이 대표 사진이면 실제 방문 경험과 달라 실망 리뷰가 늘어납니다.",
                 "사진은 첫인상입니다. 계절·메뉴·인테리어가 바뀌면 사진도 바꾸세요."]),
    ("순위만 보기", ["순위가 올라도 문의가 늘지 않으면 의미가 없습니다. 전화·예약 수를 함께 기록하세요.",
                 "순위는 수단이고 목표는 문의와 매출입니다. 둘을 같이 봐야 판단이 정확합니다."]),
    ("하루 만에 판단", ["순위는 하루에도 오르내립니다. 하루 이틀 결과로 계획을 바꾸면 무엇이 효과였는지 알 수 없습니다.",
                    "단기 변동에 반응해 매일 설정을 바꾸는 것은 가장 흔한 실수입니다. 2주 추이를 보세요."]),
    ("보장 계약", ["'상위노출 보장' 계약은 조건이 까다롭거나 환불이 어려운 경우가 많습니다. 작업 내역과 순위 기록 공유 여부부터 확인하세요.",
               "보장을 약속하는 곳일수록 계약서의 예외 조항을 꼼꼼히 읽어야 합니다."]),
    ("가짜·대가성 리뷰", ["리뷰를 사거나 별점 조건을 거는 이벤트는 정책 위반이라 리뷰 삭제·노출 제한으로 이어질 수 있습니다.",
                      "대가를 조건으로 한 후기는 표시광고법 문제가 될 수도 있습니다. 실제 손님의 자연스러운 후기만 쌓으세요."]),
    ("기준값 없이 시작", ["시작 전 순위를 기록해 두지 않으면 나중에 효과를 증명할 방법이 없습니다.",
                      "캠페인이나 정보 수정 전에 현재 순위부터 남겨 두세요."]),
    ("키워드 반복", ["소개 문구에 같은 키워드를 여러 번 넣는 것은 효과가 없고 읽는 사람에게 어색하게 보입니다.",
                 "키워드 반복은 검색엔진도 손님도 좋게 보지 않습니다. 한두 번 자연스럽게면 충분합니다."]),
    ("문의 응대 지연", ["노출이 늘어도 전화·톡 응대가 늦으면 문의가 경쟁 업체로 넘어갑니다.",
                    "예약·톡톡 기능을 켜 두고 응대하지 못하면 오히려 나쁜 인상을 남깁니다."]),
    ("경쟁 업체 무시", ["우리 업체만 보면 무엇이 부족한지 알 수 없습니다. 상위 3곳과 사진·리뷰·정보를 나란히 비교하세요.",
                    "같은 상권 경쟁 업체의 변화를 주기적으로 기록하면 순위 변동의 원인이 보입니다."]),
]

WHY = [
    ["직접 운영하면 무엇에 돈을 쓰고 있는지 정확히 알 수 있습니다.", "셀프 운영의 가장 큰 장점은 투명성입니다.",
     "대행사에 맡기면 편하지만 무엇을 했는지 보이지 않는 경우가 많습니다.", "사장님이 직접 이해하고 있어야 대행사를 쓰더라도 제대로 관리할 수 있습니다."],
    ["효과가 없으면 바로 멈추고, 효과가 있으면 그 부분만 늘리면 됩니다.", "작게 시작해서 확인하고 늘리는 방식이 가장 손해가 적습니다.",
     "고정비 계약 없이 필요한 만큼만 쓰는 구조가 작은 가게에 맞습니다.", "결과를 직접 확인하니 다음 행동을 스스로 정할 수 있습니다."],
    ["손님이 실제로 검색하는 숫자를 알고 시작하면 방향을 잘못 잡을 일이 줄어듭니다.", "검색량 데이터는 무료로 확인할 수 있는 가장 정확한 시장 조사입니다.",
     "수요를 숫자로 보면 어디에 힘을 줘야 할지 우선순위가 생깁니다.", "같은 업종이라도 상권마다 수요가 크게 다르다는 점을 기억하세요."],
]


def _interpret(pc, mo, comp, key):
    tot = pc + mo
    mr = mo * 100 / tot if tot else 0
    out = [pick(INTERPRET["tier"][tier(tot)], key, "it")]
    out.append(pick(INTERPRET["mobile"]["very" if mr >= 85 else "high" if mr >= 70 else "pc"], key, "im"))
    if comp in INTERPRET["comp"]:
        out.append(pick(INTERPRET["comp"][comp], key, "ic"))
    return " ".join(out)


def tier(total):
    return "high" if total >= 10000 else "mid" if total >= 2000 else "low"


def _mistakes(key, n=4):
    return [{"q": t, "a": pick(ans, key, t)} for t, ans in sample(MISTAKES, key, n, "mis")]


# ================================================================== 공통 변수
def _vars(subj, plat, prices, **extra):
    ch = PLAT_CH.get(plat, "place")
    p = prices.get(ch) or prices.get("place") or 0
    return {"subj": subj, "plat": plat, "pmin": fmt(p), "ex10": fmt(p * 1000), **extra}


def _faq(items, key, v):
    return [{"q": q.format(**v), "a": pick(ans, key, q).format(**v)} for q, ans in items]


def _common_faq(key, v):
    pool = [("직접 운영해도 효과가 있나요?", ["기본 정보 정비와 리뷰 관리처럼 사장님이 직접 할 때 더 잘 되는 일이 많습니다. 결과는 순위·문의 수를 기록하며 확인하세요.",
                                       "셀프 운영은 비용 구조와 결과가 모두 보인다는 장점이 있습니다. 효과가 없으면 바로 멈출 수 있습니다."]),
            ("효과는 얼마나 지나야 알 수 있나요?", ["최소 1~2주의 일자별 기록이 있어야 판단할 수 있습니다. 시작 전 순위를 기준값으로 남겨 두세요.",
                                           "2주 정도의 추이를 보세요. 순위는 하루 사이에도 오르내립니다."]),
            ("대행사와 셀프 운영은 무엇이 다른가요?", ["가장 큰 차이는 투명성입니다. 셀프 운영은 매체·단가·수량을 직접 고르고 일자별 순위를 직접 확인합니다.",
                                             "대행사를 쓴다면 작업 내역과 순위 기록을 공유받을 수 있는지 꼭 확인하세요."])]
    return _faq(sample(pool, key, 2, "cfaq"), key, v)


def _consumer_line(kw, pc, mo, key):
    tot = pc + mo
    mr = round(mo * 100 / tot) if tot else 0
    bank = ["손님이 '{kw}'{eul} 검색하는 횟수는 한 달 약 {tot}회(모바일 {mr}%)입니다.",
            "'{kw}' 월간 검색량은 PC {pc}회 · 모바일 {mo}회, 합계 {tot}회입니다.",
            "네이버 기준 '{kw}'{eun} 한 달에 {tot}번 검색되고, 그중 {mr}%가 휴대폰에서 일어납니다.",
            "실측 데이터로 보면 '{kw}' 수요는 월 {tot}회, 모바일 비중 {mr}%입니다."]
    return pick(bank, key, "cons").format(kw=kw, pc=fmt(pc), mo=fmt(mo), tot=fmt(tot), mr=mr,
                                          eul=jo(kw, "을를"), eun=jo(kw, "은는"))


def _related_line(related, key, main_tot=None):
    if not related:
        return ""
    top = related[:3]
    names = ", ".join(f"'{r['k']}'({fmt(r['pc'] + r['mo'])}회)" for r in top)
    s = sum(r["pc"] + r["mo"] for r in related)
    bank = ["함께 많이 찾는 표현은 {names}입니다.", "연관 검색어 상위는 {names} 순입니다.",
            "손님들은 {names} 같은 표현으로도 찾습니다.", "비슷한 수요를 다른 말로 찾는 키워드로 {names}가 있습니다."]
    out = pick(bank, key, "rel").format(names=names)
    if main_tot:
        ratio = s / main_tot if main_tot else 0
        out += " " + (f"상위 연관 키워드 {len(related)}개를 합치면 월 {fmt(s)}회로 메인 키워드의 {ratio:.1f}배라, 메인 하나만 보면 놓치는 수요가 큽니다."
                      if ratio >= 1.2 else f"상위 연관 키워드 {len(related)}개를 합치면 월 {fmt(s)}회로, 메인 키워드가 수요의 중심입니다.")
    return out


# ================================================================== 데이터 인덱스
def _place_rows():
    rows = sorted(_load()["place"]["rows"], key=lambda r: -(r["pc"] + r["mo"]))
    return rows[:MAX_REGIONBIZ]


def _biz_rows():
    return _load()["biz"]["rows"]


def _store_rows():
    return [r for r in _load()["store"]["rows"] if r["pc"] + r["mo"] > 0]


@lru_cache(maxsize=1)
def registry():
    """slug → (kind, key). 주소 충돌이 나면 먼저 등록된 쪽이 이긴다."""
    reg = {}

    def add(slug, kind, key):
        reg.setdefault(slug, (kind, key))

    for b in _biz_rows():
        add(f"{b['biz']}-마케팅", "bizhub", b["biz"])
        for a in ANGLES:
            add(f"{b['biz']}-{a}", "bizangle", (b["biz"], a))
    for r in _place_rows():
        add(f"{r['region']}-{r['biz']}-마케팅", "regionbiz", (r["region"], r["biz"]))
    for rg in sorted({r["region"] for r in _place_rows()}):
        add(f"{rg}-마케팅", "regionhub", rg)
    for plat, ang, base in TOPICS:
        add(f"{plat}-{ang.replace(' ', '-')}", "topic", (plat, ang, base))
    for s in _store_rows():
        add(f"스마트스토어-{s['kw']}-판매", "storecat", s["kw"])
    return reg


def all_paths():
    return [(f"/learn/{slug}/", kind, slug) for slug, (kind, _) in registry().items()]


@lru_cache(maxsize=1)
def salts():
    """페이지별 문장 재배치 값 — 유사도 검사에서 걸린 페이지만 seo_check.py --fix 가 올린다."""
    p = DATA / "salt.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def build(slug, prices):
    hit = registry().get(slug)
    if not hit:
        return None
    kind, key = hit
    salt = salts().get(slug)
    page = BUILDERS[kind](key, f"{slug}#{salt}" if salt else slug, prices)
    page.update(kind=kind, slug=slug, path=f"/learn/{slug}/")
    page["desc"] = fit_desc(page["desc"])
    return page


# ================================================================== builders
def _angle_sections(a, key, v, subj):
    A = ANGLES[a]
    steps = [s.format(**v) for s in sample(A["steps"], key, 6, "steps")]
    return [
        {"h": "순서대로 해 보세요", "list": steps},
        {"h": "왜 직접 해 볼 만한가", "p": [para(WHY, key, "why", v)]},
        {"h": "자주 하는 실수", "sub": _mistakes(key)},
        {"h": "비용은 이렇게 계산합니다", "p": [para(COST, key, "cost", v)]},
        {"h": "결과는 이렇게 확인합니다", "p": [para(MEASURE, key, "meas", v)]},
        {"h": "주의할 점", "p": [para(CAUTION, key, "caut", v)]},
    ]


def b_bizhub(biz, slug, prices):
    b = next(x for x in _biz_rows() if x["biz"] == biz)
    v = _vars(biz, "플레이스", prices)
    regions = sorted((r for r in _place_rows() if r["biz"] == biz), key=lambda r: -(r["pc"] + r["mo"]))
    sv = seller_vol(f"{biz}마케팅")
    lead = (f"'{biz} 마케팅'{jo('마케팅', '은는')} 사장님들이 한 달 약 {fmt(sv)}회 검색하는 주제입니다. " if sv else "") + \
        _consumer_line(biz, b["pc"], b["mo"], slug) + " " + \
        pick(["이 페이지에서 지역별 손님 수요, 업종 광고 규정, 셀프 운영 순서를 한 번에 볼 수 있습니다.",
              "아래에 지역별 손님 검색량과 직접 해 볼 수 있는 방법을 정리했습니다.",
              "대행사에 맡기기 전에 우리 업종의 수요와 운영 방법부터 확인해 보세요."], slug, "lead2")
    secs = []
    if regions:
        secs.append({"h": f"지역별 '{biz}' 손님 검색량", "itemlist": [(f"{r['region']} {biz} 마케팅", f"/learn/{r['region']}-{biz}-마케팅/", fmt(r["pc"] + r["mo"]) + "회") for r in regions]})
    secs.append({"h": "손님이 함께 찾는 키워드", "related": b["related"], "p": [_related_line(b["related"], slug, b["pc"] + b["mo"]), _interpret(b["pc"], b["mo"], b["comp"], slug)]})
    secs.append({"h": f"{biz} 업종 광고·홍보 유의사항", "p": GROUP_NOTE[b["group"]][:2]})
    secs.append({"h": "주제별 가이드", "links": [(f"{biz} {A['label']}", f"/learn/{biz}-{a}/") for a, A in ANGLES.items()]})
    secs += _angle_sections("홍보-방법", slug, v, biz)
    return {"kw": f"{biz} 마케팅", "channel": "place",
            "title": f"{biz} 마케팅 방법 · 손님 검색량과 셀프 운영 가이드",
            "desc": f"{biz} 마케팅을 직접 하려는 사장님을 위한 정리. 전국 손님 검색량 월 {fmt(b['pc'] + b['mo'])}회, 지역별 수요, 업종 광고 규정, 비용 계산까지.",
            "h1": f"{biz} 마케팅, 직접 하는 방법", "lead": lead,
            "stats": [("손님 검색량(전국)", fmt(b["pc"] + b["mo"]) + "회"), ("'마케팅' 검색", (fmt(sv) + "회") if sv else "-"),
                      ("지역 페이지", f"{len(regions)}곳"), ("경쟁 정도", b["comp"] or "-")],
            "sections": secs, "faq": _common_faq(slug, v),
            "links": [("다른 업종", [(f"{x['biz']} 마케팅", f"/learn/{x['biz']}-마케팅/") for x in _biz_rows() if x["group"] == b["group"] and x["biz"] != biz])],
            "crumbs": [("셀프 마케팅 가이드", "/learn/"), (f"{biz} 마케팅", None)]}


def b_bizangle(key, slug, prices):
    biz, a = key
    A = ANGLES[a]
    b = next(x for x in _biz_rows() if x["biz"] == biz)
    v = _vars(biz, "플레이스", prices)
    lead = para(A["intro"], slug, "intro", v) + " " + _consumer_line(biz, b["pc"], b["mo"], slug)
    top_regions = sorted((r for r in _place_rows() if r["biz"] == biz), key=lambda r: -(r["pc"] + r["mo"]))[:5]
    data_p = [_related_line(b["related"], slug, b["pc"] + b["mo"])]
    if top_regions:
        data_p.append("지역별로는 " + ", ".join(f"{r['region']}({fmt(r['pc'] + r['mo'])}회)" for r in top_regions) +
                      pick([" 순으로 손님 검색이 많습니다.", " 순으로 수요가 큽니다.", " 순입니다 — 우리 상권 숫자는 아래 지역 페이지에서 확인하세요."], slug, "rg"))
    data_p.append(_interpret(b["pc"], b["mo"], b["comp"], slug))
    secs = [{"h": f"{biz} 손님은 이렇게 검색합니다", "p": data_p, "related": b["related"][:8]}]
    secs += _angle_sections(a, slug, v, biz)
    secs.insert(2, {"h": f"{biz} 업종이라면 꼭 확인하세요", "p": [pick(GROUP_NOTE[b["group"]], slug, "grp")]})
    sv = seller_vol(f"{biz}{A['label'].replace(' ', '')}")
    return {"kw": f"{biz} {A['label']}", "channel": "place",
            "title": f"{biz} {A['label']} — 직접 하는 순서와 비용",
            "desc": f"{biz} {A['label']}{jo(A['label'], '을를')} 대행사 없이 하는 방법. 손님 검색량 월 {fmt(b['pc'] + b['mo'])}회 기준으로 순서, 비용 계산, 결과 확인법과 업종 유의사항을 정리했습니다.",
            "h1": f"{biz} {A['label']}, 직접 하는 방법", "lead": lead,
            "stats": [("손님 검색량", fmt(b["pc"] + b["mo"]) + "회"), ("모바일 비중", f"{round(b['mo'] * 100 / max(1, b['pc'] + b['mo']))}%"),
                      ("판매자 검색", (fmt(sv) + "회") if sv else "-"), ("경쟁 정도", b["comp"] or "-")],
            "sections": secs, "faq": _faq(A["faq"], slug, v) + _common_faq(slug, v)[:1],
            "links": [(f"{biz} 다른 주제", [(f"{biz} {X['label']}", f"/learn/{biz}-{x}/") for x, X in ANGLES.items() if x != a] + [(f"{biz} 마케팅 허브", f"/learn/{biz}-마케팅/")]),
                      ("지역별", [(f"{r['region']} {biz} 마케팅", f"/learn/{r['region']}-{biz}-마케팅/") for r in top_regions])],
            "crumbs": [("셀프 마케팅 가이드", "/learn/"), (f"{biz} 마케팅", f"/learn/{biz}-마케팅/"), (A["label"], None)]}


def b_regionbiz(key, slug, prices):
    region, biz = key
    r = next(x for x in _place_rows() if x["region"] == region and x["biz"] == biz)
    b = next((x for x in _biz_rows() if x["biz"] == biz), None)
    v = _vars(biz, "플레이스", prices, region=region)
    kw = f"{region} {biz}"
    tot = r["pc"] + r["mo"]
    peers = sorted((x for x in _place_rows() if x["biz"] == biz), key=lambda x: -(x["pc"] + x["mo"]))
    rank = next(i for i, x in enumerate(peers, 1) if x["region"] == region)
    local = sorted((x for x in _place_rows() if x["region"] == region), key=lambda x: -(x["pc"] + x["mo"]))
    lrank = next(i for i, x in enumerate(local, 1) if x["biz"] == biz)
    lead = pick([f"{region}에서 {biz}{jo(biz, '을를')} 운영하는 사장님을 위한 페이지입니다. ",
                 f"{region} 상권 {biz} 마케팅을 직접 해 보려는 분께 필요한 숫자부터 정리했습니다. ",
                 f"'{region} {biz} 마케팅'을 대행사에 맡기기 전에 상권 수요부터 확인하세요. "], slug, "l1") + \
        _consumer_line(kw, r["pc"], r["mo"], slug)
    # 업종명만 있는 전국 키워드('치과')는 지역 페이지의 연관 키워드가 아니다 — 빼고, 배수 비교도 하지 않는다
    rel = [x for x in r["related"] if x["k"] != biz]
    rank_p = (f"수집한 {len(peers)}개 지역 중 '{biz}' 손님 검색이 {rank}번째로 많은 상권이고, "
              f"{region} 안에서는 {len(local)}개 업종 중 {biz}{jo(biz, '이가')} {lrank}위입니다.")
    secs = [
        {"h": f"{region} {biz} 손님 수요", "p": [rank_p, _related_line(rel, slug), _interpret(r["pc"], r["mo"], r["comp"], slug)], "related": rel},
        {"h": "이 상권에서 할 일", "list": [s.format(**v) for s in sample(ANGLES["플레이스-상위노출"]["steps"] + ANGLES["리뷰-관리"]["steps"], slug, 6, "st")]},
    ]
    if b:
        secs.append({"h": f"{biz} 업종 유의사항", "p": [pick(GROUP_NOTE[b["group"]], slug, "grp")]})
    secs += [{"h": "왜 직접 해 볼 만한가", "p": [para(WHY, slug, "why", v)]},
             {"h": "자주 하는 실수", "sub": _mistakes(slug)},
             {"h": "비용은 이렇게 계산합니다", "p": [para(COST, slug, "cost", v)]},
             {"h": "결과는 이렇게 확인합니다", "p": [para(MEASURE, slug, "meas", v)]},
             {"h": "주의할 점", "p": [para(CAUTION, slug, "caut", v)]}]
    near = [x for x in peers if x["region"] != region and x["sido"] == r["sido"]][:6] or [x for x in peers if x["region"] != region][:6]
    return {"kw": kw, "channel": "place",
            "title": f"{region} {biz} 마케팅 · 상권 손님 월 {fmt(tot)}회 검색 분석",
            "desc": f"{region} {biz} 마케팅을 직접 하려는 사장님을 위한 상권 데이터. '{kw}' 월간 검색량 {fmt(tot)}회, 연관 키워드, 할 일 순서와 비용 계산.",
            "h1": f"{region} {biz} 마케팅", "lead": lead,
            "stats": [("손님 월 검색", fmt(tot) + "회"), ("모바일 비중", f"{round(r['mo'] * 100 / max(1, tot))}%"),
                      (f"{biz} 지역 순위", f"{rank}/{len(peers)}"), ("경쟁 정도", r["comp"] or "-")],
            "sections": secs, "faq": _common_faq(slug, v),
            "links": [(f"{biz} 마케팅 · 다른 지역", [(f"{x['region']} {biz} 마케팅", f"/learn/{x['region']}-{biz}-마케팅/") for x in near]),
                      (f"{region} · 다른 업종", [(f"{region} {x['biz']} 마케팅", f"/learn/{region}-{x['biz']}-마케팅/") for x in local if x["biz"] != biz][:8]),
                      ("주제별 가이드", [(f"{biz} {A['label']}", f"/learn/{biz}-{a}/") for a, A in list(ANGLES.items())[:4]])],
            "crumbs": [("셀프 마케팅 가이드", "/learn/"), (f"{region} 마케팅", f"/learn/{region}-마케팅/"), (f"{biz}", None)],
            "region": region, "sido": r["sido"]}


def b_regionhub(region, slug, prices):
    rows = sorted((x for x in _place_rows() if x["region"] == region), key=lambda x: -(x["pc"] + x["mo"]))
    total = sum(x["pc"] + x["mo"] for x in rows)
    v = _vars("우리 업종", "플레이스", prices)
    return {"kw": f"{region} 마케팅", "channel": "place",
            "title": f"{region} 마케팅 · 업종별 손님 검색량 {len(rows)}개 업종",
            "desc": f"{region} 상권에서 장사하는 사장님을 위한 업종별 손님 검색량. 가장 많이 찾는 업종은 {rows[0]['biz']}(월 {fmt(rows[0]['pc'] + rows[0]['mo'])}회), 업종별 셀프 마케팅 가이드로 이어집니다.",
            "h1": f"{region} 마케팅 — 업종별 손님 수요", "lead": f"{region}에서 업종 이름과 함께 검색되는 횟수를 합치면 한 달 약 {fmt(total)}회입니다. 우리 업종의 숫자를 확인하고 바로 운영 가이드로 넘어가세요.",
            "stats": [("업종 수", f"{len(rows)}개"), ("합계 월 검색", fmt(total) + "회"), ("1위 업종", rows[0]["biz"]), ("지역", rows[0]["sido"])],
            "sections": [{"h": f"{region} 상권 한눈에", "p": [_region_data(region, rows, slug)] + [_consumer_line(f"{region} {x['biz']}", x["pc"], x["mo"], slug + x["biz"]) for x in rows[:3]]},
                         {"h": f"{region} 업종별 손님 검색량", "itemlist": [(f"{region} {x['biz']} 마케팅", f"/learn/{region}-{x['biz']}-마케팅/", fmt(x["pc"] + x["mo"]) + "회") for x in rows]},
                         {"h": "이 숫자를 어떻게 쓰나요", "p": [para(MEASURE, slug, "m", v), para(WHY, slug, "w", v)]},
                         {"h": "자주 하는 실수", "sub": _mistakes(slug, 3)},
                         {"h": "주의할 점", "p": [para(CAUTION, slug, "c", v)]}],
            "faq": [], "links": [("같은 지역권", [(f"{x} 마케팅", f"/learn/{x}-마케팅/") for x in sorted({y['region'] for y in _place_rows() if y['sido'] == rows[0]['sido'] and y['region'] != region})][:12])],
            "crumbs": [("셀프 마케팅 가이드", "/learn/"), (f"{region} 마케팅", None)], "region": region, "sido": rows[0]["sido"]}


def _region_data(region, rows, key):
    """지역 허브의 데이터 문단 — 상위 업종, 업종군 비중, 같은 시도 안에서의 위치."""
    total = sum(x["pc"] + x["mo"] for x in rows)
    top = ", ".join(f"{x['biz']}({fmt(x['pc'] + x['mo'])}회)" for x in rows[:3])
    groups = {}
    for x in rows:
        groups[x["group"]] = groups.get(x["group"], 0) + x["pc"] + x["mo"]
    g, gv = max(groups.items(), key=lambda kv: kv[1])
    sido = rows[0]["sido"]
    sido_tot = {}
    for x in _place_rows():
        if x["sido"] == sido:
            sido_tot[x["region"]] = sido_tot.get(x["region"], 0) + x["pc"] + x["mo"]
    order = sorted(sido_tot, key=lambda k: -sido_tot[k])
    pos = order.index(region) + 1
    lines = [f"손님 검색이 가장 많은 업종은 {top} 순입니다.",
             f"업종군으로 묶으면 '{g}'{jo(g, '이가')} 전체의 {round(gv * 100 / total)}%를 차지합니다.",
             f"{sido} 지역 {len(order)}곳 중 업종 검색량 합계가 {pos}번째로 많은 상권입니다."]
    return " ".join(sample(lines, key, 3, "rd"))


def b_topic(key, slug, prices):
    plat, ang, base = key
    A = ANGLES[base]
    subj = {"플레이스": "업체", "스마트스토어": "상품", "쿠팡": "상품"}[plat]
    v = _vars(subj, plat, prices)
    label = f"{plat} {ang}"
    sv = seller_vol(label)
    lead = (f"'{label}'{jo(label, '은는')} 판매자·사장님들이 한 달 약 {fmt(sv)}회 검색하는 주제입니다. " if sv else "") + \
        pick(PLAT_NOTE[plat], slug, "pn") + " " + para(A["intro"][1:], slug, "intro", v)
    secs = [{"h": f"{plat}에서 {ang}{jo(ang, '이가')} 결정되는 방식", "p": [pick(PLAT_NOTE[plat], slug, "pn2"), para(A["intro"][:1], slug, "i0", v)]}]
    secs += _angle_sections(base, slug, v, subj)
    if plat != "플레이스":   # 상품 판매 채널에는 매장용 실수(업체명·영업시간·사진)를 빼고 다시 고른다
        for sct in secs:
            if sct.get("sub"):
                sct["sub"] = [m for m in _mistakes(slug, 7) if m["q"] not in ("업체명에 키워드 넣기", "영업시간 방치", "오래된 사진")][:4]
    if plat == "스마트스토어":
        secs.insert(2, {"h": "카테고리별 키워드 데이터", "links": [(f"{s['kw']} 판매", f"/learn/스마트스토어-{s['kw']}-판매/") for s in _store_rows()][:24]})
    others = [(f"{p} {a}", f"/learn/{p}-{a.replace(' ', '-')}/") for p, a, _ in TOPICS if (p, a) != (plat, ang)]
    return {"kw": label, "channel": PLAT_CH[plat],
            "title": f"{label} 방법 — 보장 없이 직접 하는 순서",
            "desc": f"{label}, 대행사 없이 직접 하는 방법을 정리했습니다. 순서별 체크리스트, 비용 계산, 결과 확인법, 그리고 '보장' 업체를 경계해야 하는 이유까지.",
            "h1": f"{label}, 직접 하는 방법", "lead": lead,
            "stats": [("판매자 검색", (fmt(sv) + "회") if sv else "-"), ("채널", plat), ("최저 단가", v["pmin"] + "원"), ("비용 예시", v["ex10"] + "원")],
            "sections": secs, "faq": _faq(A["faq"], slug, v) + _common_faq(slug, v)[:1],
            "links": [("다른 주제", sample(others, slug, 10, "oth"))],
            "crumbs": [("셀프 마케팅 가이드", "/learn/"), (label, None)]}


def b_storecat(kw, slug, prices):
    s = next(x for x in _store_rows() if x["kw"] == kw)
    v = _vars("상품", "스마트스토어", prices)
    tot = s["pc"] + s["mo"]
    lead = pick([f"스마트스토어에서 {kw}{jo(kw, '을를')} 파는 판매자를 위한 페이지입니다. ",
                 f"'{kw}' 판매를 직접 늘려 보려는 스토어 사장님께 필요한 숫자부터 정리했습니다. ",
                 f"{kw} 카테고리에서 판매를 늘리려면 먼저 구매자의 검색 수요를 보세요. "], slug, "l1") + \
        _consumer_line(kw, s["pc"], s["mo"], slug)
    sibs = [x for x in _store_rows() if x["group"] == s["group"] and x["kw"] != kw]
    secs = [{"h": f"구매자는 '{kw}'{jo(kw, '을를')} 이렇게 검색합니다", "p": [_related_line(s["related"], slug, tot), _interpret(s["pc"], s["mo"], s["comp"], slug)], "related": s["related"]},
            {"h": "상품 정보 셀프 점검", "list": sample(["상품명은 핵심 키워드를 앞쪽에, 브랜드·모델·속성 순으로 — 같은 단어 반복 금지",
                                                   "카테고리를 상위 상품들과 같은 위치로 맞추기", "속성(색상·소재·용량 등)과 태그를 빠짐없이",
                                                   "썸네일 첫 장은 흰 배경 + 상품이 꽉 차게", "상세페이지 첫 화면에 핵심 장점 3가지 요약",
                                                   "리뷰에 답글 달고 불만 사항은 상세페이지에 반영", "배송 기간·교환 조건을 명확히",
                                                   "가격 비교 탭에서 경쟁 가격 주 1회 확인", "키워드별 순위를 매일 같은 시각에 기록",
                                                   "유입 대비 구매 전환율을 주 단위로 확인"], slug, 6, "chk")},
            {"h": "왜 직접 해 볼 만한가", "p": [para(WHY, slug, "why", v)]},
            {"h": "자주 하는 실수", "sub": [m for m in _mistakes(slug, 6) if m["q"] not in ("업체명에 키워드 넣기", "영업시간 방치", "오래된 사진")][:4]},
            {"h": "비용은 이렇게 계산합니다", "p": [para(COST, slug, "cost", v)]},
            {"h": "결과는 이렇게 확인합니다", "p": [para(MEASURE, slug, "meas", v)]},
            {"h": "주의할 점", "p": [para(CAUTION, slug, "caut", v)]}]
    return {"kw": f"{kw} 스마트스토어", "channel": "store",
            "title": f"스마트스토어 {kw} 판매 · 월 {fmt(tot)}회 검색 키워드 분석",
            "desc": f"스마트스토어 {kw} 판매자를 위한 키워드 데이터. 구매자 월간 검색량 {fmt(tot)}회, 세부 키워드, 상품 정보 점검표와 쇼핑 유입 비용 계산.",
            "h1": f"스마트스토어 {kw} 판매 늘리기", "lead": lead,
            "stats": [("구매자 월 검색", fmt(tot) + "회"), ("모바일 비중", f"{round(s['mo'] * 100 / max(1, tot))}%"), ("경쟁 정도", s["comp"] or "-"), ("분류", s["group"])],
            "sections": secs, "faq": _faq(ANGLES["플레이스-상위노출"]["faq"][:1], slug, v) + _common_faq(slug, v)[:2],
            "links": [("같은 분류", [(f"{x['kw']} 판매", f"/learn/스마트스토어-{x['kw']}-판매/") for x in sibs]),
                      ("스마트스토어 가이드", [(f"스마트스토어 {a}", f"/learn/스마트스토어-{a.replace(' ', '-')}/") for p, a, _ in TOPICS if p == "스마트스토어"])],
            "crumbs": [("셀프 마케팅 가이드", "/learn/"), ("스마트스토어 마케팅", "/learn/스마트스토어-마케팅/"), (f"{kw} 판매", None)]}


BUILDERS = {"bizhub": b_bizhub, "bizangle": b_bizangle, "regionbiz": b_regionbiz, "regionhub": b_regionhub,
            "topic": b_topic, "storecat": b_storecat}


def hub():
    reg = registry()
    by = {}
    for slug, (kind, key) in reg.items():
        by.setdefault(kind, []).append(slug)
    regions = {}
    for r in _place_rows():
        regions.setdefault(r["sido"], set()).add(r["region"])
    return {"count": len(reg), "biz": [b["biz"] for b in _biz_rows()], "regions": {k: sorted(v) for k, v in regions.items()},
            "topics": [(f"{p} {a}", f"/learn/{p}-{a.replace(' ', '-')}/") for p, a, _ in TOPICS],
            "store": [s["kw"] for s in _store_rows()]}
