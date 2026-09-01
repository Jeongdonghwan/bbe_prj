"""/notice — notice list & detail (contents.board='notice')."""
from flask import Blueprint, abort, current_app, render_template, request

from ..models import content as content_model

bp = Blueprint("notice", __name__, url_prefix="/notice")

NOTICE_CATEGORIES = {"must": "필독", "update": "업데이트", "maint": "점검", "event": "이벤트"}


@bp.route("")
def index():
    page = max(1, request.args.get("page", 1, type=int))
    per_page = current_app.config["PER_PAGE"]
    items = content_model.list_contents("notice", page=page, per_page=per_page)
    total = content_model.count_contents("notice")
    total_pages = max(1, -(-total // per_page))
    return render_template("notice/list.html", items=items, page=page, total_pages=total_pages, total=total)


@bp.route("/<int:content_id>")
def detail(content_id):
    item = content_model.get_content(content_id, ["notice"])
    if not item:
        abort(404)
    content_model.increment_views(content_id)
    prev_row, next_row = content_model.get_prev_next(item)
    return render_template("notice/detail.html", item=item, prev_row=prev_row, next_row=next_row)
