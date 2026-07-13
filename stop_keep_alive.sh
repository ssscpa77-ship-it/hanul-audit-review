#!/usr/bin/env bash
# 상시 유지(keep_alive) 중지
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="${ROOT}/.keep_alive.pid"

if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    echo "keep_alive 종료 (PID $pid)"
  fi
  rm -f "$PID_FILE"
else
  echo "keep_alive 가 실행 중이 아닙니다."
fi
