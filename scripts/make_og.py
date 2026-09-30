"""OG 공유 이미지(app/static/img/og.png, 1200x630)를 만든다.

    python scripts/make_og.py

카카오톡·문자·슬랙에 링크를 붙였을 때 뜨는 그림이다. 브랜드 글자는 APP_NAME(.env) 을 읽고,
문구는 constants.SEO_TAGLINE 을 쓴다 — 서비스명·카피가 바뀌면 다시 돌리면 된다.
한글 서체는 Windows 맑은 고딕(malgunbd.ttf) → 없으면 Noto Sans KR 순으로 찾는다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from app.config import Config  # noqa: E402
from app.constants import SEO_DOMAIN_KO, SEO_SUB, SEO_TAGLINE  # noqa: E402

OUT = ROOT / "app" / "static" / "img" / "og.png"
SYM = ROOT / "app" / "static" / "img" / "logo-sym.png"     # 흰 심볼 (사이드바용)
W, H = 1200, 630
FONT_CANDIDATES = [
    "C:/Windows/Fonts/malgunbd.ttf", "C:/Windows/Fonts/malgun.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]


def font(size):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    raise SystemExit("한글 서체를 찾지 못했습니다. FONT_CANDIDATES 에 경로를 추가하세요.")


def gradient():
    """사이드바 보라(#5D50C7) → 액센트(#6C5CE7) 대각 그라데이션 — 앱과 같은 색."""
    a, b = (0x5D, 0x50, 0xC7), (0x7C, 0x6C, 0xF0)
    im = Image.new("RGB", (W, H))
    px = im.load()
    for y in range(H):
        for x in range(W):
            t = (x / W * 0.6 + y / H * 0.4)
            px[x, y] = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return im


def main():
    im = gradient()
    d = ImageDraw.Draw(im)

    # 심볼 — 왼쪽 위, 브랜드 글자와 한 줄
    sym = Image.open(SYM).convert("RGBA")
    sh = 86
    sym = sym.resize((round(sym.width * sh / sym.height), sh), Image.LANCZOS)
    x0, y0 = 96, 92
    im.paste(sym, (x0, y0), sym)
    brand = Config.APP_NAME
    f_brand = font(64)
    d.text((x0 + sym.width + 22, y0 + sh // 2), brand, font=f_brand, fill="white", anchor="lm")

    # 카피 — 두 줄 큰 글자
    f_head = font(72)
    y = 250
    for line in SEO_TAGLINE.split("\n"):
        d.text((x0, y), line, font=f_head, fill="white")
        y += 92
    # 부제 — 오른쪽 여백(96px) 안에 들어올 때까지 글자를 줄인다
    size = 30
    while size > 20 and d.textlength(SEO_SUB, font=font(size)) > W - x0 - 96:
        size -= 1
    d.text((x0, y + 18), SEO_SUB, font=font(size), fill=(0xE7, 0xE3, 0xFB))

    # 하단 — 도메인 (한글) + 얇은 선
    d.line([(x0, 540), (W - 96, 540)], fill=(255, 255, 255, 60), width=1)
    d.text((x0, 560), SEO_DOMAIN_KO, font=font(26), fill=(0xE7, 0xE3, 0xFB))
    d.text((W - 96, 560), "셀프서브 트래픽 광고 플랫폼", font=font(26), fill=(0xE7, 0xE3, 0xFB), anchor="ra")

    im.save(OUT, "PNG", optimize=True)
    print(f"저장: {OUT} ({OUT.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
