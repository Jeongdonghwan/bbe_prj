#!/usr/bin/env bash
# Linux server deploy/restart script (run via MobaXterm SSH).
#
#   bash scripts/deploy.sh --init   # first run: venv + deps + schema + seed
#   bash scripts/deploy.sh          # (re)start the preview server on :8034
#
# Requires: python3, python3-venv, git, MariaDB running with .env credentials.
set -e
cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "[deploy] .env 파일을 새로 만들었습니다. SECRET_KEY / DB_PASSWORD 등을 수정한 뒤 다시 실행하세요."
  exit 1
fi

if [ "$1" = "--init" ]; then
  echo "[deploy] applying schema + seed data..."
  python scripts/seed.py --schema
fi

python scripts/migrate.py

# cron: 주기 작업 등록. 줄 단위로 확인해서 없는 것만 더한다 — 예전에는 bbe-cron 이 하나라도
# 있으면 통째로 건너뛰어서, 나중에 추가한 작업이 기존 서버에 영영 안 들어갔다.
if command -v crontab >/dev/null 2>&1; then
  ROOT="$(pwd)"
  PY="$ROOT/.venv/bin/python"
  [ -x "$PY" ] || PY="$(command -v python3 || command -v python)"
  CUR="$(crontab -l 2>/dev/null || true)"
  NEW="$CUR"
  add_cron() {   # $1=스케줄  $2=작업명
    case "$NEW" in
      *"cron.py $2 "*) return 0 ;;
    esac
    NEW="$NEW
$1 cd $ROOT && $PY scripts/cron.py $2 >> $ROOT/cron.log 2>&1  # bbe-cron"
    echo "[deploy] cron 추가: $2 ($1)"
  }
  add_cron "10 4 * * *"  daily
  add_cron "0  * * * *"  hourly
  # 순위·이름 보정은 5분마다. 순위 서버 콜백이 막히거나 늦어도 화면이 오래 비지 않게 한다
  # (호출은 추적 중인데 오늘 순위가 없는 건에만 나가므로 평소엔 거의 0건이다).
  add_cron "*/5 * * * *" sync_ranks
  # 블로그 자동 발행: 클라우드 루틴이 04:00·13:00 에 글을 푸시하면 06:00·14:00 에 받아온다 (docs/BLOG_ROUTINE.md)
  add_cron "0 6,14 * * *" pull_content
  if [ "$NEW" != "$CUR" ]; then
    printf '%s
' "$NEW" | sed '/^$/d' | crontab -
    echo "[deploy] cron 갱신됨. 해제: crontab -e 에서 bbe-cron 줄 삭제"
  fi
fi

# restart: kill previous instance if any
pkill -f "scripts/serve_preview.py" 2>/dev/null || true
sleep 1
nohup python scripts/serve_preview.py > preview.log 2>&1 &
sleep 2
if curl -sf -o /dev/null http://127.0.0.1:8034/; then
  echo "[deploy] OK — http://$(hostname -I 2>/dev/null | awk '{print $1}'):8034"
else
  echo "[deploy] FAILED — check preview.log"
  tail -20 preview.log
  exit 1
fi
