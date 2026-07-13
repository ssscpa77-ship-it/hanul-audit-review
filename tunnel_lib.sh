#!/usr/bin/env bash
# 터널 공통 — Quick(임시) / Named(고정 URL) 모드
set -euo pipefail

tunnel_root() {
  cd "$(dirname "${BASH_SOURCE[0]}")" && pwd
}

tunnel_named_env() {
  local root
  root="$(tunnel_root)"
  [[ -f "${root}/.tunnel.named.env" ]] && echo "${root}/.tunnel.named.env" || return 1
}

tunnel_is_named() {
  tunnel_named_env >/dev/null 2>&1
}

tunnel_load_named() {
  # shellcheck disable=SC1090
  source "$(tunnel_named_env)"
}

tunnel_gateway_port() {
  echo "${SHARE_GATEWAY_PORT:-8506}"
}

tunnel_public_url() {
  local root url
  root="$(tunnel_root)"
  if tunnel_is_named; then
    tunnel_load_named
    echo "${PUBLIC_URL:-https://${PUBLIC_HOSTNAME}}"
    return 0
  fi
  url=""
  [[ -f "${root}/.tunnel.url.stable" ]] && url="$(tr -d '[:space:]' < "${root}/.tunnel.url.stable")"
  [[ -z "$url" && -f "${root}/.tunnel.url" ]] && url="$(tr -d '[:space:]' < "${root}/.tunnel.url")"
  [[ -n "$url" ]] && echo "$url"
}

tunnel_quick_running() {
  local port="${1:-$(tunnel_gateway_port)}"
  pgrep -f "cloudflared tunnel --url http://127.0.0.1:${port}" >/dev/null 2>&1
}

tunnel_named_running() {
  tunnel_load_named
  pgrep -f "cloudflared tunnel --config ${CONFIG_FILE} run ${TUNNEL_NAME}" >/dev/null 2>&1 \
    || pgrep -f "cloudflared tunnel run ${TUNNEL_NAME}" >/dev/null 2>&1
}

tunnel_any_running() {
  if tunnel_is_named; then
    tunnel_named_running
  else
    tunnel_quick_running "$@"
  fi
}

tunnel_write_public_files() {
  local root url
  root="$(tunnel_root)"
  url="$(tunnel_public_url || true)"
  [[ -z "${url:-}" ]] && return 1
  echo "$url" > "${root}/.tunnel.url"
  echo "$url" > "${root}/.tunnel.url.stable"
}
