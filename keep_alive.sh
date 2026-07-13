#!/usr/bin/env bash
# 앱 서버·통합 게이트웨이·단일 공개 터널 상시 유지 + 업데이트 자동 반영
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

APP_PORT="${STREAMLIT_SERVER_PORT:-8505}"
GATEWAY_PORT="${SHARE_GATEWAY_PORT:-8506}"
LOG="${ROOT}/.keep_alive.log"
PID_FILE="${ROOT}/.keep_alive.pid"
SERVER_LOG="${ROOT}/.server.log"
GATEWAY_LOG="${ROOT}/.gateway.log"
DEPLOY_STAMP="${ROOT}/.deploy_stamp"
KB_DB="${ROOT}/kb_store/hanul_kb.sqlite"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"
}

_deploy_mtime() {
  stat -f %m "$DEPLOY_STAMP" 2>/dev/null || stat -c %Y "$DEPLOY_STAMP" 2>/dev/null || echo 0
}

_src_changed_since_deploy() {
  [[ -f "$DEPLOY_STAMP" ]] || return 1
  local dep_m="$(_deploy_mtime)"
  local f m
  for f in "$ROOT"/*.py; do
    [[ -f "$f" ]] || continue
    m=$(stat -f %m "$f" 2>/dev/null || stat -c %Y "$f" 2>/dev/null || echo 0)
    [[ "$m" -gt "$dep_m" ]] && return 0
  done
  return 1
}

_needs_gateway_restart() {
  if [[ -f "${ROOT}/share_gateway.py" && -f "$DEPLOY_STAMP" ]]; then
    gw_m=$(stat -f %m "${ROOT}/share_gateway.py" 2>/dev/null || echo 0)
    dep_m="$(_deploy_mtime)"
    [[ "$gw_m" -gt "$dep_m" ]] && return 0
  fi
  return 1
}

_needs_app_restart() {
  _src_changed_since_deploy && return 0
  if [[ -f "$KB_DB" && -f "$DEPLOY_STAMP" ]]; then
    kb_m=$(stat -f %m "$KB_DB" 2>/dev/null || stat -c %Y "$KB_DB" 2>/dev/null || echo 0)
    dep_m="$(_deploy_mtime)"
    [[ "$kb_m" -gt "$dep_m" ]] && return 0
  fi
  return 1
}

_restart_gateway() {
  pid="$(lsof -ti :"$GATEWAY_PORT" -sTCP:LISTEN 2>/dev/null | head -1 || true)"
  [[ -n "${pid:-}" ]] && kill "$pid" 2>/dev/null || true
  sleep 1
  nohup "$ROOT/VENV/bin/python3" "$ROOT/share_gateway.py" >>"$GATEWAY_LOG" 2>&1 &
  sleep 2
}

ensure_caffeinate() {
  if ! pgrep -f "caffeinate -ims" >/dev/null 2>&1; then
    nohup caffeinate -ims >>"$LOG" 2>&1 &
    log "caffeinate 시작 (시스템 절전 방지, 화면 꺼짐 허용, PID $!)"
  fi
}

ensure_server() {
  if lsof -i :"$APP_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    if _needs_app_restart; then
      log "코드/KB 변경 감지 — Streamlit 재시작"
      "$ROOT/restart_app.sh" >>"$LOG" 2>&1
    fi
    return 0
  fi
  log "앱 서버 시작 (포트 $APP_PORT)"
  nohup "$ROOT/VENV/bin/streamlit" run app.py \
    --server.port="$APP_PORT" \
    --server.address=0.0.0.0 \
    --server.headless=true >>"$SERVER_LOG" 2>&1 &
  sleep 5
  date "+%Y-%m-%d %H:%M:%S" > "$DEPLOY_STAMP"
}

ensure_gateway() {
  if lsof -i :"$GATEWAY_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    if _needs_gateway_restart; then
      log "게이트웨이 코드 변경 감지 — 재시작"
      _restart_gateway
      date "+%Y-%m-%d %H:%M:%S" > "$DEPLOY_STAMP"
    fi
    return 0
  fi
  log "통합 게이트웨이 시작 (포트 $GATEWAY_PORT)"
  nohup "$ROOT/VENV/bin/python3" "$ROOT/share_gateway.py" >>"$GATEWAY_LOG" 2>&1 &
  sleep 2
}

ensure_tunnel() {
  # shellcheck source=tunnel_lib.sh
  source "${ROOT}/tunnel_lib.sh"
  if tunnel_is_named; then
    if tunnel_named_running; then
      return 0
    fi
    tunnel_load_named
    log "고정 URL 터널 시작 (${PUBLIC_HOSTNAME})"
    if "${ROOT}/run_named_tunnel.sh" >>"$LOG" 2>&1; then
      "${ROOT}/sync_public_url.sh" >>"$LOG" 2>&1 || true
    else
      log "고정 터널 시작 실패"
    fi
    return 0
  fi
  if pgrep -f "cloudflared tunnel --url http://127.0.0.1:${GATEWAY_PORT}" >/dev/null 2>&1; then
    return 0
  fi
  log "공개 터널 시작 (단일 URL — 게이트웨이 ${GATEWAY_PORT})"
  if "$ROOT/run_tunnel.sh" "$GATEWAY_PORT" share >>"$LOG" 2>&1; then
    "$ROOT/sync_public_url.sh" >>"$LOG" 2>&1 || true
  else
    log "터널 시작 실패"
  fi
}

print_urls() {
  "$ROOT/sync_public_url.sh" 2>/dev/null || true
}

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${old_pid:-}" ]] && kill -0 "$old_pid" 2>/dev/null; then
    print_urls
    exit 0
  fi
fi

log "=== keep_alive 시작 (단일 URL 연동) ==="
"$ROOT/disable_sleep.sh" >>"$LOG" 2>&1 || true

ensure_server
ensure_gateway
ensure_tunnel
date "+%Y-%m-%d %H:%M:%S" > "$DEPLOY_STAMP"

echo $$ > "$PID_FILE"
log "감시 PID $(cat "$PID_FILE")"
print_urls
echo "업데이트 반영: ./sync_update.sh"
echo "로그: $LOG"

# 포그라운드 감시 — LaunchAgent·nohup 환경에서 프로세스가 유지되도록 함
while true; do
  ensure_caffeinate
  ensure_server
  ensure_gateway
  ensure_tunnel
  sleep 30
done
