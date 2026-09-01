"""Media admin helpers: logo upload (square check), auto efficiency."""
import os
import uuid

from PIL import Image
from flask import current_app

from ..models import campaign as campaign_model
from ..models import media as media_model

ALLOWED = {"png", "jpg", "jpeg", "svg", "webp"}


class MediaError(Exception):
    pass


def upload_dir():
    return os.path.join(current_app.root_path, "static", "uploads", "media")


def save_logo(media_id, file):
    """Save square logo -> /static/uploads/media/<id>.<ext>. Returns url."""
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED:
        raise MediaError("PNG/JPG/SVG/WEBP 파일만 업로드할 수 있습니다.")
    data = file.read()
    if len(data) > 1_000_000:
        raise MediaError("로고는 1MB 이하여야 합니다.")
    if ext != "svg":
        from io import BytesIO
        try:
            im = Image.open(BytesIO(data))
            w, h = im.size
        except Exception:
            raise MediaError("이미지 파일을 읽을 수 없습니다.")
        if abs(w - h) > max(2, int(w * 0.02)):
            raise MediaError(f"정사각 이미지만 가능합니다 (현재 {w}×{h}).")
    os.makedirs(upload_dir(), exist_ok=True)
    for old in os.listdir(upload_dir()):
        if old.startswith(f"{media_id}."):
            os.remove(os.path.join(upload_dir(), old))
    name = f"{media_id}.{ext}"
    with open(os.path.join(upload_dir(), name), "wb") as f:
        f.write(data)
    url = f"/static/uploads/media/{name}?v={uuid.uuid4().hex[:6]}"
    media_model.update_fields(media_id, {"logo_url": url})
    return url


def delete_logo(media_id):
    d = upload_dir()
    if os.path.isdir(d):
        for old in os.listdir(d):
            if old.startswith(f"{media_id}."):
                os.remove(os.path.join(d, old))
    media_model.update_fields(media_id, {"logo_url": None})


def calc_efficiency(media_id):
    """Auto efficiency = share of done campaigns (last 30 days) whose rank improved. None if no data."""
    n, up = campaign_model.done_rank_stats(media_id, 30)
    return int(round(up / n * 100)) if n else None


def refresh_all_efficiency():
    """Batch hook (P5): recompute efficiency_auto for every media."""
    for m in media_model.list_by_channel("place", False) + media_model.list_by_channel("store", False) + media_model.list_by_channel("coupang", False):
        e = calc_efficiency(m["id"])
        if e is not None:
            media_model.update_fields(m["id"], {"efficiency_auto": e})
