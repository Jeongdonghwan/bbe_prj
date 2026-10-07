"""블로그 — content/blog/*.md (2026-10-07). 클라우드 루틴이 글을 커밋하고 서버가 git pull 하면 바로 보인다.

파일 형식 (frontmatter 는 한 줄에 key: value, 콜론·쉼표가 든 값은 작은따옴표로 감싼다):

    ---
    title: '플레이스 셀프 세팅, 처음 할 때 순서'
    description: '...80~160자...'
    date: 2026-10-08
    keywords: '플레이스 셀프 세팅, 네이버 플레이스'
    category: 플레이스
    ---
    본문(마크다운). h1 은 쓰지 않는다 — 제목이 h1 이다. ## / ### 만.

slug = 파일명(확장자 제외). 날짜가 오늘보다 뒤인 글은 아직 보이지 않는다(예약 발행).
"""
import re
from datetime import date
from pathlib import Path

import markdown as md

from .content_service import sanitize

DIR = Path(__file__).resolve().parent.parent.parent / "content" / "blog"
_CACHE = {}   # {path: (mtime, post)}


def parse_front(text):
    """(meta, body). 값의 바깥 작은/큰따옴표만 벗긴다 — YAML 전체를 쓰지 않는 단순 형식."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
    if not m:
        return None, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1].replace("''", "'")
        meta[k.strip()] = v
    return meta, m.group(2)


def _read(path):
    mt = path.stat().st_mtime
    hit = _CACHE.get(path)
    if hit and hit[0] == mt:
        return hit[1]
    meta, body = parse_front(path.read_text(encoding="utf-8"))
    if not meta or not meta.get("title"):
        return None
    try:
        d = date.fromisoformat(meta.get("date", ""))
    except ValueError:
        return None
    html = sanitize(md.markdown(body, extensions=["tables", "sane_lists"]))
    post = {"slug": path.stem, "title": meta["title"], "desc": meta.get("description", ""), "date": d,
            "updated": date.fromtimestamp(mt), "category": meta.get("category", ""),
            "keywords": meta.get("keywords", ""), "html": html, "path": f"/blog/{path.stem}/"}
    _CACHE[path] = (mt, post)
    return post


def posts():
    """공개된 글, 최신순."""
    if not DIR.exists():
        return []
    today = date.today()
    out = [p for p in (_read(f) for f in DIR.glob("*.md")) if p and p["date"] <= today]
    return sorted(out, key=lambda p: (p["date"], p["slug"]), reverse=True)


def get(slug):
    f = DIR / f"{slug}.md"
    if not f.exists() or "/" in slug or "\\" in slug:
        return None
    p = _read(f)
    return p if p and p["date"] <= date.today() else None
