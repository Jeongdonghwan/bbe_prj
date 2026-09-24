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

# cron: 주기 작업 등록 (매일 04:10 / 매시 정각). 이미 있으면 건드리지 않는다.
if command -v crontab >/dev/null 2>&1; then
  ROOT="$(pwd)"
  PY="$ROOT/.venv/bin/python"
  [ -x "$PY" ] || PY="$(command -v python3 || command -v python)"
  CUR="$(crontab -l 2>/dev/null || true)"
  if ! printf '%s' "$CUR" | grep -q "bbe-cron"; then
    { printf '%s
' "$CUR"
      echo "10 4 * * * cd $ROOT && $PY scripts/cron.py daily  >> $ROOT/cron.log 2>&1  # bbe-cron"
      echo "0  * * * * cd $ROOT && $PY scripts/cron.py hourly >> $ROOT/cron.log 2>&1  # bbe-cron"
    } | crontab -
    echo "[deploy] cron 등록됨 (daily 04:10 / hourly). 해제: crontab -e 에서 bbe-cron 줄 삭제"
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
