"""블로그 키워드 큐 생성 → content/keywords.json (AI 없이 주제 × 각도 템플릿 조합, 2026-10-07).

    python scripts/seo_keywords.py           # 큐 다시 만들기 (커서는 건드리지 않는다)

타깃은 마케팅을 직접 하려는 사장님·판매자. 그래서 주제는 '업종/플랫폼 + 마케팅 의도'다.
지역 × 업종 조합은 블로그에 넣지 않는다 — 그건 /learn 기본 페이지가 맡고, 블로그에서 지역만
바꾼 글을 찍으면 중복 문서가 된다. 순서는 같은 업종·같은 각도가 연달아 나오지 않게 섞는다
(해시 정렬이라 매번 같은 결과 → 커서 위치가 의미를 유지한다).

항목: {"kw": 글의 메인 키워드, "angle": 각도 id, "subject": 업종/플랫폼, "kind": biz|platform|general}
루틴은 content/keyword-cursor.json 의 next 부터 꺼내 쓰고 next 를 올린다 (docs/BLOG_ROUTINE.md).
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scripts.seo_collect import BIZ  # noqa: E402

OUT = ROOT / "content" / "keywords.json"
CURSOR = ROOT / "content" / "keyword-cursor.json"

# 업종 × 각도 — {s} = 업종
BIZ_ANGLES = {
    "마케팅-방법": "{s} 마케팅 방법", "홍보-아이디어": "{s} 홍보 아이디어", "신규-오픈": "{s} 신규 오픈 홍보",
    "플레이스-세팅": "{s} 네이버 플레이스 세팅", "플레이스-순위": "{s} 플레이스 순위 올리는 법", "플레이스-사진": "{s} 플레이스 사진 잘 찍는 법",
    "플레이스-소개글": "{s} 플레이스 소개글 쓰는 법", "리뷰-늘리기": "{s} 리뷰 늘리는 방법", "리뷰-답글": "{s} 리뷰 답글 예시",
    "악성-리뷰": "{s} 악성 리뷰 대처법", "영수증-리뷰": "{s} 영수증 리뷰 받는 법", "키워드": "{s} 마케팅 키워드 찾는 법",
    "검색광고": "{s} 네이버 검색광고 하는 법", "광고-비용": "{s} 광고 비용", "마케팅-비용": "{s} 마케팅 비용 계산",
    "대행사-고르기": "{s} 마케팅 대행사 고르는 법", "보장-업체": "{s} 상위노출 보장 업체 주의할 점", "체크리스트": "{s} 마케팅 체크리스트",
    "블로그": "{s} 블로그 마케팅", "체험단": "{s} 체험단 진행 방법", "인스타": "{s} 인스타그램 홍보",
    "당근": "{s} 당근 광고", "단골": "{s} 단골 만드는 법", "비수기": "{s} 비수기 마케팅", "이벤트": "{s} 이벤트 아이디어",
    "광고-규정": "{s} 광고 문구 주의사항", "경쟁업체": "{s} 경쟁 업체 분석 방법", "예약": "{s} 네이버 예약 설정",
    "스마트콜": "{s} 전화 문의 늘리는 법", "성과-측정": "{s} 마케팅 효과 측정",
}

# 플랫폼 × 각도 — {p} = 플랫폼
PLATFORMS = ["네이버 플레이스", "스마트스토어", "쿠팡"]
PLAT_ANGLES = {
    "상위노출": "{p} 상위노출 방법", "순위-올리기": "{p} 순위 올리기", "순위-확인": "{p} 순위 확인 방법", "리뷰-늘리기": "{p} 리뷰 늘리기",
    "광고": "{p} 광고 하는 법", "광고-비용": "{p} 광고 비용", "트래픽": "{p} 트래픽 늘리기", "키워드": "{p} 키워드 찾는 법",
    "초보": "{p} 초보 판매자 가이드", "체크리스트": "{p} 운영 체크리스트", "실수": "{p} 초보가 하는 실수", "알고리즘": "{p} 노출 원리",
    "리워드": "{p} 리워드 광고란", "보장-주의": "{p} 상위노출 보장 업체 주의", "셀프-운영": "{p} 셀프 마케팅",
    "상품명": "{p} 상품명 작성법", "썸네일": "{p} 썸네일 만드는 법", "상세페이지": "{p} 상세페이지 구성", "가격": "{p} 가격 전략",
    "시즌": "{p} 시즌 키워드 준비", "판매-늘리기": "{p} 판매 늘리는 법", "리뷰-이벤트": "{p} 리뷰 이벤트 주의사항",
}
PLAT_SKIP = {"네이버 플레이스": {"상품명", "썸네일", "상세페이지", "가격"}}   # 매장 채널에 안 맞는 각도

# 일반 주제 (판매자 검색어 그대로)
GENERAL = [
    "네이버 플레이스 등록 방법", "네이버 플레이스 등록 비용", "스마트플레이스 가입 방법", "영수증 리뷰란", "네이버 영수증 리뷰 작성 방법",
    "네이버 검색광고 시작하는 법", "네이버 광고 관리 시스템 사용법", "플레이스 광고와 검색광고 차이", "키워드 검색량 보는 법",
    "네이버 키워드 도구 사용법", "리워드 광고란", "트래픽 광고란", "셀프 마케팅이란", "마케팅 대행사 계약 전 확인할 것",
    "상위노출 보장 업체 구별법", "가짜 리뷰 처벌", "표시광고법 광고 문구", "의료광고 심의 대상", "체험단 대가 표시 의무",
    "광고비 부가세 처리", "세금계산서 발행 방법", "소상공인 마케팅 지원 사업", "네이버 톡톡 설정 방법", "네이버 예약 등록 방법",
    "스마트콜 설정 방법", "블로그 마케팅 시작하는 법", "인스타그램 비즈니스 계정 전환", "당근 비즈프로필 만들기",
    "구글 비즈니스 프로필 등록", "카카오맵 장소 등록", "온라인 마케팅 예산 짜는 법", "마케팅 성과 측정 지표",
    "로컬 마케팅이란", "지역 키워드 고르는 법", "롱테일 키워드란", "검색 의도란", "경쟁 업체 분석 방법",
    "리뷰 답글 잘 쓰는 법", "악성 리뷰 신고 방법", "오픈 첫 달 마케팅", "비수기 매출 올리는 법", "단골 고객 관리 방법",
]


def _h(s):
    return hashlib.md5(s.encode()).hexdigest()


def build():
    items = []
    for bs in BIZ.values():
        for b in bs:
            for a, t in BIZ_ANGLES.items():
                items.append({"kw": t.format(s=b), "angle": a, "subject": b, "kind": "biz"})
    for p in PLATFORMS:
        for a, t in PLAT_ANGLES.items():
            if a in PLAT_SKIP.get(p, set()):
                continue
            items.append({"kw": t.format(p=p), "angle": a, "subject": p, "kind": "platform"})
    items += [{"kw": g, "angle": "general", "subject": "", "kind": "general"} for g in GENERAL]

    # 섞기: 일반·플랫폼 글을 앞쪽에 고르게, 업종 글은 같은 업종·같은 각도가 붙지 않게 해시 순
    head = sorted([i for i in items if i["kind"] != "biz"], key=lambda i: _h(i["kw"]))
    biz = sorted([i for i in items if i["kind"] == "biz"], key=lambda i: _h(i["kw"]))
    out, step = [], max(1, len(biz) // max(1, len(head)))
    hi = 0
    for n, it in enumerate(biz):
        if n % step == 0 and hi < len(head):
            out.append(head[hi]); hi += 1
        out.append(it)
    out += head[hi:]
    return out


def main():
    items = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(items, ensure_ascii=False, indent=0), encoding="utf-8")
    if not CURSOR.exists():
        CURSOR.write_text(json.dumps({"next": 0}, indent=1), encoding="utf-8")
    print(f"키워드 큐 {len(items)}개 → {OUT} (하루 10편이면 {len(items) // 10}일분)")


if __name__ == "__main__":
    main()
