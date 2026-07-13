#!/usr/bin/env bash
# 코드·KB 변경 후 공개 URL 유지하며 최신 반영
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "=== 업데이트 동기화 (공개 URL 유지) ==="

if [[ "${1:-}" == "--reindex" ]]; then
  echo "KB 재색인…"
  VENV/bin/python build_index.py
fi

# 게이트웨이 재시작 (프록시·랜딩 최신화)
gw_pid="$(lsof -ti :"${SHARE_GATEWAY_PORT:-8506}" -sTCP:LISTEN 2>/dev/null | head -1 || true)"
if [[ -n "${gw_pid:-}" ]]; then
  kill "$gw_pid" 2>/dev/null || true
  sleep 1
fi
nohup VENV/bin/python share_gateway.py >>.gateway.log 2>&1 &
sleep 2

"$ROOT/restart_app.sh"
"$ROOT/sync_public_url.sh"
