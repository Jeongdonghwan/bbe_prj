"""모든 화면이 200 인지 확인 (사용자 + 어드민)."""
import os
import sys

os.chdir(r"C:\bbe_prj")
sys.path.insert(0, r"C:\bbe_prj")

from app import create_app  # noqa: E402

USER_URLS = ['/', '/notice', '/community/anon', '/community/qna', '/community/info', '/popular',
             '/popular?ch=place', '/popular?ch=coupang', '/campaign/place/new', '/campaign/store/new',
             '/campaign/coupang/new', '/campaign/place', '/campaign/store/slots', '/credit/charge',
             '/my', '/my?ct=usage', '/tools/keyword', '/notifications']
ADMIN_URLS = ['/admin', '/admin/orders', '/admin/orders?user=2', '/admin/payments', '/admin/credits',
              '/admin/media', '/admin/media?channel=store', '/admin/media?channel=coupang',
              '/admin/banners', '/admin/users', '/admin/operators', '/admin/popular', '/admin/content', '/admin/agency', '/admin/reports']


def main():
    app = create_app()
    app.config["TESTING"] = True
    c = app.test_client()
    bad = []
    with c.session_transaction() as s:
        s["uid"] = 10
    for u in USER_URLS:
        r = c.get(u)
        if r.status_code != 200:
            bad.append((u, r.status_code))
    print("user pages:", "ALL 200" if not bad else bad)
    bad = []
    with c.session_transaction() as s:
        s["uid"] = 1
    for u in ADMIN_URLS:
        r = c.get(u)
        if r.status_code != 200:
            bad.append((u, r.status_code))
    print("admin pages:", "ALL 200" if not bad else bad)


if __name__ == "__main__":
    main()
