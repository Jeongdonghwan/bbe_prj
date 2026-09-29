"""deploy/banners/ 의 이미지를 배너로 등록한다 (몇 번 돌려도 같은 결과).

    python scripts/import_banners.py            # 무엇이 바뀌는지 보여만 준다
    python scripts/import_banners.py --yes      # 실제로 반영

어드민 배너 관리에서 하나씩 올려도 되는 일이지만, 운영 서버에 파일을 옮길 통로가
git 뿐이라 이 경로를 만들었다. 원본은 deploy/banners/ 에 그대로 두고, 화면에 쓸
사본만 static/uploads/banners/ 에 만든다.

화면이 쓰는 칸 (components.css): 높이만 px 고정이고 가로는 화면 폭을 따라간다.
  그리드(.adgrid img)    높이 112px (모바일 84px) · 한 줄 4칸 → 1280px 창 2.4:1 ~ 1920px 창 3.8:1
  슬라이드(.sb-track img) 높이 200px (모바일 130px) · 한 장 전폭 → 5.7:1 ~ 8.7:1

**디자이너에게 줄 제작 규격** (이 비율로 만들면 아무 보정 없이 꽉 찬다):
  그리드   1200 x 316  — 글자·로고는 가운데 760px 안에(좁은 창에서 좌우 220px씩 잘려도 안전)
  슬라이드 2440 x 280  — 글자·로고는 가운데 1600px 안에(좁은 창에서 좌우 420px씩 잘려도 안전)
  배경은 좌우 끝까지 이어지는 단색·그라데이션·패턴으로. 좌우 끝에 요소를 두지 말 것.

규격과 다른 그림(지금 받은 5장이 전부 2.5~6:1 로 칸보다 좁다)은 두 단계로 맞춘다:
  1) BANNERS 의 crop(top, bottom) 비율만큼 위아래 배경 여백을 잘라 비율을 칸에 가깝게 만든다.
     글자를 자르지 않는 선까지만 — 값은 그림을 보고 손으로 정했다.
  2) 그래도 남는 좌우 자리는 그림 가장자리 색으로 채운다(fit_to_box). 검정·흰색 배경이면
     티가 안 나고, 그라데이션이면 살짝 보인다 — 이건 그림을 규격대로 다시 받아야 없어진다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageFilter  # noqa: E402

from app import create_app  # noqa: E402
from app.db import execute, query_one  # noqa: E402

SRC = ROOT / "deploy" / "banners"
DST = ROOT / "app" / "static" / "uploads" / "banners"

# 화면이 그리는 비율 — 이 값으로 잘림 정도를 계산한다.
# 칸은 목업대로 높이만 고정(112px/200px)이라 화면 폭에 따라 비율이 변한다:
#   그리드 1280px 창 2.4:1 ~ 1920px 창 3.8:1,  슬라이드 5.7:1 ~ 8.7:1
# 캔버스는 그중 **가장 넓은 비율**로 만들고 그림은 캔버스 높이를 꽉 채운다. 그러면 cover 가
# 어느 폭에서도 위아래는 절대 안 자르고(그림이 항상 온전히 보임) 좁은 창에서만 좌우 여백을
# 잘라낸다. 여백은 흐린 확대본이 아니라 그림 가장자리 색이라 배너가 그냥 넓어 보인다.
BOX = {"grid": (1200, 316), "slide": (2440, 280)}
MAX_W = {"grid": 1200, "slide": 2440}  # = BOX 가로

BANNERS = [
    # (파일, zone, sort, 제목, 링크, (위 crop 비율, 아래 crop 비율))
    # crop 은 글자·로고가 없는 배경 여백만 — 원본을 보고 정한 값이라 그림을 바꾸면 다시 봐야 한다.
    ("grid1.jpg",  "grid",  1, "효율 검증 완료 리워드",      "https://open.kakao.com/o/sADNDLPi", (0.09, 0.05)),
    ("grid2.jpg",  "grid",  2, "리워드 미라지 · 네이버 쇼핑", "https://open.kakao.com/o/sGEEbBHi", (0.04, 0.10)),
    ("grid3.png",  "grid",  3, "카페 침투 · 맘카페 핫딜",     "https://open.kakao.com/o/s6Kb8mLi", (0.05, 0.10)),
    ("slide1.png", "slide", 1, "리워드 실루엣 · 총판 대행 셀러 모집", "https://open.kakao.com/o/s6Kb8mLi", (0.26, 0.31)),
    ("slide2.png", "slide", 2, "Hotsource · 마케팅 프로그램 유통채널",
     "https://xn--9l4b2t505b.com/shop/?ib_sso=skip", (0.09, 0.10)),
]


def crop_margins(im, crop):
    """위아래 배경 여백을 잘라 그림 비율을 칸에 가깝게 만든다. 좌우는 건드리지 않는다."""
    top, bottom = crop
    h = im.height
    return im.crop((0, round(h * top), im.width, h - round(h * bottom)))


def crop_note(w, h, zone):
    """가장 좁은 창(그리드 2.4:1 / 슬라이드 5.7:1)에서도 그림이 온전히 보이는지."""
    tw, th = BOX[zone]
    narrow = {"grid": 2.4, "slide": 5.7}[zone]
    fs = min(th / h, tw / w)
    art_w = w * fs / tw                             # 캔버스 가로 중 그림이 차지하는 비율
    visible = narrow / (tw / th)                    # 가장 좁은 창에서 보이는 캔버스 가로 비율
    if art_w <= visible + 0.01:
        return f"그림 {art_w * 100:.0f}% · 항상 온전"
    return f"그림 {art_w * 100:.0f}% · 좁은 창 좌우 {(1 - visible / art_w) * 100:.0f}% 잘림"
def _flatten(im):
    """투명 PNG 를 흰 배경 위에 얹어 JPEG 로 저장할 수 있게 한다."""
    if im.mode in ("RGBA", "P", "LA"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        rgba = im.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    return im.convert("RGB")


def _edge_color(im):
    """좌우 가장자리 픽셀의 중간값 — 여백을 이 색으로 채우면 배너가 그냥 넓어진 것처럼 보인다."""
    w, h = im.size
    strip = max(1, w // 50)
    px = list(im.crop((0, 0, strip, h)).get_flattened_data()) + list(im.crop((w - strip, 0, w, h)).get_flattened_data())
    px.sort()
    return px[len(px) // 2]


def fit_to_box(im, zone):
    """칸 높이를 꽉 채우고 좌우 남는 자리는 가장자리 색으로 채운다. 그림은 절대 자르지 않는다."""
    tw, th = BOX[zone]
    fs = min(th / im.height, tw / im.width)        # 보통은 높이 기준, 아주 넓은 그림만 가로 기준
    fg = im.resize((max(1, round(im.width * fs)), max(1, round(im.height * fs))), Image.LANCZOS)
    canvas = Image.new("RGB", (tw, th), _edge_color(im))
    canvas.paste(fg, ((tw - fg.width) // 2, (th - fg.height) // 2))
    return canvas


def make_web_copy(src, dst, zone, crop):
    """원본은 두고 화면용 사본만 만든다. 여백을 잘라 칸 비율에 맞추고 JPEG 로 줄인다."""
    im = fit_to_box(crop_margins(_flatten(Image.open(src)), crop), zone)
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, "JPEG", quality=86, optimize=True, progressive=True)
    return im.size, dst.stat().st_size


def main():
    apply = "--yes" in sys.argv
    missing = [b[0] for b in BANNERS if not (SRC / b[0]).exists()]
    if missing:
        print("원본이 없습니다:", ", ".join(missing))
        return 1

    app = create_app()
    with app.app_context():
        print(f"{'파일':14}{'zone':7}{'원본':13}{'표시':26}{'사본':13}제목")
        for name, zone, sort, title, link, crop in BANNERS:
            src = SRC / name
            w, h = Image.open(src).size
            ch = h - round(h * crop[0]) - round(h * crop[1])   # 여백을 잘라낸 뒤의 높이
            dst = DST / f"{zone}{sort}.jpg"
            url = f"/static/uploads/banners/{dst.name}"
            note = crop_note(w, ch, zone)
            if apply:
                (nw, nh), size = make_web_copy(src, dst, zone, crop)
                row = query_one("SELECT id FROM banners WHERE image_url = %s", [url])
                if row:
                    execute("""UPDATE banners SET title=%s, link=%s, zone=%s, sort=%s, is_active=1
                               WHERE id=%s""", [title, link, zone, sort, row["id"]])
                else:
                    execute("""INSERT INTO banners (image_url, link, title, zone, sort, is_active)
                               VALUES (%s,%s,%s,%s,%s,1)""", [url, link, title, zone, sort])
                shown = f"{nw}x{nh} {size // 1024}KB"
            else:
                shown = "(드라이런)"
            print(f"{name:14}{zone:7}{f'{w}x{h}':13}{note:26}{shown:13}{title}")

        if not apply:
            print("\n실제로 반영하려면: python scripts/import_banners.py --yes")
            return 0

        # 시드가 심어둔 "테스트 N" 배너는 같이 내린다 (지우지는 않는다).
        n = execute("UPDATE banners SET is_active = 0 WHERE title LIKE '테스트 %%' OR title LIKE '슬라이드 테스트 %%'",
                    rowcount=True)
        print(f"\n반영 완료. 테스트 배너 {n}건은 비노출로 내렸습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
