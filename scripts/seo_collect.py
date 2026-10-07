"""SEO 기본 페이지용 실데이터 수집 (네이버 검색광고 키워드도구) → data/seo/*.json

    python scripts/seo_collect.py            # 전체 (약 15~20분, 결과는 git 에 커밋)
    python scripts/seo_collect.py --limit 20 # 시험 수집
    python scripts/seo_collect.py --seller   # 판매자 의도 키워드("치과마케팅" 등) 검색량만

페이지를 문장 조합이 아니라 **실제 검색량·연관 키워드**로 차별화하기 위한 원천이다 (docs/SEO_PLAN.md).
지역×업종 후보를 전부 조회해 월간 검색량이 MIN_VOLUME 이상인 조합만 남긴다 — 검색되지 않는
조합의 페이지는 만들지 않는다. 결과는 생성 시점의 스냅샷이고, 다시 돌리면 갱신된다.
"""
import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.services import naver_ad  # noqa: E402

OUT = ROOT / "data" / "seo"
MIN_VOLUME = 150        # 월간 PC+모바일 — 이보다 적은 조합은 페이지를 만들지 않는다
MAX_PLACE_PAGES = 820
SLEEP = 0.25            # 검색광고 API 호출 간격

# 사람들이 실제로 검색하는 짧은 지역명 (구 이름의 '구' 를 떼거나 생활권 이름).
REGIONS = {
    "서울": ["강남", "서초", "송파", "잠실", "강동", "마포", "홍대", "합정", "용산", "이태원", "성수", "건대", "왕십리",
           "동대문", "청량리", "성북", "노원", "도봉", "은평", "연신내", "신촌", "종로", "을지로", "영등포", "여의도",
           "구로", "신도림", "관악", "신림", "사당", "목동", "강서", "마곡", "발산"],
    "경기": ["분당", "판교", "수원", "광교", "영통", "용인", "수지", "기흥", "동탄", "평택", "안양", "평촌", "군포", "산본",
           "안산", "시흥", "광명", "부천", "김포", "일산", "파주", "운정", "의정부", "남양주", "다산", "구리", "하남",
           "미사", "위례", "이천", "오산", "고양"],
    "인천": ["인천", "송도", "청라", "부평", "구월동", "계양", "검단"],
    "부산": ["부산", "해운대", "서면", "센텀", "동래", "광안리", "연산동"],
    "대구": ["대구", "동성로", "수성구", "범어동"],
    "대전": ["대전", "둔산동", "유성"],
    "광주": ["광주", "상무지구", "수완지구"],
    "울산": ["울산", "삼산동"],
    "세종": ["세종"],
    "충청": ["청주", "천안", "아산"],
    "전라": ["전주", "여수", "순천", "목포"],
    "경상": ["창원", "김해", "포항", "구미", "진주", "경주"],
    "강원": ["원주", "춘천", "강릉"],
    "제주": ["제주", "서귀포"],
}

# 플레이스(지도) 검색이 실제로 매출이 되는 업종.
BIZ = {
    "병원·의원": ["치과", "피부과", "한의원", "정형외과", "성형외과", "안과", "이비인후과", "소아과", "산부인과", "내과",
               "비뇨기과", "정신건강의학과", "동물병원"],
    "뷰티": ["미용실", "네일샵", "피부관리", "왁싱", "속눈썹", "두피관리"],
    "운동": ["필라테스", "요가", "헬스장", "PT", "골프연습장", "복싱", "크로스핏"],
    "교육": ["영어학원", "수학학원", "피아노학원", "미술학원", "태권도", "스터디카페", "코딩학원"],
    "음식점": ["맛집", "고기집", "횟집", "카페", "베이커리", "술집", "오마카세"],
    "생활 서비스": ["인테리어", "이사", "입주청소", "세탁", "꽃집", "사진관", "안경점", "자동차정비", "세차"],
    "전문 서비스": ["변호사", "세무사", "법무사", "부동산", "공인중개사"],
}

# 스마트스토어 · 쇼핑검색 카테고리 대표 키워드.
STORE = {
    "생활": ["무선청소기", "로봇청소기", "가습기", "제습기", "공기청정기", "전기요", "수건", "이불"],
    "주방": ["에어프라이어", "텀블러", "밀폐용기", "프라이팬", "커피머신"],
    "식품": ["한우선물세트", "과일선물세트", "닭가슴살", "견과류", "제주감귤", "김치"],
    "반려동물": ["강아지사료", "고양이모래", "강아지간식", "고양이사료", "펫매트"],
    "패션": ["여성원피스", "남자니트", "운동화", "가방", "레인부츠"],
    "캠핑·레저": ["캠핑의자", "텐트", "캠핑테이블", "등산화", "요가매트"],
    "디지털": ["무선이어폰", "보조배터리", "키보드", "모니터암", "usb선풍기"],
    "유아": ["기저귀", "아기물티슈", "유모차", "아기띠"],
}


def chunks(xs, n):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def stats(hints):
    """keyword_stats 재시도 래퍼. 반환은 {키워드(공백 제거): row}."""
    for attempt in range(4):
        try:
            rows = naver_ad.keyword_stats(hints)
            time.sleep(SLEEP)
            return {r["keyword"].replace(" ", ""): r for r in rows}, rows
        except naver_ad.NaverAdError as e:
            wait = 2 * (attempt + 1)
            print(f"  재시도 {attempt + 1} ({e}) — {wait}s", flush=True)
            time.sleep(wait)
    return {}, []


def related_top(rows, must, exclude, n=10):
    """연관 키워드 중 must 를 포함하는 것만, 검색량 순 n 개."""
    out = []
    for r in sorted(rows, key=lambda r: -(r["pc"] + r["mo"])):
        k = r["keyword"]
        if k == exclude or not any(m in k for m in must):
            continue
        out.append({"k": k, "pc": r["pc"], "mo": r["mo"]})
        if len(out) >= n:
            break
    return out


def collect_seller():
    """판매자 의도 키워드 검색량 → data/seo/seller.json  {"rows": {키워드(공백 제거): 월간 합계}}"""
    from app.services.seo_pages import ANGLES, TOPICS
    kws = []
    for bs in BIZ.values():
        for b in bs:
            kws.append(f"{b}마케팅")
            kws += [f"{b}{A['label'].replace(' ', '')}" for A in ANGLES.values()]
    kws += [f"{p}{a.replace(' ', '')}" for p, a, _ in TOPICS]
    kws = list(dict.fromkeys(kws))
    vol = {}
    for i, batch in enumerate(chunks(kws, 5)):
        by, _ = stats(batch)
        for k in batch:
            if by.get(k):
                vol[k] = by[k]["pc"] + by[k]["mo"]
        if i % 20 == 0:
            print(f"  판매자 키워드 {i * 5}/{len(kws)}", flush=True)
    meta = {"collected": date.today().isoformat(), "source": "네이버 검색광고 키워드도구"}
    (OUT / "seller.json").write_text(json.dumps({"meta": meta, "rows": vol}, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"저장: seller {len(vol)}/{len(kws)} → {OUT / 'seller.json'}")


def main():
    if "--seller" in sys.argv:
        with create_app().app_context():
            collect_seller()
        return 0
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    app = create_app()
    OUT.mkdir(parents=True, exist_ok=True)
    with app.app_context():
        if not naver_ad.configured():
            print("NAVER_AD_* 키가 없습니다."); return 1

        # 1) 지역 × 업종 검색량 스캔 (5개씩)
        cands = [(sido, rg, grp, b) for sido, rgs in REGIONS.items() for rg in rgs
                 for grp, bs in BIZ.items() for b in bs]
        if limit:
            cands = cands[:limit]
        print(f"지역×업종 후보 {len(cands)}개 조회", flush=True)
        vol = {}
        for i, batch in enumerate(chunks(cands, 5)):
            by, _ = stats([rg + b for _, rg, _, b in batch])
            for c in batch:
                r = by.get(c[1] + c[3])
                if r:
                    vol[c] = r
            if i % 50 == 0:
                print(f"  {i * 5}/{len(cands)}", flush=True)
        kept = sorted(((c, r) for c, r in vol.items() if r["pc"] + r["mo"] >= MIN_VOLUME),
                      key=lambda x: -(x[1]["pc"] + x[1]["mo"]))[:MAX_PLACE_PAGES]
        print(f"검색량 {MIN_VOLUME}+ 조합 {len(kept)}개 → 연관 키워드 수집", flush=True)

        # 2) 남은 조합마다 연관 키워드 (단일 힌트)
        place = []
        for i, ((sido, rg, grp, b), r) in enumerate(kept):
            _, rows = stats([rg + b])
            place.append({"sido": sido, "region": rg, "group": grp, "biz": b, "pc": r["pc"], "mo": r["mo"],
                          "comp": r["comp"], "related": related_top(rows, [b], rg + b)})
            if i % 50 == 0:
                print(f"  연관 {i}/{len(kept)}", flush=True)

        # 3) 업종 전국 키워드 (업종 가이드 페이지)
        biz = []
        for grp, bs in BIZ.items():
            for b in bs:
                _, rows = stats([b])
                me = next((x for x in rows if x["keyword"].replace(" ", "") == b), {"pc": 0, "mo": 0, "comp": None})
                biz.append({"group": grp, "biz": b, "pc": me["pc"], "mo": me["mo"], "comp": me["comp"],
                            "related": related_top(rows, [b], b, 12)})

        # 4) 스마트스토어 카테고리 키워드
        store = []
        for grp, ks in STORE.items():
            for k in ks:
                _, rows = stats([k])
                me = next((x for x in rows if x["keyword"].replace(" ", "") == k), {"pc": 0, "mo": 0, "comp": None})
                store.append({"group": grp, "kw": k, "pc": me["pc"], "mo": me["mo"], "comp": me["comp"],
                              "related": related_top(rows, [k[-2:]], k, 12)})

    meta = {"collected": date.today().isoformat(), "source": "네이버 검색광고 키워드도구", "min_volume": MIN_VOLUME}
    for name, rows in (("place", place), ("biz", biz), ("store", store)):
        (OUT / f"{name}.json").write_text(json.dumps({"meta": meta, "rows": rows}, ensure_ascii=False, indent=0),
                                          encoding="utf-8")
    print(f"저장: place {len(place)} · biz {len(biz)} · store {len(store)} → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
