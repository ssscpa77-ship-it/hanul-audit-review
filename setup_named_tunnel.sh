#!/usr/bin/env bash
# Cloudflare Named Tunnel + 자체 도메인 — 교수님용 URL 영구 고정
#
# 사전 준비 (1회, 약 10분):
#   1) https://dash.cloudflare.com 무료 가입
#   2) 도메인 구매 후 Cloudflare에 사이트 추가 (DNS 네임서버 Cloudflare로)
#      저렴 예: .xyz / .site — Cloudflare Registrar 또는 Namecheap 등 (연 1~10달러)
#   3) 터미널에서 이 스크립트 실행 → 브라우저 로그인 1회
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

NAMED_ENV="${ROOT}/.tunnel.named.env"
CF_DIR="${ROOT}/cloudflared"
CONFIG_FILE="${CF_DIR}/config.yml"
GATEWAY_PORT="${SHARE_GATEWAY_PORT:-8506}"
TUNNEL_NAME="${TUNNEL_NAME:-hanul-audit-review}"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared 설치: brew install cloudflared" >&2
  exit 1
fi

echo "=== Cloudflare 고정 URL 설정 ==="
echo ""
echo "Quick Tunnel(trycloudflare.com)은 재시작마다 URL이 바뀝니다."
echo "Named Tunnel + 본인 도메인이면 URL이 고정됩니다. (Cloudflare 터널 요금: 무료)"
echo ""

if [[ -f "$NAMED_ENV" ]]; then
  # shellcheck disable=SC1090
  source "$NAMED_ENV"
  echo "이미 설정됨: ${PUBLIC_URL:-https://${PUBLIC_HOSTNAME}}"
  read -r -p "다시 설정하시겠습니까? [y/N] " redo
  [[ "${redo:-N}" =~ ^[Yy]$ ]] || exit 0
fi

read -r -p "Cloudflare에 등록한 도메인 (예: hanul-review.xyz): " DOMAIN
DOMAIN="${DOMAIN#https://}"
DOMAIN="${DOMAIN%%/*}"
DOMAIN="${DOMAIN#www.}"
[[ -n "$DOMAIN" ]] || { echo "도메인을 입력하세요." >&2; exit 1; }

read -r -p "서브도메인 [review]: " SUB
SUB="${SUB:-review}"
HOSTNAME="${SUB}.${DOMAIN}"
PUBLIC_URL="https://${HOSTNAME}"

echo ""
echo "고정 URL: ${PUBLIC_URL}"
echo ""

if [[ ! -f "${HOME}/.cloudflared/cert.pem" ]]; then
  echo "브라우저가 열립니다. Cloudflare 계정으로 로그인하고 도메인 ${DOMAIN} 을 승인하세요."
  cloudflared tunnel login
fi

if ! cloudflared tunnel list 2>/dev/null | awk '{print $2}' | grep -qx "$TUNNEL_NAME"; then
  echo "터널 생성: ${TUNNEL_NAME}"
  cloudflared tunnel create "$TUNNEL_NAME"
fi

TUNNEL_ID="$(cloudflared tunnel list 2>/dev/null | awk -v n="$TUNNEL_NAME" '$2 == n {print $1; exit}')"
[[ -n "${TUNNEL_ID:-}" ]] || { echo "터널 ID 확인 실패" >&2; exit 1; }

CRED_FILE="${HOME}/.cloudflared/${TUNNEL_ID}.json"
[[ -f "$CRED_FILE" ]] || { echo "인증 파일 없음: ${CRED_FILE}" >&2; exit 1; }

echo "DNS 연결: ${HOSTNAME} → 터널"
cloudflared tunnel route dns "$TUNNEL_NAME" "$HOSTNAME" || true

mkdir -p "$CF_DIR"
cat > "$CONFIG_FILE" <<EOF
# 한울 감사조서 Smart Reviewer — 고정 URL 터널
tunnel: ${TUNNEL_ID}
credentials-file: ${CRED_FILE}

ingress:
  - hostname: ${HOSTNAME}
    service: http://127.0.0.1:${GATEWAY_PORT}
  - service: http_status:404
EOF

cat > "$NAMED_ENV" <<EOF
# 고정 공개 URL (자동 생성 — setup_named_tunnel.sh)
TUNNEL_NAME=${TUNNEL_NAME}
TUNNEL_ID=${TUNNEL_ID}
PUBLIC_HOSTNAME=${HOSTNAME}
PUBLIC_URL=${PUBLIC_URL}
CONFIG_FILE=${CONFIG_FILE}
SHARE_GATEWAY_PORT=${GATEWAY_PORT}
EOF

echo "${PUBLIC_URL}" > "${ROOT}/.tunnel.url"
echo "${PUBLIC_URL}" > "${ROOT}/.tunnel.url.stable"

# Quick 터널 중지
pkill -f "cloudflared tunnel --url http://127.0.0.1:${GATEWAY_PORT}" 2>/dev/null || true

if lsof -i :"$GATEWAY_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  "${ROOT}/run_named_tunnel.sh"
else
  echo "게이트웨이 없음 — ./restart_all.sh 실행 후 ./run_named_tunnel.sh"
fi

"${ROOT}/sync_public_url.sh" 2>/dev/null || true

echo ""
echo "=== 완료 ==="
echo "고정 URL (교수님): ${PUBLIC_URL}/?share=1"
echo "앱 바로가기:       ${PUBLIC_URL}/?app=1"
echo ""
echo "재부팅 후: cd ${ROOT} && ./keep_alive.sh"
echo "URL은 변경되지 않습니다."
