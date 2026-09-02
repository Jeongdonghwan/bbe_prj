"""Idempotent DB/data migrations. Runs on every deploy (scripts/deploy.sh).

Safe to run repeatedly: only applies what is missing.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402

from app.config import Config  # noqa: E402


def font(size):
    from PIL import ImageFont
    for p in (r"C:\Windows\Fonts\arialbd.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def ensure_banner_images():
    """Placeholder AD images (uploads/ is gitignored, so servers must generate their own)."""
    from PIL import Image, ImageDraw
    d = ROOT / "app" / "static" / "uploads" / "banners"
    d.mkdir(parents=True, exist_ok=True)
    made = 0
    f_grid, f_slide = font(96), font(110)
    for i in range(1, 9):
        p = d / f"t{i}.png"
        if p.exists():
            continue
        im = Image.new("RGB", (1200, 300), (243, 244, 246))
        dr = ImageDraw.Draw(im)
        dr.rectangle([3, 3, 1196, 296], outline=(209, 213, 219), width=6)
        bb = dr.textbbox((0, 0), "AD", font=f_grid)
        dr.text(((1200 - bb[2] + bb[0]) / 2, (300 - bb[3] - bb[1]) / 2), "AD", fill=(156, 163, 175), font=f_grid)
        im.save(p)
        made += 1
    colors = [(96, 165, 250), (59, 130, 246), (99, 102, 241), (139, 92, 246), (14, 165, 233), (37, 99, 235)]
    for i, col in enumerate(colors, 1):
        p = d / f"s{i}.png"
        if p.exists():
            continue
        im = Image.new("RGB", (1600, 360), col)
        dr = ImageDraw.Draw(im)
        txt = f"AD {i}"
        bb = dr.textbbox((0, 0), txt, font=f_slide)
        dr.text(((1600 - bb[2] + bb[0]) / 2, (360 - bb[3] - bb[1]) / 2), txt, fill=(255, 255, 255), font=f_slide)
        im.save(p)
        made += 1
    return made


def main():
    conn = pymysql.connect(host=Config.DB_HOST, port=Config.DB_PORT, user=Config.DB_USER,
                           password=Config.DB_PASSWORD, database=Config.DB_NAME, autocommit=True)
    cur = conn.cursor()

    def col(table, name):
        cur.execute(f"SHOW COLUMNS FROM {table} LIKE %s", (name,))
        return cur.fetchone()

    def table(name):
        cur.execute("SHOW TABLES LIKE %s", (name,))
        return cur.fetchone()

    done = []

    # -- media badge/eff (2026-09-01) --------------------------------------
    c = col("media", "badge")
    if c and "sale" in str(c[1]):
        cur.execute("ALTER TABLE media MODIFY badge ENUM('rec','sale','best','new') NULL")
        cur.execute("UPDATE media SET badge = 'best' WHERE badge = 'sale'")
        cur.execute("ALTER TABLE media MODIFY badge ENUM('rec','best','new') NULL")
        done.append("media.badge sale->best")
    if not col("media", "eff_level"):
        cur.execute("ALTER TABLE media ADD COLUMN eff_level ENUM('normal','good','best') NOT NULL DEFAULT 'good' AFTER badge")
        cur.execute("""UPDATE media SET eff_level = CASE
            WHEN COALESCE(efficiency_manual, efficiency_auto) >= 75 THEN 'best'
            WHEN COALESCE(efficiency_manual, efficiency_auto) >= 60 THEN 'good' ELSE 'normal' END""")
        done.append("media.eff_level")
    if not col("media", "eff_note"):
        cur.execute("ALTER TABLE media ADD COLUMN eff_note VARCHAR(120) NULL AFTER eff_level")
        cur.execute("UPDATE media SET eff_note = '테스트'")
        done.append("media.eff_note")

    # -- media discussion tables (2026-09-01) ------------------------------
    if not table("media_nicks"):
        cur.execute("""CREATE TABLE media_nicks (
            media_id INT NOT NULL, user_id INT NOT NULL, nick VARCHAR(20) NOT NULL,
            PRIMARY KEY (media_id, user_id)) ENGINE=InnoDB""")
        done.append("media_nicks")
    if not table("media_comments"):
        cur.execute("""CREATE TABLE media_comments (
            id INT AUTO_INCREMENT PRIMARY KEY, media_id INT NOT NULL, user_id INT NOT NULL,
            anon_nick VARCHAR(20) NOT NULL, body VARCHAR(500) NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            KEY idx_media_created (media_id, created_at)) ENGINE=InnoDB""")
        done.append("media_comments")

    # -- banners.zone + slide slots (2026-09-02) ---------------------------
    if not col("banners", "zone"):
        cur.execute("ALTER TABLE banners ADD COLUMN zone ENUM('grid','slide') NOT NULL DEFAULT 'grid' AFTER subtitle")
        done.append("banners.zone")
    cur.execute("SELECT COUNT(*) FROM banners WHERE zone = 'slide'")
    if cur.fetchone()[0] == 0:
        for i in range(1, 7):
            cur.execute("INSERT INTO banners (title, link, image_url, zone, sort, is_active) VALUES (%s,'',%s,'slide',%s,1)",
                        (f"슬라이드 테스트 {i}", f"/static/uploads/banners/s{i}.png", i))
        done.append("slide banner rows x6")

    # -- strip banner settings (2026-09-02, default OFF) -------------------
    for k, v in (("strip_on", "0"), ("strip_text", "테스트 띠배너 문구입니다"), ("strip_link", ""), ("strip_bg", "#2563EB")):
        cur.execute("INSERT IGNORE INTO settings (k, v) VALUES (%s,%s)", (k, v))

    n = ensure_banner_images()
    if n:
        done.append(f"banner images x{n}")

    conn.close()
    print("migrate:", ", ".join(done) if done else "nothing to do")


if __name__ == "__main__":
    main()
