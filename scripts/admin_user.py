"""운영자 계정 발급·비밀번호 재설정.

    python scripts/admin_user.py list
    python scripts/admin_user.py create ops@bbene.co.kr            # 비밀번호 자동 생성
    python scripts/admin_user.py create ops@bbene.co.kr --nickname 운영팀
    python scripts/admin_user.py passwd ops@bbene.co.kr            # 재설정
    python scripts/admin_user.py revoke ops@bbene.co.kr            # 운영 권한 회수(일반 회원으로)

비밀번호는 화면에 한 번만 보여주고 저장하지 않는다. 직접 정하려면 --password 로 주되,
셸 히스토리에 남으니 되도록 자동 생성을 쓸 것.
"""
import argparse
import secrets
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from werkzeug.security import generate_password_hash  # noqa: E402

from app import create_app  # noqa: E402
from app.db import execute, query, query_one  # noqa: E402

ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*"


def gen_password(n=16):
    return "".join(secrets.choice(ALPHABET) for _ in range(n))


def cmd_list():
    rows = query("SELECT id, email, nickname, status, (password_hash IS NOT NULL) AS pw FROM users WHERE role='admin' ORDER BY id")
    if not rows:
        print("운영자 계정이 없습니다. create 로 만드세요.")
        return 1
    print(f"{'id':>4}  {'이메일':<30} {'이름':<12} {'상태':<8} 비밀번호")
    for r in rows:
        print(f"{r['id']:>4}  {(r['email'] or '-'):<30} {(r['nickname'] or '-'):<12} {r['status']:<8} "
              f"{'설정됨' if r['pw'] else '없음 (로그인 불가)'}")
    return 0


def cmd_create(email, nickname, password):
    if query_one("SELECT id FROM users WHERE email = %s", [email]):
        print(f"이미 있는 이메일입니다: {email}\n비밀번호를 바꾸려면 passwd 를 쓰세요.")
        return 1
    shown = password or gen_password()
    uid = execute(
        """INSERT INTO users (email, password_hash, nickname, role, status, notify_event)
           VALUES (%s,%s,%s,'admin','active',0)""",
        [email, generate_password_hash(shown), nickname])
    print(f"운영자 계정을 만들었습니다 (id {uid})")
    print(f"  이메일   {email}")
    print(f"  비밀번호 {shown}")
    print("\n로그인: /auth/admin/login  — 이 비밀번호는 다시 볼 수 없습니다.")
    return 0


def cmd_passwd(email, password):
    u = query_one("SELECT id, role FROM users WHERE email = %s", [email])
    if not u:
        print(f"없는 이메일입니다: {email}")
        return 1
    shown = password or gen_password()
    execute("UPDATE users SET password_hash = %s WHERE id = %s", [generate_password_hash(shown), u["id"]])
    if u["role"] != "admin":
        execute("UPDATE users SET role = 'admin' WHERE id = %s", [u["id"]])
        print("(일반 회원이라 운영 권한도 함께 부여했습니다)")
    print(f"비밀번호를 재설정했습니다: {email}")
    print(f"  비밀번호 {shown}")
    return 0


def cmd_revoke(email):
    u = query_one("SELECT id, role FROM users WHERE email = %s", [email])
    if not u or u["role"] != "admin":
        print(f"운영자 계정이 아닙니다: {email}")
        return 1
    if query_one("SELECT COUNT(*) AS n FROM users WHERE role='admin' AND status='active'")["n"] <= 1:
        print("마지막 운영자 계정이라 회수할 수 없습니다. 다른 운영자를 먼저 만드세요.")
        return 1
    execute("UPDATE users SET role = 'biz' WHERE id = %s", [u["id"]])
    print(f"운영 권한을 회수했습니다: {email} (계정은 일반 회원으로 남습니다)")
    return 0


def main():
    ap = argparse.ArgumentParser(description="운영자 계정 관리")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="운영자 계정 목록")
    c = sub.add_parser("create", help="운영자 계정 발급")
    c.add_argument("email")
    c.add_argument("--nickname", default="운영팀")
    c.add_argument("--password", help="직접 지정 (비우면 자동 생성)")
    p = sub.add_parser("passwd", help="비밀번호 재설정")
    p.add_argument("email")
    p.add_argument("--password", help="직접 지정 (비우면 자동 생성)")
    r = sub.add_parser("revoke", help="운영 권한 회수")
    r.add_argument("email")
    a = ap.parse_args()

    app = create_app()
    with app.app_context():
        if a.cmd == "list":
            return cmd_list()
        if a.cmd == "create":
            return cmd_create(a.email.strip().lower(), a.nickname.strip()[:20], a.password)
        if a.cmd == "passwd":
            return cmd_passwd(a.email.strip().lower(), a.password)
        if a.cmd == "revoke":
            return cmd_revoke(a.email.strip().lower())
    return 0


if __name__ == "__main__":
    sys.exit(main())
