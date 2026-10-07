"""SEO 품질 게이트 (2026-10-07).

    python scripts/seo_check.py --blog [파일...]   # 블로그 글 — 표준 라이브러리만 씀(클라우드 루틴에서 그대로 실행)
    python scripts/seo_check.py --learn            # /learn 기본 페이지 전부 (앱·DB 필요)

검사: 금지 표현(보장·과장) · 키워드 반복 · 본문 글자수(공백 제외) · 3-gram Jaccard 유사도 ≤ 35%
      · title ≤ 60자 · description 80~160자 · h1 1개 · frontmatter 형식(콜론·쉼표 값은 작은따옴표).
하나라도 실패하면 종료 코드 1 — 루틴은 이때 커밋하지 않는다.
"""
import re
import sys
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOG_DIR = ROOT / "content" / "blog"
MAX_JACCARD = 0.35
MIN_CHARS = {"blog": 1500, "bizhub": 1100, "bizangle": 1100, "regionbiz": 1000, "regionhub": 450, "topic": 900, "storecat": 1050}

# 단정적 보장·과장. "보장 업체를 경계하라" 같은 부정 문맥은 걸리지 않게 '보장합니다/드립니다' 형태만.
BANNED = [r"보장\s?합니다", r"보장해\s?드(립|려)", r"보장\s?드립", r"확실히\s?(올라|오릅|상승)", r"무조건\s?(상위|1위|노출|올)",
          r"100\s?%\s?(상위|노출|효과|보장)", r"반드시\s?(상위|1위)", r"최저가\s?보장", r"환불\s?보장",
          r"리뷰\s?(작업|조작)\s?(해|가능)", r"가짜\s?리뷰\s?(로|를)\s?(늘|만들)", r"어뷰징\s?(하세요|추천)"]


def strip_ws(s):
    return re.sub(r"\s+", "", s)


def grams(text, n=3):
    w = re.findall(r"[가-힣A-Za-z0-9]+", text)
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def banned_hits(text):
    return [p for p in BANNED if re.search(p, text)]


def stuffing(text, kw):
    """키워드(공백 무시)가 본문 1,000자당 몇 번 나오는지. 10 초과면 반복으로 본다."""
    if not kw:
        return 0.0
    body = strip_ws(text)
    return body.count(strip_ws(kw)) * 1000 / max(1, len(body))


# ------------------------------------------------------------------ blog (stdlib only)
def parse_front(raw):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, re.S)
    if not m:
        return None, raw, ["frontmatter(---) 가 없습니다"]
    meta, errs = {}, []
    for i, line in enumerate(m.group(1).splitlines(), 1):
        if not line.strip():
            continue
        if ":" not in line:
            errs.append(f"frontmatter {i}행 형식 오류: {line!r}")
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        quoted = len(v) >= 2 and v[0] == v[-1] and v[0] in "'\""
        if not quoted and (":" in v or "," in v or "#" in v):
            errs.append(f"frontmatter '{k.strip()}' 값에 콜론/쉼표가 있어 작은따옴표로 감싸야 합니다")
        meta[k.strip()] = v[1:-1].replace("''", "'") if quoted else v
    return meta, m.group(2), errs


def check_blog(files):
    files = files or sorted(BLOG_DIR.glob("*.md"))
    every = sorted(BLOG_DIR.glob("*.md"))
    fails, texts = [], {}
    for f in every:
        meta, body, _ = parse_front(f.read_text(encoding="utf-8"))
        texts[f.name] = grams(body)
    for f in files:
        f = Path(f)
        raw = f.read_text(encoding="utf-8")
        meta, body, errs = parse_front(raw)
        meta = meta or {}
        if not re.fullmatch(r"[0-9a-z가-힣\-]+", f.stem):
            errs.append("파일명(slug)은 소문자·숫자·한글·하이픈만")
        for k in ("title", "description", "date", "keywords", "category"):
            if not meta.get(k):
                errs.append(f"frontmatter '{k}' 없음")
        if meta.get("title") and len(meta["title"]) > 60:
            errs.append(f"title {len(meta['title'])}자 (60자 이내)")
        if meta.get("description") and not 80 <= len(meta["description"]) <= 160:
            errs.append(f"description {len(meta['description'])}자 (80~160자)")
        if meta.get("date") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", meta["date"]):
            errs.append("date 는 YYYY-MM-DD")
        if re.search(r"^#\s", body, re.M):
            errs.append("본문에 h1(# ) 금지 — 제목이 h1 입니다. ## / ### 만")
        if not re.search(r"^##\s", body, re.M):
            errs.append("소제목(##)이 없습니다")
        n = len(strip_ws(re.sub(r"[#>*`|\-]", "", body)))
        if n < MIN_CHARS["blog"]:
            errs.append(f"본문 {n}자 (공백 제외 {MIN_CHARS['blog']}자 이상)")
        hits = banned_hits(body + meta.get("title", "") + meta.get("description", ""))
        if hits:
            errs.append(f"금지 표현: {hits}")
        main_kw = (meta.get("keywords") or "").split(",")[0].strip()
        st = stuffing(body, main_kw)
        if st > 10:
            errs.append(f"키워드 '{main_kw}' 반복 과다 ({st:.1f}회/1000자)")
        g = grams(body)
        worst = max(((jaccard(g, t), name) for name, t in texts.items() if name != f.name), default=(0, ""))
        if worst[0] > MAX_JACCARD:
            errs.append(f"유사도 {worst[0]:.0%} — {worst[1]} 와 너무 비슷합니다")
        print(("FAIL " if errs else "OK   ") + f.name + ("" if not errs else "\n     - " + "\n     - ".join(errs)))
        if errs:
            fails.append(f.name)
    return fails


# ------------------------------------------------------------------ learn pages
def prose(page):
    parts = [page["lead"]]
    for s in page["sections"]:
        parts += s.get("p") or []
        parts += s.get("list") or []
        parts += [m["q"] + " " + m["a"] for m in s.get("sub") or []]
    parts += [f["q"] + " " + f["a"] for f in page["faq"]]
    return " ".join(parts)


def full_text(page):
    """글자수 판정용 — 실데이터 표(연관 키워드·지역 목록)까지 포함한 화면 텍스트."""
    extra = []
    for s in page["sections"]:
        extra += [r["k"] for r in s.get("related") or []]
        extra += [n for n, _, _ in s.get("itemlist") or []]
    return prose(page) + " " + " ".join(extra)


def check_learn():
    sys.path.insert(0, str(ROOT))
    from app import create_app
    from app.blueprints.seo import _prices
    from app.services import seo_pages
    app = create_app()
    app.config["TESTING"] = True
    fails = []
    with app.test_request_context():
        prices = _prices()
        pages = [seo_pages.build(slug, prices) for _, _, slug in seo_pages.all_paths()]
    tc = app.test_client()
    by_group = {}
    for p in pages:
        errs = []
        text = prose(p)
        n = len(strip_ws(full_text(p)))
        if n < MIN_CHARS[p["kind"]]:
            errs.append(f"본문 {n}자 < {MIN_CHARS[p['kind']]}")
        if len(p["title"]) > 60:
            errs.append(f"title {len(p['title'])}자")
        if not 80 <= len(p["desc"]) <= 160:
            errs.append(f"description {len(p['desc'])}자")
        if banned_hits(text):
            errs.append(f"금지 표현 {banned_hits(text)}")
        if stuffing(text, p["kw"]) > 10:
            errs.append(f"키워드 반복 {stuffing(text, p['kw']):.1f}/1000자")
        if errs:
            fails.append((p["path"], errs))
        # 서로 가장 닮기 쉬운 묶음: 같은 종류 + (같은 업종 / 같은 지역 / 같은 각도)
        k, slug = p["kind"], p["slug"]
        if k in ("bizhub", "topic", "storecat", "regionhub"):
            by_group.setdefault((k, "all"), []).append(p)
        if k == "bizangle":
            by_group.setdefault((k, slug.split("-", 1)[1]), []).append(p)   # 같은 각도, 다른 업종
            by_group.setdefault((k, slug.split("-", 1)[0]), []).append(p)   # 같은 업종, 다른 각도
        if k == "regionbiz":
            by_group.setdefault((k, p["region"]), []).append(p)
            by_group.setdefault((k, p["kw"].split(" ", 1)[1]), []).append(p)
    # 유사도 — 가장 닮기 쉬운 묶음(같은 업종 / 같은 지역 / 쇼핑) 안에서 전부 비교
    worst = (0, None, None)
    gcache = {}
    for group in by_group.values():
        for a, b in combinations(group, 2):
            ga = gcache.setdefault(a["path"], grams(prose(a)))
            gb = gcache.setdefault(b["path"], grams(prose(b)))
            j = jaccard(ga, gb)
            if j > worst[0]:
                worst = (j, a["path"], b["path"])
            if j > MAX_JACCARD:
                fails.append((a["path"], [f"유사도 {j:.0%} vs {b['path']}"]))
    # 렌더 검사 — 상태 코드·h1 개수 (표본)
    for path, kind, _ in seo_pages.all_paths()[::25]:
        h = tc.get(path)
        if h.status_code != 200 or h.get_data(as_text=True).count("<h1") != 1:
            fails.append((path, [f"status {h.status_code} / h1 {h.get_data(as_text=True).count('<h1')}"]))
    print(f"페이지 {len(pages)}개 · 최대 유사도 {worst[0]:.1%} ({worst[1]} ↔ {worst[2]})")
    from collections import Counter
    kinds = {path: k for path, k, _ in seo_pages.all_paths()}
    summary = Counter((kinds.get(path, "?"), re.sub(r"[0-9.,%]+", "N", e.split(" vs ")[0])) for path, errs in fails for e in errs)
    for (k, e), n in summary.most_common(20):
        print(f"  {n:5}  {k:10} {e}")
    for path, errs in fails[:15]:
        print("FAIL", path, "; ".join(errs))
    print(f"실패 {len(fails)}건")
    return fails


def fix_learn(rounds=8):
    """유사도로 걸린 페이지의 salt 를 올려 문장 조합을 바꾼다 → data/seo/salt.json. 통과할 때까지 반복."""
    import json
    sys.path.insert(0, str(ROOT))
    from app.services import seo_pages
    path = ROOT / "data" / "seo" / "salt.json"
    for r in range(rounds):
        fails = check_learn()
        sim = sorted({p for p, errs in fails if any(e.startswith("유사도") for e in errs)})
        if not sim:
            return fails
        salts = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        for p in sim:
            slug = p.strip("/").split("/", 1)[1]
            salts[slug] = salts.get(slug, 0) + 1
        path.write_text(json.dumps(salts, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
        seo_pages.salts.cache_clear()
        print(f"[fix {r + 1}] salt 조정 {len(sim)}개")
    return check_learn()


if __name__ == "__main__":
    if "--learn" in sys.argv:
        sys.exit(1 if (fix_learn() if "--fix" in sys.argv else check_learn()) else 0)
    files = [a for a in sys.argv[1:] if not a.startswith("--")]
    bad = check_blog(files)
    print(f"\n{'통과' if not bad else f'{len(bad)}편 실패'}")
    sys.exit(1 if bad else 0)
