#!/usr/bin/env bash
# 임시 공개 URL — Cloudflare Quick Tunnel
# 사용: ./run_tunnel.sh [포트] [url파일접미사]
#   ./run_tunnel.sh 8506 share   → .tunnel.url (카톡 공유용)
#   ./run_tunnel.sh 8505 app     → .app_tunnel.url (앱 직접 접속)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PORT="${1:-${TUNNEL_PORT:-8506}}"
NAME="${2:-share}"
METRICS_BASE="${TUNNEL_METRICS_PORT:-20342}"
METRICS_PORT="$((METRICS_BASE + PORT - 8505))"
TUNNEL_LOG="${ROOT}/.tunnel_${NAME}.log"
TUNNEL_PID_FILE="${ROOT}/.tunnel_${NAME}.pid"
TUNNEL_URL_FILE="${ROOT}/.tunnel.url"
[[ "$NAME" == "app" ]] && TUNNEL_URL_FILE="${ROOT}/.app_tunnel.url"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared 가 없습니다. 설치: brew install cloudflared" >&2
  exit 1
fi

if ! lsof -i :"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "포트 ${PORT} 에 서비스가 없습니다." >&2
  exit 1
fi

existing_pid="$(pgrep -f "cloudflared tunnel --url http://127.0.0.1:${PORT}" 2>/dev/null | head -1 || true)"
if [[ -n "${existing_pid:-}" ]]; then
  echo "[$NAME] 터널 실행 중 (PID $existing_pid, 포트 $PORT)"
  [[ -f "$TUNNEL_URL_FILE" ]] && echo "URL: $(cat "$TUNNEL_URL_FILE")"
  exit 0
fi

: > "$TUNNEL_LOG"

nohup cloudflared tunnel \
  --url "http://127.0.0.1:${PORT}" \
  --metrics "127.0.0.1:${METRICS_PORT}" \
  --no-autoupdate >>"$TUNNEL_LOG" 2>&1 &

disown

echo "[$NAME] 터널 시작 중… (포트 $PORT)"
for _ in $(seq 1 35); do
  pid="$(pgrep -f "cloudflared tunnel --url http://127.0.0.1:${PORT}" 2>/dev/null | head -1 || true)"
  url="$(grep -F 'trycloudflare.com' "$TUNNEL_LOG" | grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1 || true)"
  if [[ -n "${pid:-}" && -n "${url:-}" ]]; then
    echo "$pid" > "$TUNNEL_PID_FILE"
    echo "$url" > "$TUNNEL_URL_FILE"
    stable="${ROOT}/.tunnel.url.stable"
    echo "$url" > "$stable"
    echo "[$NAME] $url"
    exit 0
  fi
  sleep 1
done

echo "[$NAME] URL 확인 실패. 로그: $TUNNEL_LOG" >&2
exit 1
