"""deploy/banners/ 의 이미지를 배너로 등록한다 (몇 번 돌려도 같은 결과).

    python scripts/import_banners.py            # 무엇이 바뀌는지 보여만 준다
    python scripts/import_banners.py --yes      # 실제로 반영

어드민 배너 관리에서 하나씩 올려도 되는 일이지만, 운영 서버에 파일을 옮길 통로가
git 뿐이라 이 경로를 만들었다. 원본은 deploy/banners/ 에 그대로 두고, 화면에 쓸
사본만 static/uploads/banners/ 에 만든다.

화면이 쓰는 크기 (components.css):
  그리드(.adgrid img)  height 112px · 4열 → 1220px 기준 약 296x112 (2.64:1), object-fit: cover
  슬라이드(.sb-track img) height 200px · 전체폭 → 1220x200 (6.1:1), object-fit: cover
비율이 다르면 잘린다. 잘리는 정도를 아래 표로 찍어주니 확인하고 쓸 것.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from app import create_app  # noqa: E402
from app.db import execute, query_one  # noqa: E402

SRC = ROOT / "deploy" / "banners"
DST = ROOT / "app" / "static" / "uploads" / "banners"

# 화면이 그리는 비율 — 이 값으로 잘림 정도를 계산한다.
BOX = {"grid": (296, 112), "slide": (1220, 200)}
# 저장할 최대 가로 (2배 해상도까지만. 그 이상은 용량만 먹는다).
MAX_W = {"grid": 1200, "slide": 2440}

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
    """이 이미지가 화면에서 얼마나 잘리는지 한 줄로."""
    bw, bh = BOX[zone]
    src, box = w / h, bw / bh
    if abs(src - box) < 0.05:
        return "거의 안 잘림"
    if src > box:                       # 원본이 더 넓다 → 좌우가 잘린다
        keep = box / src
        return f"좌우 {(1 - keep) * 100:.0f}% 잘림"
    keep = src / box                    # 원본이 더 높다 → 위아래가 잘린다
    return f"위아래 {(1 - keep) * 100:.0f}% 잘림"


def make_web_copy(src, dst, zone):
    """원본은 두고 화면용 사본만 만든다. 큰 PNG 는 JPEG 로 줄인다."""
    im = Image.open(src)
    w, h = im.size
    limit = MAX_W[zone]
    if w > limit:
        im = im.resize((limit, round(h * limit / w)), Image.LANCZOS)
    if im.mode in ("RGBA", "P", "LA"):
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
        im = bg
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.convert("RGB").save(dst, "JPEG", quality=86, optimize=True, progressive=True)
    return im.size, dst.stat().st_size


def main():
    apply = "--yes" in sys.argv
    missing = [b[0] for b in BANNERS if not (SRC / b[0]).exists()]
    if missing:
        print("원본이 없습니다:", ", ".join(missing))
        return 1

    app = create_app()
    with app.app_context():
        print(f"{'파일':14}{'zone':7}{'원본':13}{'화면에서':16}{'사본':13}제목")
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
