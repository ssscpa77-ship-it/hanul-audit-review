#!/usr/bin/env bash
# Streamlit → 게이트웨이 → 터널 순서로 안전 기동
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
APP_PORT="${STREAMLIT_SERVER_PORT:-8505}"
GATEWAY_PORT="${SHARE_GATEWAY_PORT:-8506}"

echo "=== 전체 서비스 재시작 ==="

# 정리
for port in "$GATEWAY_PORT" "$APP_PORT"; do
  pid="$(lsof -ti :"$port" -sTCP:LISTEN 2>/dev/null | head -1 || true)"
  [[ -n "${pid:-}" ]] && kill "$pid" 2>/dev/null || true
done
sleep 2

# 1) Streamlit
"$ROOT/restart_app.sh"

# 2) Streamlit 준비 대기
for i in $(seq 1 20); do
  if curl -sf --max-time 2 "http://127.0.0.1:${APP_PORT}/_stcore/health" >/dev/null 2>&1 \
     || curl -sf --max-time 2 "http://127.0.0.1:${APP_PORT}/" >/dev/null 2>&1; then
    echo "✓ Streamlit 준비 완료"
    break
  fi
  sleep 1
  [[ "$i" -eq 20 ]] && echo "⚠ Streamlit 응답 지연 — 게이트웨이는 계속 시작합니다"
done

# 3) Gateway
nohup "$ROOT/VENV/bin/python" "$ROOT/share_gateway.py" >>"$ROOT/.gateway.log" 2>&1 &
sleep 2
if ! lsof -i :"$GATEWAY_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "✗ Gateway 시작 실패 — .gateway.log 확인" >&2
  exit 1
fi
echo "✓ Gateway (포트 $GATEWAY_PORT)"

# 4) Tunnel
# shellcheck source=tunnel_lib.sh
source "${ROOT}/tunnel_lib.sh"
if tunnel_is_named; then
  "${ROOT}/run_named_tunnel.sh" 2>/dev/null || echo "⚠ 고정 터널 시작 실패 — ./run_named_tunnel.sh 확인"
elif ! pgrep -f "cloudflared tunnel --url http://127.0.0.1:${GATEWAY_PORT}" >/dev/null 2>&1; then
  nohup cloudflared tunnel \
    --url "http://127.0.0.1:${GATEWAY_PORT}" \
    --metrics "127.0.0.1:20346" \
    --no-autoupdate >>"$ROOT/.tunnel_share.log" 2>&1 &
  echo "터널 시작 중… (15초)"
  for _ in $(seq 1 15); do
    url="$(grep -Eo 'https://[a-z0-9-]+\.trycloudflare\.com' "$ROOT/.tunnel_share.log" 2>/dev/null | tail -1 || true)"
    [[ -n "${url:-}" ]] && echo "$url" > "$ROOT/.tunnel.url" && break
    sleep 1
  done
fi
"$ROOT/sync_public_url.sh"
echo ""
echo -n "랜딩: "; curl -s -o /dev/null -w "%{http_code}\n" --max-time 5 "http://127.0.0.1:${GATEWAY_PORT}/"
echo -n "앱:   "; curl -s -o /dev/null -w "%{http_code}\n" --max-time 8 "http://127.0.0.1:${GATEWAY_PORT}/?app=1"
