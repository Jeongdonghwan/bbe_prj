"""Content (notice/info/series) admin helpers: HTML sanitize, image upload."""
import os
import uuid

import bleach
from flask import current_app

ALLOWED_TAGS = ["p", "br", "b", "strong", "i", "em", "u", "h2", "h3", "ul", "ol", "li", "a", "img", "hr", "table", "thead", "tbody",
                "tr", "th", "td", "blockquote", "code", "pre", "span", "div"]
ALLOWED_ATTRS = {"a": ["href", "title", "target", "rel"], "img": ["src", "alt", "width", "height"], "td": ["colspan", "rowspan"],
                 "th": ["colspan", "rowspan"], "span": ["class"], "div": ["class"]}
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]
IMG_EXT = {"png", "jpg", "jpeg", "gif", "webp"}

NOTICE_CATEGORIES = {"must": "필독", "update": "업데이트", "maint": "점검", "event": "이벤트"}
INFO_CATEGORIES = {"guide": "가이드", "data": "데이터", "update": "업데이트"}


class ContentError(Exception):
    pass


def sanitize(html):
    return bleach.clean(html or "", tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, protocols=ALLOWED_PROTOCOLS, strip=True)


def save_image(file):
    if not file or not file.filename:
        raise ContentError("파일이 없습니다.")
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in IMG_EXT:
        raise ContentError("이미지 파일만 업로드할 수 있습니다.")
    data = file.read()
    if len(data) > 5_000_000:
        raise ContentError("이미지는 5MB 이하여야 합니다.")
    d = os.path.join(current_app.root_path, "static", "uploads", "content")
    os.makedirs(d, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(d, name), "wb") as f:
        f.write(data)
    return f"/static/uploads/content/{name}"
