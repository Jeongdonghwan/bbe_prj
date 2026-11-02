"""전국 시군구 × 업종 × 의도 키워드 실측 → data/seo/sg.json + keywords/마이마케팅_전국.xlsx

    python scripts/seo_keywords_sg.py               # 전체 (처음 약 1시간, 이후 캐시로 빠름)
    python scripts/seo_keywords_sg.py --limit 30    # 시험
    python scripts/seo_keywords_sg.py --seller-vol  # 판매자 의도 검색량도 잰다 (대부분 10 미만이라 기본은 생략)

/learn 확장(docs/SEO_PLAN.md, 2026-11-02) 1단계. curtain_prj 처럼 키워드 엑셀(키워드 시트 1장)을 먼저 뽑는다.
  - 지역: 전국 시군구 (서울·경기로 시작했다가 2026-11-02 JDH "지방도 하라") — 검색어는 사람들이 치는 짧은 이름
  - 업종: seo_collect.BIZ (플레이스 검색이 매출이 되는 업종)
  - 의도: 마케팅 / 플레이스 상위노출 / 홍보 — 판매자 검색어. 손님 키워드("강남치과")는 페이지 주제가 아니라
    "이 지역에 이 업종 손님 수요가 있다"는 근거와 포함 기준으로만 쓴다.
포함 기준: 손님 키워드 월간 검색량 MIN_DEMAND 이상인 지역×업종만 페이지(의도 3개)를 만든다.
측정값은 data/seo/sg_cache.json 에 쌓아 다시 돌릴 때 재조회하지 않는다.
"""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from app import create_app  # noqa: E402
from app.services import naver_ad  # noqa: E402
from seo_collect import BIZ, chunks, related_top, stats  # noqa: E402

MIN_DEMAND = 100   # 손님 월간 검색량(PC+모바일) — 이보다 적으면 그 지역×업종 페이지는 만들지 않는다
CACHE = ROOT / "data" / "seo" / "sg_cache.json"

# 시도 → 시군구 (공식 이름). 광역시의 중·동·서·남·북구처럼 여러 곳에 있는 이름은 시 이름을 붙여 검색한다.
SIGUNGU = {
    "서울": "강남구 강동구 강북구 강서구 관악구 광진구 구로구 금천구 노원구 도봉구 동대문구 동작구 마포구 서대문구 서초구 "
            "성동구 성북구 송파구 양천구 영등포구 용산구 은평구 종로구 중구 중랑구",
    "경기": "수원시 성남시 고양시 용인시 부천시 안산시 안양시 남양주시 화성시 평택시 의정부시 시흥시 파주시 김포시 광명시 "
            "광주시 군포시 하남시 오산시 이천시 안성시 의왕시 양주시 구리시 포천시 여주시 동두천시 과천시 가평군 양평군 연천군",
    "인천": "중구 동구 미추홀구 연수구 남동구 부평구 계양구 서구 강화군 옹진군",
    "부산": "중구 서구 동구 영도구 부산진구 동래구 남구 북구 해운대구 사하구 금정구 강서구 연제구 수영구 사상구 기장군",
    "대구": "중구 동구 서구 남구 북구 수성구 달서구 달성군 군위군",
    "광주": "동구 서구 남구 북구 광산구",
    "대전": "동구 중구 서구 유성구 대덕구",
    "울산": "중구 남구 동구 북구 울주군",
    "세종": "세종시",
    "강원": "춘천시 원주시 강릉시 동해시 태백시 속초시 삼척시 홍천군 횡성군 영월군 평창군 정선군 철원군 화천군 양구군 인제군 고성군 양양군",
    "충북": "청주시 충주시 제천시 보은군 옥천군 영동군 증평군 진천군 괴산군 음성군 단양군",
    "충남": "천안시 공주시 보령시 아산시 서산시 논산시 계룡시 당진시 금산군 부여군 서천군 청양군 홍성군 예산군 태안군",
    "전북": "전주시 군산시 익산시 정읍시 남원시 김제시 완주군 진안군 무주군 장수군 임실군 순창군 고창군 부안군",
    "전남": "목포시 여수시 순천시 나주시 광양시 담양군 곡성군 구례군 고흥군 보성군 화순군 장흥군 강진군 해남군 영암군 "
            "무안군 함평군 영광군 장성군 완도군 진도군 신안군",
    "경북": "포항시 경주시 김천시 안동시 구미시 영주시 영천시 상주시 문경시 경산시 의성군 청송군 영양군 영덕군 청도군 "
            "고령군 성주군 칠곡군 예천군 봉화군 울진군 울릉군",
    "경남": "창원시 진주시 통영시 사천시 김해시 밀양시 거제시 양산시 의령군 함안군 창녕군 고성군 남해군 하동군 산청군 "
            "함양군 거창군 합천군",
    "제주": "제주시 서귀포시",
}
METRO = {"인천", "부산", "대구", "광주", "대전", "울산"}
SPECIAL = {("서울", "중구"): "명동", ("경기", "광주시"): "경기광주", ("강원", "고성군"): "강원고성",
           ("경남", "고성군"): "경남고성", ("부산", "강서구"): "부산강서", ("대구", "군위군"): "군위",
           ("세종", "세종시"): "세종"}


def short(name):
    return name[:-1] if len(name) > 2 and name[-1] in "시군구" else name


def regions():
    out = []
    for sido, names in SIGUNGU.items():
        for n in names.split():
            if (sido, n) in SPECIAL:
                q = SPECIAL[(sido, n)]
            elif sido in METRO and n[:-1] in ("중", "동", "서", "남", "북"):
                q = f"{sido}{n[:-1]}구"              # 부산중구 · 대구북구
            else:
                q = short(n)
            out.append({"sido": sido, "name": n, "q": q})
    return out


INTENTS = [("마케팅", "마케팅"), ("플레이스-상위노출", "플레이스상위노출"), ("홍보", "홍보")]


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {"demand": {}, "seller": {}}
    # 서울·경기 첫 실행(sg.json) 결과도 캐시로 쓴다
    old = ROOT / "data" / "seo" / "sg.json"
    if old.exists():
        for r in json.loads(old.read_text(encoding="utf-8"))["rows"]:
            cache["demand"].setdefault(f"{r['q']}{r['biz']}", {"pc": r["demand_pc"], "mo": r["demand_mo"],
                                                               "vol": r["demand"], "related": r["related"]})

    def save_cache():
        CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    app = create_app()
    with app.app_context():
        if not naver_ad.configured():
            print("NAVER_AD_* 키가 없습니다."); return 1
        regs = regions()
        bizs = [(g, b) for g, bs in BIZ.items() for b in bs]
        pairs = [(r, g, b) for r in regs for g, b in bizs][:limit]
        todo = [p for p in pairs if f"{p[0]['q']}{p[2]}" not in cache["demand"]]
        print(f"지역 {len(regs)} × 업종 {len(bizs)} = 손님 키워드 {len(pairs)}개 (새로 조회 {len(todo)}개)", flush=True)

        # 1) 손님 수요: "강남치과"
        for i, batch in enumerate(chunks(todo, 5)):
            kws = [f"{r['q']}{b}" for r, _, b in batch]
            by, rows = stats(kws)
            for (r, g, b), k in zip(batch, kws):
                row = by.get(k)
                cache["demand"][k] = {"pc": row["pc"] if row else 0, "mo": row["mo"] if row else 0,
                                      "vol": (row["pc"] + row["mo"]) if row else 0,
                                      "related": [x for x in related_top(rows, [b], k, 10) if x["k"] != b][:6] if row else []}
            if i % 40 == 0:
                print(f"  손님 {i * 5}/{len(todo)}", flush=True)
                save_cache()
        save_cache()
        demand = cache["demand"]
        keep = [(r, g, b) for r, g, b in pairs if demand[f"{r['q']}{b}"]["vol"] >= MIN_DEMAND]
        print(f"수요 {MIN_DEMAND}+ 지역×업종 {len(keep)}개 → 페이지 {len(keep) * len(INTENTS)}개", flush=True)

        # 2) 판매자 의도: "강남치과마케팅" 등 — 대부분 10 미만이라 요청할 때만
        if "--seller-vol" in sys.argv:
            kws = [f"{r['q']}{b}{q}" for r, _, b in keep for _, q in INTENTS if f"{r['q']}{b}{q}" not in cache["seller"]]
            for i, batch in enumerate(chunks(kws, 5)):
                by, _ = stats(batch)
                for k in batch:
                    row = by.get(k)
                    cache["seller"][k] = (row["pc"] + row["mo"]) if row else 0
                if i % 80 == 0:
                    print(f"  판매자 {i * 5}/{len(kws)}", flush=True); save_cache()
            save_cache()
    seller = cache["seller"]

    rows = []
    for r, g, b in keep:
        d = demand[f"{r['q']}{b}"]
        for slug_word, q in INTENTS:
            rows.append({"sido": r["sido"], "region": r["name"], "q": r["q"], "group": g, "biz": b,
                         "intent": slug_word, "keyword": f"{r['q']} {b} {slug_word.replace('-', ' ')}",
                         "slug": f"{r['q']}-{b}-{slug_word}", "seller_vol": seller.get(f"{r['q']}{b}{q}"),
                         "demand_pc": d["pc"], "demand_mo": d["mo"], "demand": d["vol"], "related": d["related"]})
    out = ROOT / "data" / "seo" / "sg.json"
    meta = {"collected": date.today().isoformat(), "source": "네이버 검색광고 키워드도구", "min_demand": MIN_DEMAND,
            "regions": len(regions()), "biz": sum(len(v) for v in BIZ.values())}
    out.write_text(json.dumps({"meta": meta, "rows": rows}, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"저장 {len(rows)}행 → {out}")

    # 키워드 엑셀 — 키워드 시트 1장 (요약은 대화로 알린다)
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook(); ws = wb.active; ws.title = "키워드"
    ws.append(["시도", "시군구", "업종 분류", "업종", "의도", "페이지 키워드", "주소", "손님 수요 키워드", "손님 검색량(월)",
               "PC", "모바일", "판매자 검색량(월)"])
    for c in ws[1]:
        c.font = Font(bold=True)
    for x in sorted(rows, key=lambda x: (-x["demand"], x["slug"])):
        ws.append([x["sido"], x["region"], x["group"], x["biz"], x["intent"].replace("-", " "), x["keyword"],
                   f"/learn/{x['slug']}/", f"{x['q']}{x['biz']}", x["demand"], x["demand_pc"], x["demand_mo"],
                   x["seller_vol"] if x["seller_vol"] is not None else "-"])
    ws.freeze_panes = "A2"
    for col, w in zip("ABCDEFGHIJKL", [6, 10, 12, 12, 14, 28, 36, 16, 14, 9, 9, 14]):
        ws.column_dimensions[col].width = w
    x = ROOT / "keywords" / "마이마케팅_전국.xlsx"
    x.parent.mkdir(exist_ok=True)
    wb.save(x)
    print(f"엑셀 → {x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
