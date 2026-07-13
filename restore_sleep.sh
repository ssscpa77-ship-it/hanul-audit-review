#!/usr/bin/env bash
# 절전 설정 기본값 복원 (검증 종료 후)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
CAFFEINATE_PID_FILE="${ROOT}/.caffeinate.pid"

if [[ -f "$CAFFEINATE_PID_FILE" ]]; then
  pid="$(cat "$CAFFEINATE_PID_FILE" 2>/dev/null || true)"
  if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    echo "caffeinate 종료 (PID $pid)"
  fi
  rm -f "$CAFFEINATE_PID_FILE"
fi

# macOS 기본에 가깝게 복원
sudo pmset -a sleep 1 standby 1 powernap 1 disksleep 10 displaysleep 10 2>/dev/null \
  || pmset -c sleep 0 displaysleep 10 2>/dev/null \
  || true

echo "절전 설정을 기본값에 가깝게 복원했습니다."
