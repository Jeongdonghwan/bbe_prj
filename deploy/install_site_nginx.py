"""마이마케팅 도메인 server 블록을 nginx 에 설치한다 (몇 번 돌려도 같은 결과).

    sudo python3 /root/bbe_prj/bbe_prj/deploy/install_site_nginx.py

deploy/nginx-site.conf 를 /etc/nginx/sites-available/mymarketing 에 복사하고 sites-enabled 에
심볼릭 링크를 건다. 이미 certbot 이 443 을 붙여 놓은 파일이 있으면 **덮어쓰지 않는다** —
그 파일에는 인증서 경로가 들어 있어서 원본으로 되돌리면 https 가 죽는다.
남의 사이트(ilioom) 설정은 건드리지 않는다. 실행 후 nginx -t 를 자동으로 돌리고, 통과하면
reload 명령을 알려준다(직접 reload 하지는 않는다 — 실패 시 되돌릴 판단은 사람이).
"""
import io
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

NAME = "mymarketing"
AVAILABLE = Path("/etc/nginx/sites-available") / NAME
ENABLED = Path("/etc/nginx/sites-enabled") / NAME
SRC = Path(__file__).resolve().parent / "nginx-site.conf"


def main():
    if not SRC.exists():
        print(f"원본 설정이 없습니다: {SRC}")
        return 1
    if not AVAILABLE.parent.exists():
        print(f"{AVAILABLE.parent} 가 없습니다. 이 서버의 nginx 는 sites-available 구조가 아닙니다 — "
              f"nginx.conf 의 include 줄을 확인해서 {SRC} 를 그 디렉터리에 두세요.")
        return 1

    if AVAILABLE.exists():
        cur = io.open(AVAILABLE, encoding="utf-8").read()
        if "ssl_certificate" in cur:
            print(f"{AVAILABLE} 에 이미 certbot 이 붙인 인증서 설정이 있습니다. 덮어쓰지 않습니다.")
            print("80 블록 내용을 바꾸고 싶으면 그 파일을 직접 고치세요 (443 블록은 그대로 두고).")
        elif cur == io.open(SRC, encoding="utf-8").read():
            print("이미 같은 내용입니다.")
        else:
            # 백업은 sites-enabled 바깥에. include sites-enabled/* 가 통째로 읽기 때문.
            bdir = Path("/var/backups/nginx")
            bdir.mkdir(parents=True, exist_ok=True)
            b = bdir / f"{NAME}.{datetime.now():%Y%m%d-%H%M%S}"
            shutil.copy2(AVAILABLE, b)
            shutil.copy2(SRC, AVAILABLE)
            print(f"갱신했습니다. 백업: {b}")
    else:
        shutil.copy2(SRC, AVAILABLE)
        print(f"설치했습니다: {AVAILABLE}")

    if not ENABLED.exists():
        ENABLED.symlink_to(AVAILABLE)
        print(f"활성화했습니다: {ENABLED} -> {AVAILABLE}")

    r = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
    print(r.stderr.strip())
    if r.returncode != 0:
        print("\nnginx -t 실패. 활성화를 되돌립니다 (다른 사이트가 죽지 않게).")
        ENABLED.unlink(missing_ok=True)
        return 1
    print("\n통과. 이제:  sudo systemctl reload nginx")
    print("확인:        curl -sI -H 'Host: xn--hz2ba848cszgbqko5fcyd.kr' http://127.0.0.1/ | head -3")
    return 0


if __name__ == "__main__":
    sys.exit(main())
