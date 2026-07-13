#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
for name in share app; do
  pid_file="${ROOT}/.tunnel_${name}.pid"
  port=8506
  [[ "$name" == "app" ]] && port=8505
  pid=""
  [[ -f "$pid_file" ]] && pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [[ -z "${pid:-}" ]] || ! kill -0 "$pid" 2>/dev/null; then
    pid="$(pgrep -f "cloudflared tunnel --url http://127.0.0.1:${port}" 2>/dev/null | head -1 || true)"
  fi
  if [[ -n "${pid:-}" ]]; then
    kill "$pid" 2>/dev/null || true
    echo "[$name] 터널 종료 (PID $pid)"
  fi
  rm -f "$pid_file"
done
rm -f "${ROOT}/.tunnel.url" "${ROOT}/.app_tunnel.url"
echo "모든 터널 종료"
