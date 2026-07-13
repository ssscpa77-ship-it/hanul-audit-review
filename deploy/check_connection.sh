#!/usr/bin/env bash
# GitHub ↔ Streamlit Cloud 연결 상태 점검
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

GITHUB_USER="${GITHUB_USER:-ssscpa77}"
REPO_NAME="${REPO_NAME:-hanul-audit-review}"
APP_URL="https://${REPO_NAME}.streamlit.app"

echo "=== 연결 상태 점검 ==="
echo "GitHub: ${GITHUB_USER}/${REPO_NAME}"
echo ""

# 1) 로컬 git
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "[OK] 로컬 Git 저장소"
  git log -1 --oneline
else
  echo "[FAIL] 로컬 Git 없음 — deploy/prepare_streamlit_cloud.sh 실행"
  exit 1
fi

if git remote get-url origin >/dev/null 2>&1; then
  echo "[OK] origin: $(git remote get-url origin)"
else
  echo "[FAIL] origin 미설정"
  echo "  → git remote add origin https://github.com/${GITHUB_USER}/${REPO_NAME}.git"
fi

if git rev-parse --abbrev-ref --symbolic-full-name @{u} >/dev/null 2>&1; then
  echo "[OK] upstream 연결됨 ($(git rev-parse --abbrev-ref @{u}))"
else
  echo "[WARN] 아직 push 안 됨 — git push -u origin main 필요"
fi

echo ""

# 2) GitHub 저장소
HTTP_CODE="$(curl -s -o /dev/null -w "%{http_code}" "https://api.github.com/repos/${GITHUB_USER}/${REPO_NAME}")"
if [[ "$HTTP_CODE" == "200" ]]; then
  echo "[OK] GitHub 저장소 존재"
elif [[ "$HTTP_CODE" == "404" ]]; then
  echo "[FAIL] GitHub 저장소 없음 (404)"
  echo "  → https://github.com/new 에서 Private 저장소 생성"
  echo "     이름: ${REPO_NAME}"
  echo "     README/.gitignore 추가하지 말 것"
else
  echo "[?] GitHub 응답: HTTP ${HTTP_CODE}"
fi

echo ""

# 3) Streamlit 앱
ST_CODE="$(curl -s -o /dev/null -w "%{http_code}" -L "${APP_URL}")"
if [[ "$ST_CODE" == "200" ]]; then
  echo "[OK] Streamlit 앱 접속 가능: ${APP_URL}"
elif [[ "$ST_CODE" == "404" || "$ST_CODE" == "403" ]]; then
  echo "[FAIL] Streamlit 앱 미배포 또는 권한 없음"
  echo "  → https://share.streamlit.io → Create app"
  echo "     Repository: ${GITHUB_USER}/${REPO_NAME}"
  echo "     Main file: app.py"
else
  echo "[?] Streamlit 응답: HTTP ${ST_CODE} (배포 전이면 정상)"
  echo "  예상 URL: ${APP_URL}"
fi

echo ""
echo "=== 다음에 할 일 ==="
if [[ "$HTTP_CODE" == "404" ]]; then
  echo "1) GitHub 저장소 생성 (위 링크)"
  echo "2) Mac 터미널: cd ${ROOT} && git push -u origin main"
  echo "3) share.streamlit.io 에서 Deploy"
elif ! git rev-parse --abbrev-ref --symbolic-full-name @{u} >/dev/null 2>&1; then
  echo "1) Mac 터미널: cd ${ROOT} && git push -u origin main"
  echo "2) share.streamlit.io 에서 Deploy"
else
  echo "1) share.streamlit.io → Create app → Deploy"
  echo "2) Running 상태 확인 후 ${APP_URL} 접속"
fi
