"""/tools — keyword lookup (max 5) and related keywords (max 100) with 24h cache and daily quota."""
import csv
import io

from flask import Blueprint, Response, flash, g, redirect, render_template, request, session, url_for

from ..constants import CHANNEL_LABEL
from ..services import keyword_service, naver_ad
from .auth import login_required

bp = Blueprint("tools", __name__, url_prefix="/tools")


def _ip():
    return (request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr or "-")[:45]


def _ctx():
    q = keyword_service.quota(g.get("user"), _ip())
    return {"quota": q, "api_on": naver_ad.configured(), "logged": bool(g.get("user"))}


def _check_quota():
    q = keyword_service.quota(g.get("user"), _ip())
    if q["unlimited"] or q["remaining"] > 0:
        return None
    return q


@bp.route("/keyword", methods=["GET", "POST"])
@login_required
def keyword():
    rows, source, keywords, sort = [], None, "", request.values.get("sort", "total")
    if request.method == "POST" or request.args.get("q"):
        keywords = (request.values.get("q") or "").strip()
        parts = [k.strip() for k in keywords.replace("\n", ",").split(",") if k.strip()]
        if not parts:
            flash("키워드를 입력해주세요.")
        elif len(parts) > 5:
            flash("키워드는 최대 5개까지 조회할 수 있습니다.")
        elif _check_quota():
            flash("오늘 조회 한도(하루 30회)를 모두 썼습니다.")
        else:
            rows, source = keyword_service.lookup(parts)
            keyword_service.log_query(g.get("user"), _ip(), "keyword", ", ".join(parts))
            if sort in ("pc", "mo", "total"):
                rows.sort(key=lambda r: -r[sort])
            if request.args.get("csv") == "1":
                return _csv(rows, "keywords")
    return render_template("tools/keyword.html", rows=rows, source=source, keywords=keywords, sort=sort, **_ctx())


def _csv(rows, name):
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["키워드", "PC 검색량", "모바일 검색량", "합계", "경쟁도"])
    for r in rows:
        w.writerow([r["keyword"], r["pc"], r["mo"], r["total"], r.get("comp") or ""])
    return Response("﻿" + buf.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={name}.csv"})


@bp.route("/related", methods=["GET", "POST"])
@login_required
def related():
    rows, source, seed = [], None, (request.values.get("seed") or "").strip()
    if seed and (request.method == "POST" or request.args.get("seed")):
        if _check_quota():
            flash("오늘 조회 한도(하루 30회)를 모두 썼습니다.")
        else:
            rows, source = keyword_service.related(seed)
            keyword_service.log_query(g.get("user"), _ip(), "related", seed)
            if request.args.get("csv") == "1":
                return _csv(rows, f"related_{seed}")
    return render_template("tools/related.html", rows=rows, source=source, seed=seed, channels=CHANNEL_LABEL, **_ctx())


@bp.route("/related/pick", methods=["POST"])
def related_pick():
    """Selected related keywords -> session prefill -> campaign create (channel chosen in the modal)."""
    picked = [k.strip()[:60] for k in request.form.getlist("kw") if k.strip()][:6]
    channel = request.form.get("channel") if request.form.get("channel") in CHANNEL_LABEL else "place"
    if not picked:
        flash("키워드를 선택해주세요.")
        return redirect(url_for("tools.related", seed=request.form.get("seed", "")))
    if not g.get("user"):
        flash("캠페인 생성은 로그인 후 가능합니다.")
        return redirect(url_for("auth.kakao", next=url_for("tools.related", seed=request.form.get("seed", ""))))
    pre = {"main_keyword": picked[0], "keyword_mode": "manual", "setting_keywords": picked[:5]}
    if channel == "store" and len(picked) > 1:
        pre["sub_keywords"] = picked[1:4]
    session["campaign_prefill"] = pre
    flash(f"키워드 {len(picked)}개를 담았습니다. 세팅 키워드에 채워져 있어요.")
    return redirect(url_for("campaign.new", channel=channel))
