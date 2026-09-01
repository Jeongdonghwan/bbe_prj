"""/auth — Kakao login, first-login profile modal, dev login, logout."""
import re
import secrets
from functools import wraps

from werkzeug.security import check_password_hash, generate_password_hash

from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template, request, session,
                   url_for)

from ..models import user as user_model
from ..services import kakao_service

bp = Blueprint("auth", __name__, url_prefix="/auth")

PHONE_RE = re.compile(r"^01[016789]-?\d{3,4}-?\d{4}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---- helpers used app-wide -------------------------------------------------
def load_current_user():
    """before_request: g.user = users row or None."""
    g.user = None
    uid = session.get("uid")
    if uid:
        u = user_model.get_by_id(uid)
        if u and u["status"] == "active":
            g.user = u
        else:
            session.pop("uid", None)


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if not g.get("user"):
            flash("로그인이 필요합니다.")
            return redirect(url_for("auth.login", next=request.path))
        return view(*a, **kw)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if not g.get("user") or g.user["role"] != "admin":
            abort(403)
        return view(*a, **kw)
    return wrapped


def needs_onboarding(user):
    return bool(user) and not user.get("phone")


def _login(user_id, next_url=None):
    session.clear()
    session["uid"] = user_id
    return redirect(next_url if next_url and next_url.startswith("/") else "/")


def _fmt_phone(phone):
    digits = phone.replace("-", "")
    return f"{digits[:3]}-{digits[3:-4]}-{digits[-4:]}"


# ---- login / signup page ---------------------------------------------------
@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.get("user"):
        return redirect(request.args.get("next") or "/")
    next_url = request.values.get("next") or ""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = user_model.get_by_email(email) if email else None
        if not user or not user["password_hash"] or not check_password_hash(user["password_hash"], password):
            flash("이메일 또는 비밀번호가 올바르지 않습니다.")
            return redirect(url_for("auth.login", next=next_url or None))
        if user["status"] != "active":
            flash("이용이 제한된 계정입니다.")
            return redirect(url_for("auth.login"))
        return _login(user["id"], next_url or "/")
    key = current_app.config["KAKAO_REST_KEY"]
    return render_template("auth/login.html",
                           kakao_url=url_for("auth.kakao", next=next_url or None),
                           dev_mode=current_app.debug and current_app.config["DEV_LOGIN"],
                           no_key=not key, next_url=next_url)


# ---- local (email) signup ---------------------------------------------------
@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.get("user"):
        return redirect("/")
    next_url = request.values.get("next") or ""
    if request.method == "POST":
        f = request.form
        email = (f.get("email") or "").strip().lower()
        password = f.get("password") or ""
        nickname = (f.get("nickname") or "").strip()
        phone = (f.get("phone") or "").strip().replace(" ", "")
        err = None
        if not EMAIL_RE.match(email):
            err = "이메일 형식이 올바르지 않습니다."
        elif len(password) < 8:
            err = "비밀번호는 8자 이상이어야 합니다."
        elif password != f.get("password2"):
            err = "비밀번호 확인이 일치하지 않습니다."
        elif not (2 <= len(nickname) <= 20):
            err = "닉네임은 2~20자로 입력해주세요."
        elif not PHONE_RE.match(phone):
            err = "연락처 형식이 올바르지 않습니다. 예) 010-1234-5678"
        elif f.get("agree_terms") != "1" or f.get("agree_privacy") != "1":
            err = "이용약관과 개인정보 수집·이용에 동의해주세요."
        elif user_model.get_by_email(email):
            err = "이미 가입된 이메일입니다. 로그인해주세요."
        if err:
            flash(err)
            return render_template("auth/register.html", next_url=next_url, form=f), 400
        uid = user_model.create_local(email, generate_password_hash(password), nickname, _fmt_phone(phone),
                                      f.get("agree_marketing") == "1")
        resp = _login(uid, next_url or "/")  # _login clears the session, so flash afterwards
        flash("가입을 환영합니다! 첫 캠페인을 만들어보세요.")
        return resp
    return render_template("auth/register.html", next_url=next_url, form={})


# ---- kakao -----------------------------------------------------------------
@bp.route("/kakao")
def kakao():
    if g.get("user"):
        return redirect("/")
    key = current_app.config["KAKAO_REST_KEY"]
    if not key:
        # No key yet: send to the login page (dev buttons in DEBUG, guidance in prod).
        if not current_app.debug:
            flash("카카오 로그인 준비 중입니다. 잠시 후 다시 시도해주세요.")
        return redirect(url_for("auth.login", next=request.args.get("next")))
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    session["next"] = request.args.get("next", "/")
    return redirect(kakao_service.authorize_url(key, current_app.config["KAKAO_REDIRECT_URI"], state))


@bp.route("/kakao/callback")
def kakao_callback():
    if request.args.get("error"):
        flash("카카오 로그인이 취소되었습니다.")
        return redirect("/")
    if request.args.get("state") != session.pop("oauth_state", None):
        abort(400)
    try:
        token = kakao_service.exchange_code(
            current_app.config["KAKAO_REST_KEY"], current_app.config["KAKAO_REDIRECT_URI"], request.args.get("code", ""))
        kakao_id, nick = kakao_service.fetch_me(token)
    except kakao_service.KakaoError as e:
        current_app.logger.warning("kakao login failed: %s", e)
        flash("카카오 로그인에 실패했습니다. 잠시 후 다시 시도해주세요.")
        return redirect("/")
    user = user_model.get_by_kakao_id(kakao_id)
    if not user:
        uid = user_model.create(kakao_id, (nick or "회원")[:30])
    else:
        if user["status"] != "active":
            flash("이용이 제한된 계정입니다.")
            return redirect("/")
        uid = user["id"]
    return _login(uid, session.pop("next", "/"))


# ---- first-login profile modal ---------------------------------------------
@bp.route("/welcome", methods=["POST"])
def welcome():
    user = g.get("user")
    if not user:
        return redirect(url_for("auth.kakao"))
    if not needs_onboarding(user):
        return redirect(request.form.get("next") or "/my")
    if request.form.get("agree_terms") != "1" or request.form.get("agree_privacy") != "1":
        flash("이용약관과 개인정보 수집·이용에 동의해주세요.")
        return redirect(request.form.get("next") or "/")
    nickname = (request.form.get("nickname") or "").strip()
    phone = (request.form.get("phone") or "").strip().replace(" ", "")
    if not (2 <= len(nickname) <= 20):
        flash("닉네임은 2~20자로 입력해주세요.")
        return redirect(request.form.get("next") or "/")
    if not PHONE_RE.match(phone):
        flash("연락처 형식이 올바르지 않습니다. 예) 010-1234-5678")
        return redirect(request.form.get("next") or "/")
    digits = phone.replace("-", "")
    phone = f"{digits[:3]}-{digits[3:-4]}-{digits[-4:]}"
    user_model.update_profile(user["id"], nickname, phone)
    user_model.update_notify(user["id"], "notify_event", request.form.get("agree_marketing") == "1")
    flash("가입을 환영합니다! 첫 캠페인을 만들어보세요.")
    return redirect(request.form.get("next") or "/my")


# ---- dev login (DEBUG only) -------------------------------------------------
@bp.route("/dev-login")
def dev_login():
    """?as=user|admin|new — bypass Kakao while developing. 404 unless DEV_LOGIN=1 and FLASK_DEBUG."""
    if not (current_app.debug and current_app.config["DEV_LOGIN"]):
        abort(404)
    who = request.args.get("as", "user")
    if who == "admin":
        row = user_model.get_by_kakao_id("admin-0001")
    elif who == "new":
        n = secrets.token_hex(3)
        return _login(user_model.create(f"dev-{n}", f"신규{n[:4]}"), request.args.get("next"))
    else:
        row = user_model.get_by_kakao_id("kakao-1001")
    if not row:
        abort(404, "seed data missing — run scripts/seed.py")
    return _login(row["id"], request.args.get("next"))


@bp.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ---- terms / privacy --------------------------------------------------------
TERMS = [
    ("목적", "이 약관은 TRAFFIC HUB(이하 '회사')가 제공하는 리워드 트래픽 캠페인 서비스의 이용 조건과 절차를 정합니다."),
    ("회원가입", "가입은 카카오 계정 연동으로 이루어지며, 닉네임과 연락처를 등록하면 완료됩니다. 만 19세 이상 사업자·마케터를 대상으로 합니다."),
    ("서비스 내용", "플레이스·쇼핑스토어·쿠팡 유입 캠페인 주문, 키워드 도구, 커뮤니티를 제공합니다. 캠페인은 운영팀 검수 후 구동됩니다."),
    ("결제와 환불", "캠페인은 주문 시 카드·계좌이체로 건별 결제합니다. 검수 반려 시 전액, 진행 중 중단 시 잔여 일수분이 환불됩니다."),
    ("금지 행위", "허위·과장 문구(최저가, 1위, 의료법 위반 용어 등) 사용, 타인 업체 무단 등록, 커뮤니티 광고성 도배는 제한될 수 있습니다."),
    ("책임의 한계", "검색 순위는 플랫폼 정책 등 외부 요인의 영향을 받으며 특정 순위 도달을 보장하지 않습니다."),
]
PRIVACY = [
    ("수집 항목", "카카오 계정 식별자, 닉네임, 연락처(휴대전화), 선택 시 사업자 정보(상호·사업자번호). 서비스 이용 기록과 접속 IP가 자동 수집됩니다."),
    ("이용 목적", "회원 식별, 캠페인 진행 상태 안내(알림톡), 결제·세금계산서 처리, 부정 이용 방지, (동의 시) 이벤트 소식 안내."),
    ("보관 기간", "회원 탈퇴 시 지체 없이 파기합니다. 단, 전자상거래법 등 관련 법령에 따른 거래 기록은 법정 기간 동안 보관합니다."),
    ("제3자 제공", "결제 처리를 위한 PG사, 알림톡 발송 대행사 외에는 제공하지 않습니다. 대행의뢰 연락처는 본인이 제안을 수락한 상대에게만 공개됩니다."),
    ("이용자 권리", "마이페이지에서 알림 수신 설정을 변경하고 회원 탈퇴할 수 있습니다."),
]



