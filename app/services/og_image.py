"""페이지별 공유 이미지(og:image) 1200×630 — /og/learn/<slug>.png · /og/blog/<slug>.png (2026-11-04).

예전엔 모든 페이지가 같은 og.png 를 써서 네이버·카톡 썸네일이 전부 똑같았다. 페이지 h1(키워드)과 핵심 숫자 하나,
브랜드를 그린다. 네이버 웹문서 결과는 og:image 를 정사각형으로 잘라 보여주므로 글자는 가운데 630×630 안에 둔다.
처음 요청 때 그리고 instance/og/ 에 저장해 다음부터는 파일을 그대로 준다 (본문이 바뀌면 키가 바뀐다).
"""
import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
SAFE = 600                     # 가운데 정사각 안전영역 폭
ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "static" / "fonts" / "Pretendard-Bold.otf"
SYM = ROOT / "static" / "img" / "logo-sym.png"
CACHE = ROOT.parent / "instance" / "og"
# 브랜드 보라 (tokens --accent 계열) · 글자는 흰색
BG_TOP, BG_BOT = (108, 92, 231), (74, 62, 196)


def _font(size):
    return ImageFont.truetype(str(FONT), size)


def _wrap(draw, text, font, width):
    """공백 단위 줄바꿈 — 한 줄이 width 를 넘으면 다음 줄로. 단어 하나가 너무 길면 글자 단위."""
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = word
        while draw.textlength(cur, font=font) > width and len(cur) > 1:   # 아주 긴 단어
            i = len(cur)
            while i > 1 and draw.textlength(cur[:i], font=font) > width:
                i -= 1
            lines.append(cur[:i]); cur = cur[i:]
    if cur:
        lines.append(cur)
    return lines


def render(title, sub, brand):
    img = Image.new("RGB", (W, H), BG_TOP)
    d = ImageDraw.Draw(img)
    for y in range(H):   # 세로 그라데이션
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOT)))
    x0 = (W - SAFE) // 2
    # 제목 — 길이에 맞춰 글자 크기를 줄인다 (최대 3줄)
    for size in (76, 68, 60, 52, 46):
        f = _font(size)
        lines = _wrap(d, title, f, SAFE)
        if len(lines) <= 3:
            break
    lines = lines[:3]
    lh = int(size * 1.22)
    fs = _font(34)
    block = lh * len(lines) + (24 + 46 if sub else 0)
    y = (H - block) // 2 - 20
    for ln in lines:
        d.text((W // 2, y), ln, font=f, fill="white", anchor="ma")
        y += lh
    if sub:
        y += 24
        d.text((W // 2, y), sub, font=fs, fill=(226, 222, 249), anchor="ma")
    # 브랜드 — 아래 가운데 (심볼 + 이름)
    fb = _font(30)
    bw = d.textlength(brand, font=fb)
    try:
        sym = Image.open(SYM).convert("RGBA")
        sh = 40
        sym = sym.resize((int(sym.width * sh / sym.height), sh), Image.LANCZOS)
        total = sym.width + 12 + bw
        sx = int((W - total) / 2)
        img.paste(sym, (sx, H - 92), sym)
        d.text((sx + sym.width + 12, H - 92 + sh // 2), brand, font=fb, fill="white", anchor="lm")
    except OSError:
        d.text((W // 2, H - 72), brand, font=fb, fill="white", anchor="mm")
    _ = x0
    return img


def path_for(kind, slug, title, sub, brand):
    """캐시 파일 — 없으면 그려서 저장. 제목·부제·브랜드가 바뀌면 키가 바뀐다."""
    key = hashlib.md5(f"{kind}|{slug}|{title}|{sub}|{brand}|v1".encode()).hexdigest()
    p = CACHE / kind / f"{key}.png"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        render(title, sub, brand).save(tmp, "PNG", optimize=True)
        tmp.replace(p)
    return p
