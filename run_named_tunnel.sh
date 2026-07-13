#!/usr/bin/env bash
# Cloudflare Named Tunnel — 고정 URL (재부팅 후에도 동일 hostname)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=tunnel_lib.sh
source "${ROOT}/tunnel_lib.sh"

if ! tunnel_is_named; then
  echo "고정 URL 미설정 — ./setup_named_tunnel.sh 먼저 실행" >&2
  exit 1
fi
tunnel_load_named

GATEWAY_PORT="${SHARE_GATEWAY_PORT:-8506}"
LOG="${ROOT}/.tunnel_named.log"
PID_FILE="${ROOT}/.tunnel_named.pid"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared 없음 — brew install cloudflared" >&2
  exit 1
fi

if ! lsof -i :"$GATEWAY_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "게이트웨이(포트 ${GATEWAY_PORT})가 없습니다. restart_all.sh 먼저 실행하세요." >&2
  exit 1
fi

if [[ ! -f "${CONFIG_FILE}" ]]; then
  echo "터널 설정 없음: ${CONFIG_FILE}" >&2
  exit 1
fi

if tunnel_named_running; then
  echo "[named] 터널 실행 중 — ${PUBLIC_URL}"
  tunnel_write_public_files || true
  exit 0
fi

# Quick 터널이 있으면 정리 (동시 사용 방지)
pkill -f "cloudflared tunnel --url http://127.0.0.1:${GATEWAY_PORT}" 2>/dev/null || true
sleep 1

: > "$LOG"
nohup cloudflared tunnel --config "${CONFIG_FILE}" run "${TUNNEL_NAME}" >>"$LOG" 2>&1 &
disown
echo $! > "$PID_FILE"

echo "[named] 터널 시작 중… ${PUBLIC_HOSTNAME}"
for _ in $(seq 1 25); do
  if tunnel_named_running; then
    tunnel_write_public_files
    "${ROOT}/sync_public_url.sh" 2>/dev/null || true
    echo "[named] 고정 URL: ${PUBLIC_URL}"
    exit 0
  fi
  sleep 1
done

echo "[named] 시작 실패 — ${LOG} 확인" >&2
exit 1
