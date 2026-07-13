#!/usr/bin/env bash
# Mac → VPS 코드·KB 동기화
# 사용: ./deploy/sync_to_vps.sh user@서버IP [원격경로]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-}"
REMOTE_DIR="${2:-/opt/hanul-002}"

if [[ -z "$TARGET" ]]; then
  echo "사용법: $0 user@VPS_IP [/opt/hanul-002]" >&2
  echo "예:     $0 ubuntu@123.45.67.89" >&2
  exit 1
fi

echo "=== VPS 동기화 → ${TARGET}:${REMOTE_DIR} ==="

ssh "$TARGET" "sudo mkdir -p '${REMOTE_DIR}' && sudo chown -R \$(whoami):\$(whoami) '${REMOTE_DIR}'"

rsync -avz --delete \
  --exclude 'VENV/' \
  --exclude '.git/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '.server.log' \
  --exclude '.gateway.log' \
  --exclude '.tunnel*' \
  --exclude '.keep_alive*' \
  --exclude '.deploy_stamp' \
  --exclude '.cursor/' \
  "${ROOT}/" "${TARGET}:${REMOTE_DIR}/"

if [[ -f "${ROOT}/.env" ]]; then
  rsync -avz "${ROOT}/.env" "${TARGET}:${REMOTE_DIR}/.env"
  echo "✓ .env 전송"
else
  echo "⚠ .env 없음 — 서버에서 deploy/env.vps.example 참고"
fi

echo ""
echo "서버 최초 설치(1회):"
echo "  ssh ${TARGET}"
echo "  sudo bash ${REMOTE_DIR}/deploy/vps_bootstrap.sh ${REMOTE_DIR}"
echo ""
echo "코드만 갱신 후 재시작:"
echo "  ssh ${TARGET} 'sudo systemctl restart hanul-streamlit hanul-gateway'"
