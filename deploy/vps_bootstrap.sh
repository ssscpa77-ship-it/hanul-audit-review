#!/usr/bin/env bash
# Ubuntu VPS 최초 1회 설치 (서버에서 root 로 실행)
# 사용: sudo bash vps_bootstrap.sh [설치경로] [도메인(선택)]
set -euo pipefail

INSTALL_ROOT="${1:-/opt/hanul-002}"
DOMAIN="${2:-}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "root 로 실행하세요: sudo bash $0" >&2
  exit 1
fi

if [[ ! -f "${INSTALL_ROOT}/app.py" ]]; then
  echo "앱 파일 없음: ${INSTALL_ROOT}/app.py" >&2
  echo "먼저 Mac에서 ./deploy/sync_to_vps.sh 로 업로드하세요." >&2
  exit 1
fi

DEPLOY_USER="${SUDO_USER:-${USER}}"
if [[ "$DEPLOY_USER" == "root" ]]; then
  DEPLOY_USER="$(ls /home 2>/dev/null | head -1 || echo ubuntu)"
fi

echo "=== Hanul VPS 설치 ==="
echo "경로: ${INSTALL_ROOT}"
echo "사용자: ${DEPLOY_USER}"
echo "도메인: ${DOMAIN:-없음 (IP로 접속)}"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip nginx ufw rsync curl \
  tesseract-ocr tesseract-ocr-kor certbot python3-certbot-nginx

chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "${INSTALL_ROOT}"

sudo -u "${DEPLOY_USER}" bash -c "
  cd '${INSTALL_ROOT}'
  python3 -m venv VENV
  ./VENV/bin/pip install -q -U pip
  ./VENV/bin/pip install -q -r requirements.txt
"

# systemd
for unit in hanul-streamlit hanul-gateway; do
  sed -e "s|HANUL_ROOT|${INSTALL_ROOT}|g" -e "s|HANUL_USER|${DEPLOY_USER}|g" \
    "${SCRIPT_DIR}/${unit}.service" > "/etc/systemd/system/${unit}.service"
done

systemctl daemon-reload
systemctl enable hanul-streamlit hanul-gateway
systemctl restart hanul-streamlit hanul-gateway

# nginx
rm -f /etc/nginx/sites-enabled/default
if [[ -n "$DOMAIN" ]]; then
  sed "s|DOMAIN_PLACEHOLDER|${DOMAIN}|g" "${SCRIPT_DIR}/nginx-hanul-https.conf" > /etc/nginx/sites-available/hanul
  # certbot 전 임시 HTTP
  sed "s|DOMAIN_PLACEHOLDER|${DOMAIN}|g" "${SCRIPT_DIR}/nginx-hanul-http.conf" > /etc/nginx/sites-available/hanul
  ln -sf /etc/nginx/sites-available/hanul /etc/nginx/sites-enabled/hanul
  nginx -t && systemctl reload nginx
  certbot certonly --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "admin@${DOMAIN}" || true
  sed "s|DOMAIN_PLACEHOLDER|${DOMAIN}|g" "${SCRIPT_DIR}/nginx-hanul-https.conf" > /etc/nginx/sites-available/hanul
  nginx -t && systemctl reload nginx
else
  cp "${SCRIPT_DIR}/nginx-hanul-http.conf" /etc/nginx/sites-available/hanul
  ln -sf /etc/nginx/sites-available/hanul /etc/nginx/sites-enabled/hanul
  nginx -t && systemctl reload nginx
fi

# firewall
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

PUBLIC_IP="$(curl -4 -s ifconfig.me || hostname -I | awk '{print $1}')"
echo ""
echo "=== 설치 완료 ==="
if [[ -n "$DOMAIN" ]]; then
  echo "소개: https://${DOMAIN}/?share=1"
  echo "앱:   https://${DOMAIN}/?app=1"
else
  echo "소개: http://${PUBLIC_IP}/?share=1"
  echo "앱:   http://${PUBLIC_IP}/?app=1"
  echo "※ 카톡 미리보기·HTTPS 권장 → 도메인 A레코드 연결 후:"
  echo "   sudo bash ${SCRIPT_DIR}/vps_bootstrap.sh ${INSTALL_ROOT} your.domain.xyz"
fi
echo ""
echo "상태 확인: systemctl status hanul-streamlit hanul-gateway nginx"
