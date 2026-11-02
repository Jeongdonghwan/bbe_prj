"""전국 시군구 × 업종 × 의도 페이지 — /learn/<지역>-<업종>-<의도>/ (2026-11-02 확장, docs/SEO_PLAN.md).

데이터: data/seo/sg.json (scripts/seo_keywords_sg.py — 네이버 검색광고 실측). 페이지 주제는 판매자 검색어
("강남 치과 마케팅 / 플레이스 상위노출 / 홍보"), 손님 검색량("강남치과")은 근거 데이터로만 쓴다.
같은 지역·업종의 세 의도 페이지가 서로 닮지 않도록 의도마다 데이터를 다른 각도로 쓴다
(마케팅 = 전국·시도 안 위치, 플레이스 = 지도 검색·연관 키워드, 홍보 = 지역 안 업종 순위·손님 경로).

오픈 일정: data/seo/drip.json — 손님 검색량 큰 순으로 첫날 FIRST 개, 이후 매일 나눠 DAYS 일에 전부.
열리지 않은 페이지는 404 + 사이트맵 제외. 확장 전부터 있던 주소(지역×업종 520)는 처음부터 열려 있다.
"""
import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from . import seo_pages as sp

DATA = Path(__file__).resolve().parent.parent.parent / "data" / "seo"
INTENTS = ["마케팅", "플레이스-상위노출", "홍보"]
LABEL = {"마케팅": "마케팅", "플레이스-상위노출": "플레이스 상위노출", "홍보": "홍보"}


# ================================================================== data
@lru_cache(maxsize=1)
def _rows():
    p = DATA / "sg.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"meta": {}, "rows": []}


@lru_cache(maxsize=1)
def _idx():
    """(q, biz) → pair · biz → 전국 순 · (sido, biz) → 시도 순 · q → 지역 안 업종 순 · sido → 지역 목록."""
    pairs = {}
    for r in _rows()["rows"]:
        pairs.setdefault((r["q"], r["biz"]), r)
    by_biz, by_sido_biz, by_q, by_sido = {}, {}, {}, {}
    for (q, b), r in pairs.items():
        by_biz.setdefault(b, []).append(r)
        by_sido_biz.setdefault((r["sido"], b), []).append(r)
        by_q.setdefault(q, []).append(r)
        by_sido.setdefault(r["sido"], set()).add(q)
    for d in (by_biz, by_sido_biz, by_q):
        for k in d:
            d[k].sort(key=lambda x: -x["demand"])
    return {"pairs": pairs, "biz": by_biz, "sido_biz": by_sido_biz, "q": by_q,
            "sido": {k: sorted(v, key=lambda q: -sum(x["demand"] for x in by_q[q])) for k, v in by_sido.items()}}


def meta():
    return _rows()["meta"]


# ================================================================== drip (나눠 오픈)
@lru_cache(maxsize=1)
def _drip():
    p = DATA / "drip.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


@lru_cache(maxsize=1)
def _order():
    """오픈 순서 — 손님 검색량 큰 지역·업종부터, 같은 쌍은 마케팅 → 플레이스 → 홍보."""
    pairs = sorted(_idx()["pairs"].values(), key=lambda r: (-r["demand"], r["q"], r["biz"]))
    return [f"{r['q']}-{r['biz']}-{i}" for r in pairs for i in INTENTS]


def open_count(today=None):
    d = _drip()
    if not d.get("start"):
        return len(_order())                      # 일정이 없으면 전부 연다
    day = ((today or date.today()) - date.fromisoformat(d["start"])).days
    if day < 0:
        return 0
    total, first, days = len(_order()), int(d.get("first", 0)), int(d.get("days", 30))
    if day >= days - 1:
        return total
    return min(total, first + (total - first) * day // max(1, days - 1))


@lru_cache(maxsize=4)
def _open_set(day_key):
    return set(_order()[:open_count(date.fromisoformat(day_key))]) | set(_drip().get("always", []))


def is_open(slug):
    return slug in _open_set(date.today().isoformat())


# ================================================================== registry
def register(add):
    """seo_pages.registry() 가 부른다 — 기존 페이지보다 먼저 등록해 같은 주소면 새 내용이 이긴다."""
    ix = _idx()
    for (q, b) in ix["pairs"]:
        for i in INTENTS:
            add(f"{q}-{b}-{i}", "rbi", (q, b, i))
    for q in ix["q"]:
        add(f"{q}-마케팅", "sghub", q)
    for s in ix["sido"]:
        add(f"{s}-지역-마케팅", "sidohub", s)


def visible(kind, slug):
    return kind != "rbi" or is_open(slug)


# ================================================================== 문장 뱅크 (의도별)
LEAD = {
    "마케팅": ["{sido} {region}에서 {biz}{eul} 운영하는 사장님을 위해 상권 수요부터 정리했습니다. ",
             "'{q} {biz} 마케팅'을 대행사에 맡기기 전에 이 지역 손님이 얼마나 찾는지 먼저 확인하세요. ",
             "{q} {biz} 마케팅을 직접 해 보려는 분께 필요한 숫자와 순서를 한 페이지에 담았습니다. ",
             "{region} {biz} 사장님이 셀프로 마케팅을 시작할 때 기준이 되는 데이터입니다. "],
    "플레이스-상위노출": ["'{q} {biz}'를 지도에서 찾는 손님에게 먼저 보이려면 무엇부터 해야 하는지 정리했습니다. ",
                    "{q} {biz} 플레이스 순위를 직접 관리하려는 사장님을 위한 페이지입니다. ",
                    "{region}에서 {biz} 플레이스 상위노출을 노린다면 이 지역 검색 수요부터 보세요. ",
                    "네이버 지도에서 '{q} {biz}'를 검색했을 때 우리 업체가 몇 번째에 나오는지가 출발점입니다. "],
    "홍보": ["{q} {biz} 홍보를 어디서부터 해야 할지 막막한 사장님을 위해 손님이 찾아오는 경로부터 정리했습니다. ",
            "{region} {biz} 홍보는 큰 예산보다 손님이 실제로 보는 곳을 먼저 채우는 게 순서입니다. ",
            "'{q} {biz} 홍보'를 검색했다면 이 지역 손님 수요와 채널별 할 일을 함께 확인하세요. ",
            "{sido} {region} 상권에서 {biz}{eul} 알리는 방법을 비용 순서대로 정리했습니다. "],
}

PLACE_FACTORS = [
    ("정보 정확도", ["영업시간·전화번호·주소·가격이 실제와 맞는지가 기본입니다. 틀린 정보는 헛걸음 리뷰로 돌아옵니다.",
                 "업체 정보가 빠짐없이 채워져 있을수록 검색 결과에서 신뢰를 얻습니다. 가격표와 휴무일부터 확인하세요."]),
    ("사진 수와 최신성", ["대표 사진은 손님이 업체를 고르는 첫 기준입니다. 경쟁 업체보다 사진이 적거나 오래됐다면 교체부터 하세요.",
                     "계절·메뉴·인테리어가 바뀌었는데 사진이 그대로면 클릭이 줄어듭니다. 실제 모습을 최근 사진으로 보여주세요."]),
    ("리뷰와 답글", ["최근 리뷰가 꾸준히 달리고 사장님 답글이 있는 업체가 활발한 곳으로 보입니다.",
                "리뷰 수보다 최근성과 답글 여부가 더 많이 보입니다. 불만 리뷰에도 차분히 답하세요."]),
    ("손님 행동", ["저장·길찾기·전화·예약 같은 실제 손님 행동이 쌓이는 업체가 유리합니다. 버튼이 실제로 응대되는지 점검하세요.",
               "검색 후 클릭하고 머무는 손님이 많을수록 좋은 신호가 됩니다. 첫 화면 정보가 충실해야 이탈이 줄어듭니다."]),
    ("카테고리·키워드", ["카테고리를 실제 업종과 정확히 맞추고, 소개글에 주요 서비스와 지역을 자연스럽게 한두 번 적으세요.",
                    "업체명에 키워드를 덧붙이는 방식은 위험합니다. 키워드는 소개글과 메뉴 설명에 자연스럽게 녹이세요."]),
    ("소식·업데이트", ["소식 탭을 2주에 한 번이라도 갱신하면 관리되는 업체라는 신호가 됩니다.",
                   "이벤트·신메뉴·휴무 안내를 소식으로 올리면 단골에게 알림이 가고 활동성도 보여줍니다."]),
]

CHANNELS = [
    ("네이버 플레이스", ["지역 손님 대부분이 지도에서 업체를 비교합니다. 비용이 들지 않는 첫 번째 채널입니다.",
                     "검색 → 지도 → 리뷰 확인 → 전화로 이어지는 흐름의 시작점입니다. 정보 정비가 가장 먼저입니다."]),
    ("리뷰", ["영수증 리뷰 안내만 꾸준히 해도 리뷰가 늘어납니다. 대가를 조건으로 한 리뷰는 피하세요.",
             "손님은 사진 다음으로 리뷰를 봅니다. 모든 리뷰에 답글을 다는 것만으로 신뢰가 쌓입니다."]),
    ("블로그 후기", ["실제 방문 경험이 담긴 후기 글은 오래 검색에 남습니다. 협찬이라면 반드시 표시하세요.",
                 "체험단을 쓴다면 협찬 표시와 실제 방문 여부를 확인하세요. 표시 없는 후기는 문제가 될 수 있습니다."]),
    ("인스타그램", ["사진이 강점인 업종에 맞습니다. 지역 태그와 매장 위치를 꼭 연결해 두세요.",
               "꾸준한 게시가 중요합니다. 매장 분위기·신메뉴·작업 사례를 주 1~2회 올리는 정도면 충분합니다."]),
    ("지역 커뮤니티", ["동네 커뮤니티·지역 앱 광고는 반경이 좁은 업종에 효율적입니다. 작은 예산으로 시험해 보세요.",
                   "지역 기반 앱은 근처 주민에게 직접 닿습니다. 오픈·이벤트 시기에 짧게 써 보세요."]),
    ("유입 캠페인", ["기본 정보가 갖춰진 뒤 노출을 앞당기는 보조 수단입니다. 최소 수량·최소 기간으로 시작하세요.",
                 "순위 추적과 함께 쓰면 효과를 날짜별로 확인할 수 있습니다. 정보 정비 없이 쓰면 오래가지 않습니다."]),
]

DATA_MKT = [
    "'{kw}'{eun} 한 달에 약 {tot}회 검색됩니다. 전국 {nat_n}개 시군구 중 {biz} 손님 검색이 {nat}번째로 많고, {sido} 안에서는 {s_n}곳 중 {srank}위입니다.",
    "{biz} 손님 수요로 보면 {region}{reg_eun} 전국 {nat_n}곳 가운데 {nat}위, {sido}에서는 {srank}위인 상권입니다. 월간 검색량은 '{kw}' 기준 {tot}회입니다.",
    "네이버 실측 기준 '{kw}' 월 {tot}회 — {sido} {s_n}개 지역 중 {srank}번째, 전국으로 넓히면 {nat}번째 규모입니다.",
]
DATA_PLACE = [
    "지도에서 '{kw}'{eul} 찾는 검색은 한 달 {tot}회이고, 그중 {mr}%가 휴대폰에서 일어납니다. 휴대폰 지도 첫 화면이 곧 이 상권의 승부처입니다.",
    "'{kw}' 월간 검색 {tot}회 가운데 모바일이 {mo}회({mr}%)입니다. 손님 대부분이 이동 중에 지도로 비교하고 바로 전화하거나 길찾기를 누릅니다.",
    "모바일 {mo}회 · PC {pc}회, 합계 월 {tot}회가 '{kw}'의 수요입니다. 모바일 비중이 {mr}%라 지도 화면 정보가 전환을 좌우합니다.",
]
DATA_PROMO = [
    "{region}에서 손님이 업종 이름으로 검색하는 {l_n}개 업종 중 {biz}{eun} {lrank}번째로 많이 찾습니다. 이 지역에서 가장 많이 찾는 업종은 {ltop}입니다.",
    "{region} 업종별 손님 검색을 비교하면 {ltop} 순이고, {biz}{eun} {l_n}개 업종 가운데 {lrank}위입니다. '{kw}'만 월 {tot}회 검색됩니다.",
    "같은 {region} 안에서 {biz}{eun} 손님 검색 {lrank}위 업종입니다(총 {l_n}개). 상위 업종은 {ltop}이며 '{kw}' 검색은 한 달 {tot}회입니다.",
]

FAQ_INTENT = {
    "마케팅": [("{q} {biz} 마케팅, 대행사에 맡겨야 하나요?",
               ["먼저 직접 해 보는 것을 권합니다. 플레이스 정보 정비와 리뷰 관리처럼 사장님이 할 때 더 잘 되는 일이 많고, 숫자를 알고 나면 대행사를 쓰더라도 제대로 관리할 수 있습니다.",
                "맡기더라도 작업 내역과 일자별 순위를 공유받을 수 있는지 확인하세요. 셀프로 해 보면 무엇에 돈을 써야 하는지가 보입니다."]),
              ("{q} {biz} 마케팅 비용은 얼마나 드나요?",
               ["무료로 할 수 있는 정보 정비·리뷰 관리를 먼저 하고, 유입 캠페인은 1회 {pmin}원부터 하루 100회 × 10일이면 {ex10}원입니다.",
                "셀프 운영은 단가 × 수량 × 기간이 전부입니다. 플레이스 최저 단가 {pmin}원 기준 100회씩 10일이면 {ex10}원입니다."])],
    "플레이스-상위노출": [("{q} {biz} 플레이스 1위를 보장받을 수 있나요?",
                       ["아니요. 순위는 네이버가 정하고 매일 바뀌며 누구도 보장할 수 없습니다. 보장을 내거는 곳은 조심하세요.",
                        "보장은 불가능합니다. 일자별 순위를 기록하면서 무엇이 효과였는지 직접 확인하는 방식이 가장 안전합니다."]),
                      ("순위가 오르는 데 얼마나 걸리나요?",
                       ["정보 정비 후 최소 1~2주의 추이를 보세요. 마이마케팅은 캠페인을 등록하는 순간부터 일자별 순위를 자동으로 기록합니다.",
                        "하루 이틀 변화로 판단하지 마세요. 시작 전 순위를 기준값으로 남기고 2주 단위로 비교합니다."])],
    "홍보": [("{q} {biz} 홍보, 돈을 안 쓰고 할 수 있는 건 뭔가요?",
             ["플레이스 정보 정비, 대표 사진 교체, 리뷰 답글, 소식 업데이트는 비용이 들지 않습니다. 대부분의 업체가 여기서 차이가 납니다.",
              "영수증 리뷰 안내와 모든 리뷰에 답글 달기만 꾸준히 해도 손님이 느끼는 신뢰가 달라집니다."]),
            ("체험단·SNS 홍보는 효과가 있나요?",
             ["업종마다 다릅니다. 진행한다면 협찬 표시를 반드시 하고, 실제 방문 경험이 담긴 글인지 확인하세요.",
              "사진이 강점인 업종이라면 효과가 큽니다. 다만 대가를 받은 글은 그 사실을 표시해야 합니다."])],
}


# ================================================================== builders
def _ctx(q, biz, intent, slug, prices):
    ix = _idx()
    r = ix["pairs"][(q, biz)]
    nat = ix["biz"][biz]
    sp_peers = ix["sido_biz"][(r["sido"], biz)]
    local = ix["q"][q]
    tot = r["demand"]
    kw = f"{q} {biz}"
    v = sp._vars(biz, "플레이스", prices, region=r["region"])
    v.update(q=q, biz=biz, sido=r["sido"], kw=kw, tot=sp.fmt(tot), pc=sp.fmt(r["demand_pc"]), mo=sp.fmt(r["demand_mo"]),
             mr=round(r["demand_mo"] * 100 / max(1, tot)), nat=next(i for i, x in enumerate(nat, 1) if x["q"] == q),
             nat_n=len(nat), srank=next(i for i, x in enumerate(sp_peers, 1) if x["q"] == q), s_n=len(sp_peers),
             lrank=next(i for i, x in enumerate(local, 1) if x["biz"] == biz), l_n=len(local),
             ltop=", ".join(x["biz"] for x in local[:3]),
             eul=sp.jo(biz, "을를"), eun=sp.jo(biz, "은는"), reg_eun=sp.jo(r["region"], "은는"))
    return r, v, sp_peers, local


def _fill(bank, slug, salt, v):
    # 키워드('강남 치과')는 늘 업종명으로 끝나서 조사는 업종명 기준 {eun}/{eul} 하나로 충분하다
    return sp.pick(bank, slug, salt).format(**v)


COMPARE = [
    "같은 {sido}의 {others}와 비교하면 '{kw}' 수요는 {cmp}입니다.",
    "{sido} 안 이웃 상권 {others}와 견줘 보면 {q}의 {biz} 수요는 {cmp}입니다.",
    "비교 기준으로 {others}를 보면, {q} {biz} 손님 검색은 {cmp}입니다.",
]


def _compare(v, peers, q, slug):
    """같은 시도 이웃 상권과 숫자 비교 — 페이지마다 다른 실데이터 문장."""
    others = [x for x in peers if x["q"] != q][:3]
    if not others:
        return ""
    me = next(x for x in peers if x["q"] == q)["demand"]
    avg = sum(x["demand"] for x in others) / len(others)
    ratio = me / avg if avg else 0
    cmp = (f"이들 평균의 {ratio:.1f}배로 큰 편" if ratio >= 1.2 else
           f"이들 평균의 {round(ratio * 100)}% 수준으로 작은 편" if ratio <= 0.8 else "이들과 비슷한 규모")
    names = ", ".join(f"{x['q']}(월 {sp.fmt(x['demand'])}회)" for x in others)
    return sp.pick(COMPARE, slug, "cmp").format(**{**v, "others": names, "cmp": cmp})


REL_DETAIL = [
    "'{k}'{eun} 월 {n}회로 메인 키워드의 {pct}% 규모입니다.",
    "'{k}' 검색은 한 달 {n}회, 메인 대비 {pct}%입니다.",
    "'{k}'(월 {n}회)는 메인 키워드의 {pct}%만큼 검색됩니다.",
]


def _rel_detail(rel, tot, slug):
    """연관 키워드 상위 3개를 메인 대비 비율로 — 지역마다 다른 숫자."""
    out = []
    for i, x in enumerate(rel[:3]):
        n = x["pc"] + x["mo"]
        out.append(sp.pick(REL_DETAIL, slug, f"rd{i}").format(k=x["k"], n=sp.fmt(n), pct=round(n * 100 / max(1, tot)),
                                                              eun=sp.jo(x["k"], "은는")))
    if out:
        out.append(sp.pick(["이런 표현을 업체 소개와 메뉴 설명에 자연스럽게 담아 두면 다른 말로 찾는 손님에게도 보입니다.",
                            "메인 키워드 하나에 매달리기보다 이런 연관 표현을 함께 관리하면 접점이 넓어집니다.",
                            "순위를 기록할 때도 메인 키워드와 이 연관 키워드들을 같이 보세요."], slug, "rdx"))
    return " ".join(out)


def _open_links(items):
    return [(n, p) for n, p in items if is_open(p.strip("/").split("/", 1)[1])]


def b_rbi(key, slug, prices):
    q, biz, intent = key
    r, v, peers, local = _ctx(q, biz, intent, slug, prices)
    group = r["group"]
    rel = r["related"]
    note = sp.pick(sp.GROUP_NOTE[group], slug, "grp") if group in sp.GROUP_NOTE else ""
    lead = _fill(LEAD[intent], slug, "lead", v)
    if intent == "마케팅":
        lead += sp._consumer_line(v["kw"], r["demand_pc"], r["demand_mo"], slug)
        secs = [
            {"h": f"{q} {biz} 상권 수요", "p": [_fill(DATA_MKT, slug, "dm", v), _compare(v, peers, q, slug),
                                             sp._interpret(r["demand_pc"], r["demand_mo"], None, slug)]},
            {"h": "손님이 쓰는 다른 표현", "p": [sp._related_line(rel, slug, r["demand"]), _rel_detail(rel, r["demand"], slug)], "related": rel},
            {"h": "셀프 마케팅 순서", "list": [s.format(**v) for s in sp.sample(sp.ANGLES["홍보-방법"]["steps"] + sp.ANGLES["키워드-찾기"]["steps"], slug, 9, "st")]},
            {"h": f"{biz} 업종에서 조심할 점", "p": [note, sp.para(sp.CAUTION, slug, "caut", v)]},
            {"h": "비용 계산", "p": [sp.para(sp.COST, slug, "cost", v), sp.para(sp.WHY, slug, "why", v)]},
            {"h": "결과 확인 방법", "p": [sp.para(sp.MEASURE, slug, "meas", v)]},
            {"h": "자주 하는 실수", "sub": sp._mistakes(slug, 4)},
        ]
        title = f"{q} {biz} 마케팅 · 손님 월 {v['tot']}회 검색 상권 분석"
        desc = (f"{r['region']} {biz} 마케팅을 직접 하려는 사장님을 위한 상권 데이터. '{v['kw']}' 월 {v['tot']}회 검색, "
                f"전국 {v['nat_n']}곳 중 {v['nat']}위. 셀프 마케팅 순서와 비용 계산까지.")
        stats = [("손님 월 검색", v["tot"] + "회"), ("전국 순위", f"{v['nat']}/{v['nat_n']}"),
                 (f"{r['sido']} 안 순위", f"{v['srank']}/{v['s_n']}"), ("모바일 비중", f"{v['mr']}%")]
    elif intent == "플레이스-상위노출":
        lead += _fill(DATA_PLACE, slug, "lp", v)
        factors = sp.sample(PLACE_FACTORS, slug, 4, "pf")
        secs = [
            {"h": f"지도에서 '{q} {biz}'를 찾는 손님", "p": [sp._consumer_line(v["kw"], r["demand_pc"], r["demand_mo"], slug + "p"),
                                                       sp.pick(sp.INTERPRET["tier"][sp.tier(r["demand"])], slug, "pt"), _compare(v, peers, q, slug + "p")]},
            {"h": "함께 노려볼 키워드", "p": [sp._related_line(rel, slug + "p"), _rel_detail(rel, r["demand"], slug + "p")], "related": rel},
            {"h": "플레이스 순위에 영향을 주는 것", "sub": [{"q": t, "a": sp.pick(a, slug, t)} for t, a in factors]},
            {"h": "상위노출 실행 순서", "list": [s.format(**v) for s in sp.sample(sp.ANGLES["플레이스-상위노출"]["steps"], slug, 9, "ps")]},
            {"h": "유입 캠페인으로 순위 관리하기",
             "p": [f"정보 정비가 끝났다면 유입 캠페인으로 노출을 앞당길 수 있습니다. 마이마케팅 플레이스 매체는 1회 {v['pmin']}원부터, "
                   f"하루 100회씩 10일이면 {v['ex10']}원이고 최소 작업일수는 3일입니다.",
                   sp.para(sp.MEASURE, slug, "pm", v)]},
            {"h": "주의할 점", "p": [sp.para(sp.CAUTION, slug, "pc", v), note]},
            {"h": "직접 관리하면 좋은 이유", "p": [sp.para(sp.WHY, slug, "pw", v)]},
        ]
        title = f"{q} {biz} 플레이스 상위노출 · 순위 올리는 순서와 비용"
        desc = (f"'{v['kw']}' 지도 검색 월 {v['tot']}회(모바일 {v['mr']}%). {q} {biz} 플레이스 순위에 영향을 주는 요소, "
                f"실행 순서, 유입 캠페인 비용을 사장님이 직접 할 수 있게 정리했습니다.")
        stats = [("지도 검색(월)", v["tot"] + "회"), ("모바일", v["mo"] + "회"), ("PC", v["pc"] + "회"),
                 ("1회 단가", f"{v['pmin']}원~")]
    else:  # 홍보
        lead += _fill(DATA_PROMO, slug, "lh", v)
        chans = sp.sample(CHANNELS, slug, 5, "ch")
        others = [x for x in local if x["biz"] != biz][:5]
        secs = [
            {"h": f"{q} 손님이 많이 찾는 업종", "p": [_fill(DATA_PROMO, slug, "dp2", v), sp.pick(sp.INTERPRET["mobile"]["very" if v["mr"] >= 85 else "high" if v["mr"] >= 70 else "pc"], slug, "hm")],
             "itemlist": [(f"{q} {x['biz']} 홍보", f"/learn/{q}-{x['biz']}-홍보/", sp.fmt(x["demand"]) + "회") for x in [r] + others]},
            {"h": "채널별로 할 일", "sub": [{"q": t, "a": sp.pick(a, slug, t)} for t, a in chans]},
            {"h": "리뷰로 신뢰 쌓기", "list": [s.format(**v) for s in sp.sample(sp.ANGLES["리뷰-관리"]["steps"], slug, 8, "rv")]},
            {"h": "예산은 이렇게 나눕니다", "p": [sp.para(sp.COST, slug, "hc", v), note]},
            {"h": "주변 상권과 비교", "p": [_compare(v, peers, q, slug + "h"), _rel_detail(rel, r["demand"], slug + "h"), sp.para(sp.MEASURE, slug, "hm2", v)]},
            {"h": "자주 하는 실수", "sub": sp._mistakes(slug + "h", 4)},
        ]
        title = f"{q} {biz} 홍보 방법 · 손님이 찾는 경로와 채널별 할 일"
        desc = (f"{r['region']} {biz} 홍보를 직접 하려는 사장님께. 이 지역 업종 중 손님 검색 {v['lrank']}위, '{v['kw']}' 월 {v['tot']}회. "
                f"플레이스·리뷰·블로그·SNS 채널별 할 일과 예산 나누는 법.")
        stats = [("손님 월 검색", v["tot"] + "회"), (f"{q} 업종 순위", f"{v['lrank']}/{v['l_n']}"),
                 ("1위 업종", local[0]["biz"]), ("모바일 비중", f"{v['mr']}%")]

    # 업종 관점 문단 — 의도마다 다른 각도의 도입 뱅크를 업종명으로 (본문 분량 + 의도별 차이)
    ang = {"마케팅": "마케팅-비용", "플레이스-상위노출": "네이버-광고", "홍보": "홍보-방법"}[intent]
    secs.insert(2, {"h": f"{biz} 사장님이 먼저 알아야 할 것", "p": [sp.para(sp.ANGLES[ang]["intro"], slug, "ai", v),
                                                           sp.para(sp.ANGLES["키워드-찾기"]["intro"], slug, "ak", v)]})
    if not rel:   # 연관 키워드가 없는 작은 상권 — 대신 수요 해석을 한 문단 더
        secs.insert(1, {"h": "작은 상권에서의 전략", "p": [sp.pick(sp.INTERPRET["tier"]["low"], slug, "lw"),
                                                    sp.pick(sp.INTERPRET["mobile"]["very" if v["mr"] >= 85 else "high" if v["mr"] >= 70 else "pc"], slug, "lwm")]})
    secs = [s for s in secs if any(s.get(k) for k in ("p", "list", "sub", "itemlist"))]
    for s in secs:
        if s.get("p"):
            s["p"] = [t for t in s["p"] if t]
    faq = sp._faq(FAQ_INTENT[intent], slug, v) + sp._common_faq(slug, v)
    near = [x for x in peers if x["q"] != q][:6]
    lab = LABEL[intent]
    links = [
        (f"{q} {biz} · 다른 주제", _open_links([(f"{q} {biz} {LABEL[i]}", f"/learn/{q}-{biz}-{i}/") for i in INTENTS if i != intent])),
        (f"{biz} {lab} · {r['sido']} 다른 지역", _open_links([(f"{x['q']} {biz} {lab}", f"/learn/{x['q']}-{biz}-{intent}/") for x in near])),
        (f"{q} · 다른 업종", _open_links([(f"{q} {x['biz']} {lab}", f"/learn/{q}-{x['biz']}-{intent}/") for x in local if x["biz"] != biz][:8])),
        (f"{biz} 업종 가이드", [(f"{biz} {A['label']}", f"/learn/{biz}-{a}/") for a, A in list(sp.ANGLES.items())[:4]]),
    ]
    return {"kw": f"{q} {biz} {lab}", "channel": "place", "title": title, "desc": desc, "h1": f"{q} {biz} {lab}",
            "lead": lead, "stats": stats, "sections": secs, "faq": faq, "links": links,
            "crumbs": [("셀프 마케팅 가이드", "/learn/"), (f"{r['sido']} 지역", f"/learn/{r['sido']}-지역-마케팅/"),
                       (f"{q} 마케팅", f"/learn/{q}-마케팅/"), (f"{biz} {lab}", None)],
            "region": r["region"], "sido": r["sido"]}


def b_sghub(q, slug, prices):
    ix = _idx()
    rows = ix["q"][q]
    r0 = rows[0]
    total = sum(x["demand"] for x in rows)
    v = sp._vars("우리 업종", "플레이스", prices)
    sido_list = ix["sido"][r0["sido"]]
    pos = sido_list.index(q) + 1
    groups = {}
    for x in rows:
        groups[x["group"]] = groups.get(x["group"], 0) + x["demand"]
    g, gv = max(groups.items(), key=lambda kv: kv[1])
    items = _open_links([(f"{q} {x['biz']} 마케팅", f"/learn/{q}-{x['biz']}-마케팅/") for x in rows])
    vol = {f"/learn/{q}-{x['biz']}-마케팅/": sp.fmt(x["demand"]) + "회" for x in rows}
    return {"kw": f"{q} 마케팅", "channel": "place",
            "title": f"{q} 마케팅 · 업종별 손님 검색량 {len(rows)}개 업종",
            "desc": f"{r0['sido']} {r0['region']} 상권에서 장사하는 사장님을 위한 업종별 손님 검색량. 가장 많이 찾는 업종은 {r0['biz']}(월 {sp.fmt(r0['demand'])}회), 업종별 셀프 마케팅 가이드로 이어집니다.",
            "h1": f"{q} 마케팅 — 업종별 손님 수요",
            "lead": f"{r0['region']}에서 업종 이름과 함께 검색되는 횟수를 합치면 한 달 약 {sp.fmt(total)}회입니다. {r0['sido']} {len(sido_list)}개 지역 중 {pos}번째로 큰 상권입니다. 우리 업종의 숫자를 확인하고 바로 가이드로 넘어가세요.",
            "stats": [("업종 수", f"{len(rows)}개"), ("합계 월 검색", sp.fmt(total) + "회"), ("1위 업종", r0["biz"]), (f"{r0['sido']} 안 순위", f"{pos}/{len(sido_list)}")],
            "sections": [{"h": f"{q} 상권 한눈에", "p": [sp._consumer_line(f"{q} {x['biz']}", x["demand_pc"], x["demand_mo"], slug + x["biz"]) for x in rows[:3]] + [f"손님 검색이 가장 많은 업종은 {', '.join(x['biz'] + '(' + sp.fmt(x['demand']) + '회)' for x in rows[:3])} 순입니다. 업종군으로 묶으면 '{g}'{sp.jo(g, '이가')} 전체의 {round(gv * 100 / max(1, total))}%를 차지합니다."]},
                         {"h": f"{q} 업종별 손님 검색량", "itemlist": [(n, p, vol[p]) for n, p in items]},
                         {"h": "이 숫자를 어떻게 쓰나요", "p": [sp.para(sp.MEASURE, slug, "m", v), sp.para(sp.WHY, slug, "w", v), sp.para(sp.COST, slug, "c", v)]},
                         {"h": "자주 하는 실수", "sub": sp._mistakes(slug, 3)}],
            "faq": [], "links": [(f"{r0['sido']} 다른 지역", [(f"{x} 마케팅", f"/learn/{x}-마케팅/") for x in sido_list if x != q][:12])],
            "crumbs": [("셀프 마케팅 가이드", "/learn/"), (f"{r0['sido']} 지역", f"/learn/{r0['sido']}-지역-마케팅/"), (f"{q} 마케팅", None)],
            "region": r0["region"], "sido": r0["sido"]}


def b_sidohub(sido, slug, prices):
    ix = _idx()
    qs = ix["sido"][sido]
    tot = {q: sum(x["demand"] for x in ix["q"][q]) for q in qs}
    allsum = sum(tot.values())
    top_biz = {}
    for q in qs:
        for x in ix["q"][q]:
            top_biz[x["biz"]] = top_biz.get(x["biz"], 0) + x["demand"]
    tb = sorted(top_biz.items(), key=lambda kv: -kv[1])[:5]
    return {"kw": f"{sido} 지역 마케팅", "channel": "place",
            "title": f"{sido} 지역 마케팅 · 시군구 {len(qs)}곳 업종별 손님 검색량",
            "desc": f"{sido} {len(qs)}개 지역의 업종별 네이버 손님 검색량. 가장 큰 상권은 {qs[0]}, 가장 많이 찾는 업종은 {tb[0][0]}입니다. 지역을 골라 셀프 마케팅 가이드로 이어가세요.",
            "h1": f"{sido} 지역별 마케팅 가이드",
            "lead": f"{sido}에서 업종 이름과 함께 검색되는 횟수는 한 달 약 {sp.fmt(allsum)}회입니다. 지역마다 손님이 많이 찾는 업종이 다르니, 우리 가게가 있는 곳의 숫자부터 확인하세요.",
            "stats": [("지역 수", f"{len(qs)}곳"), ("합계 월 검색", sp.fmt(allsum) + "회"), ("가장 큰 상권", qs[0]), ("1위 업종", tb[0][0])],
            "sections": [{"h": f"{sido}에서 많이 찾는 업종", "p": [", ".join(f"{b}(월 {sp.fmt(n)}회)" for b, n in tb) + " 순입니다.",
                                                             " ".join(f"{q}에서는 {ix['q'][q][0]['biz']}{sp.jo(ix['q'][q][0]['biz'], '이가')} 가장 많이 검색됩니다(월 {sp.fmt(ix['q'][q][0]['demand'])}회)." for q in qs[:5])]},
                         {"h": "지역 페이지 활용법", "p": [sp.para(sp.MEASURE, slug, "m", sp._vars("우리 업종", "플레이스", prices)),
                                                     sp.para(sp.WHY, slug, "w", sp._vars("우리 업종", "플레이스", prices))]},
                         {"h": f"{sido} 지역별 손님 검색량", "itemlist": [(f"{q} 마케팅", f"/learn/{q}-마케팅/", sp.fmt(tot[q]) + "회") for q in qs]}],
            "faq": [], "links": [("다른 시도", [(f"{s} 지역 마케팅", f"/learn/{s}-지역-마케팅/") for s in ix["sido"] if s != sido])],
            "crumbs": [("셀프 마케팅 가이드", "/learn/"), (f"{sido} 지역", None)], "sido": sido}


BUILDERS = {"rbi": b_rbi, "sghub": b_sghub, "sidohub": b_sidohub}
