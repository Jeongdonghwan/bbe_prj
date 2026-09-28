"""80 번 server 블록에 순위 콜백 location 을 끼워 넣는다 (한 번만 실행).

    sudo /root/bbe_prj/bbe_prj/deploy/install_callback_nginx.py [nginx설정파일]

기본 대상은 /etc/nginx/sites-enabled/ilioom — 이 서버의 80 번을 쥐고 있는 사이트다.
남의 사이트 설정을 건드리므로 백업을 먼저 뜨고, 이미 들어가 있으면 아무것도 하지 않는다.
실행 후 반드시 `nginx -t && systemctl reload nginx`.
"""
import io
import shutil
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_TARGET = "/etc/nginx/sites-enabled/ilioom"
MARKER = "/bbe/rank-callback"


def main():
    target = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TARGET)
    snippet = Path(__file__).resolve().parent / "nginx-callback.conf"
    if not target.exists():
        print(f"대상 파일이 없습니다: {target}")
        return 1
    if not snippet.exists():
        print(f"삽입할 설정이 없습니다: {snippet}")
        return 1

    s = io.open(target, encoding="utf-8").read()
    if MARKER in s:
        print("이미 들어가 있습니다. 아무것도 하지 않았습니다.")
        return 0

    # 80 번 server 블록의 기준선을 찾는다 — server_name 줄 바로 뒤에 넣는다.
    anchor = None
    for line in s.splitlines():
        if line.strip().startswith("server_name "):
            anchor = line
            break
    if anchor is None:
        print("server_name 줄을 찾지 못했습니다. 수동으로 넣어주세요:")
        print(io.open(snippet, encoding="utf-8").read())
        return 1

    backup = target.with_suffix(target.suffix + f".bak.{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(target, backup)
    body = io.open(snippet, encoding="utf-8").read().rstrip()
    io.open(target, "w", encoding="utf-8").write(s.replace(anchor, anchor + "\n\n" + body + "\n", 1))
    print(f"추가했습니다. 백업: {backup}")
    print("이제: sudo nginx -t && sudo systemctl reload nginx")
    return 0


if __name__ == "__main__":
    sys.exit(main())
