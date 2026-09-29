"""deploy/banners/ 의 이미지를 배너로 등록한다 (몇 번 돌려도 같은 결과).

    python scripts/import_banners.py            # 무엇이 바뀌는지 보여만 준다
    python scripts/import_banners.py --yes      # 실제로 반영

어드민 배너 관리에서 하나씩 올려도 되는 일이지만, 운영 서버에 파일을 옮길 통로가
git 뿐이라 이 경로를 만들었다. 원본은 deploy/banners/ 에 그대로 두고, 화면에 쓸
사본만 static/uploads/banners/ 에 만든다.

화면이 쓰는 비율 (components.css, aspect-ratio 로 고정 — 화면 폭이 변해도 그대로다):
  그리드(.adgrid img)    높이 112px 고정 (모바일 84px)
  슬라이드(.sb-track img) 높이 200px 고정 (모바일 130px)
  제작 권장: 그리드 1200x400 · 슬라이드 2440x350 — 본 내용은 가운데 80% 안에.
비율이 다른 이미지는 **잘라내지 않는다**. 통째로 넣고 남는 여백을 그 이미지를 흐리게 깐
배경으로 채운다(letterbox). 그래서 어떤 비율을 올려도 내용이 사라지지 않는다.
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
# 그래서 사본은 그 중간 비율의 캔버스로 만들고, 본 그림은 캔버스 가운데 SAFE 비율 안에 둔다.
# 어느 폭에서 잘려도 잘리는 건 흐린 여백이고 본 그림은 남는다.
BOX = {"grid": (1200, 400), "slide": (2440, 349)}
SAFE = 0.82
# 저장할 최대 가로 (2배 해상도까지만. 그 이상은 용량만 먹는다).
MAX_W = {"grid": 1200, "slide": 2440}  # = BOX 가로

BANNERS = [
    # (파일, zone, sort, 제목, 링크)
    ("grid1.jpg",  "grid",  1, "효율 검증 완료 리워드",      "https://open.kakao.com/o/sADNDLPi"),
    ("grid2.jpg",  "grid",  2, "리워드 미라지 · 네이버 쇼핑", "https://open.kakao.com/o/sGEEbBHi"),
    ("grid3.png",  "grid",  3, "카페 침투 · 맘카페 핫딜",     "https://open.kakao.com/o/s6Kb8mLi"),
    ("slide1.png", "slide", 1, "리워드 실루엣 · 총판 대행 셀러 모집", "https://open.kakao.com/o/s6Kb8mLi"),
    ("slide2.png", "slide", 2, "Hotsource · 마케팅 프로그램 유통채널",
     "https://xn--9l4b2t505b.com/shop/?ib_sso=skip"),
]


def crop_note(w, h, zone):
    """본 그림이 캔버스에서 차지하는 비율 — 100% 에 가까울수록 여백이 적다."""
    tw, th = BOX[zone]
    fs = min(tw * SAFE / w, th * SAFE / h)
    return f"그림 {w * fs / tw * 100:.0f}% x {h * fs / th * 100:.0f}%"


def _flatten(im):
    """투명 PNG 를 흰 배경 위에 얹어 JPEG 로 저장할 수 있게 한다."""
    if im.mode in ("RGBA", "P", "LA"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        rgba = im.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    return im.convert("RGB")


def fit_to_box(im, zone):
    """칸 비율 범위 어디서도 본 그림이 잘리지 않게 캔버스에 앉힌다.

    캔버스(BOX)는 화면 폭에 따라 변하는 칸 비율의 중간값. 본 그림은 캔버스의 SAFE(82%)
    안에 통째로 들어가고, 남는 자리는 같은 그림의 흐린 확대본으로 채운다. object-fit: cover
    가 좌우/위아래를 잘라도 그 자리는 여백이지 그림이 아니다.
    """
    tw, th = BOX[zone]
    # 배경: 캔버스를 꽉 채우도록 잘라 흐리게
    cs = max(tw / im.width, th / im.height)
    bg = im.resize((max(1, round(im.width * cs)), max(1, round(im.height * cs))), Image.LANCZOS)
    l, t = (bg.width - tw) // 2, (bg.height - th) // 2
    bg = bg.crop((l, t, l + tw, t + th)).filter(ImageFilter.GaussianBlur(radius=max(10, tw // 50)))
    # 앞: 안전 영역 안에 통째로
    sw, sh = tw * SAFE, th * SAFE
    fs = min(sw / im.width, sh / im.height)
    fg = im.resize((max(1, round(im.width * fs)), max(1, round(im.height * fs))), Image.LANCZOS)
    bg.paste(fg, ((tw - fg.width) // 2, (th - fg.height) // 2))
    return bg


def make_web_copy(src, dst, zone):
    """원본은 두고 화면용 사본만 만든다. 칸 비율에 맞추고 JPEG 로 줄인다."""
    im = fit_to_box(_flatten(Image.open(src)), zone)
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
        print(f"{'파일':14}{'zone':7}{'원본':13}{'캔버스 점유':16}{'사본':13}제목")
        for name, zone, sort, title, link in BANNERS:
            src = SRC / name
            w, h = Image.open(src).size
            dst = DST / f"{zone}{sort}.jpg"
            url = f"/static/uploads/banners/{dst.name}"
            note = crop_note(w, h, zone)
            if apply:
                (nw, nh), size = make_web_copy(src, dst, zone)
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
            print(f"{name:14}{zone:7}{f'{w}x{h}':13}{note:16}{shown:13}{title}")

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
