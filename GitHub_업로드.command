#!/bin/bash
# GitHub 업로드 — 더블클릭만 하면 됩니다 (macOS)
cd "$(dirname "$0")" || exit 1

GITHUB_USER="ssscpa77"
REPO_NAME="한울-감사-검토"
REMOTE="https://github.com/${GITHUB_USER}/${REPO_NAME}.git"

echo "================================================"
echo "  GitHub 업로드 (자동)"
echo "  저장소: ${GITHUB_USER}/${REPO_NAME}"
echo "================================================"
echo ""
echo "  잠시 후 GitHub 로그인 창이 뜨면"
echo "  ssscpa77 계정으로 승인(Authorize) 해 주세요."
echo "------------------------------------------------"
echo ""

if ! command -v git >/dev/null 2>&1; then
  echo "[오류] git 이 없습니다. Xcode Command Line Tools 설치가 필요합니다."
  read -r -p "엔터 키를 누르면 창이 닫힙니다..."
  exit 1
fi

git remote set-url origin "$REMOTE" 2>/dev/null || git remote add origin "$REMOTE"

echo "[1/3] GitHub README 와 합치는 중..."
git pull origin main --allow-unrelated-histories --no-edit 2>/dev/null || true

echo "[2/3] GitHub 에 업로드 중... (1~3분)"
if git push -u origin main; then
  echo ""
  echo "================================================"
  echo "  업로드 성공!"
  echo "  https://github.com/${GITHUB_USER}/${REPO_NAME}"
  echo "================================================"
  echo ""
  echo "[3/3] Streamlit 배포 페이지를 엽니다..."
  sleep 2
  open "https://share.streamlit.io/deploy"
  echo ""
  echo "  Streamlit 화면에서:"
  echo "  - Repository: ${GITHUB_USER}/${REPO_NAME}"
  echo "  - Main file: app.py"
  echo "  - Deploy 클릭"
else
  echo ""
  echo "[오류] 업로드 실패 — GitHub 로그인을 다시 시도해 주세요."
  echo "  또는 이 창의 오류 메시지를 캡처해서 보내 주세요."
fi

echo ""
read -r -p "엔터 키를 누르면 창이 닫힙니다..."
