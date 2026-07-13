#!/bin/bash
# GitHub 업로드 — 더블클릭만 하면 됩니다 (macOS)
cd "$(dirname "$0")" || exit 1

GITHUB_USER="ssscpa77"
# 영문 저장소 이름 (한글 URL 오류 방지)
REPO_NAME="hanul-audit-review"
REMOTE="https://github.com/${GITHUB_USER}/${REPO_NAME}.git"

echo "================================================"
echo "  GitHub 업로드 (자동)"
echo "  저장소: ${GITHUB_USER}/${REPO_NAME}"
echo "================================================"
echo ""

if ! command -v git >/dev/null 2>&1; then
  echo "[오류] git 이 없습니다."
  read -r -p "엔터 키를 누르면 창이 닫힙니다..."
  exit 1
fi

# GitHub CLI 설치 (로그인용)
if ! command -v gh >/dev/null 2>&1; then
  echo "[준비] GitHub 로그인 도구 설치 중..."
  if command -v brew >/dev/null 2>&1; then
    brew install gh
  else
    echo "[오류] Homebrew 없음. https://cli.github.com 에서 gh 설치 후 다시 실행하세요."
    read -r -p "엔터 키를 누르면 창이 닫힙니다..."
    exit 1
  fi
fi

# GitHub 로그인 (브라우저에서 승인)
if ! gh auth status >/dev/null 2>&1; then
  echo ""
  echo "  ▶ GitHub 로그인 창이 열립니다."
  echo "  ▶ ssscpa77 계정으로 로그인 → Authorize 클릭"
  echo ""
  gh auth login -h github.com -p https -w
fi

# 저장소 없으면 자동 생성 (Private)
if ! gh repo view "${GITHUB_USER}/${REPO_NAME}" >/dev/null 2>&1; then
  echo ""
  echo "[준비] GitHub 저장소 생성 중: ${REPO_NAME} (Private)"
  gh repo create "${REPO_NAME}" --private --source=. --remote=origin --push=false 2>/dev/null \
    || gh repo create "${GITHUB_USER}/${REPO_NAME}" --private
fi

git remote set-url origin "$REMOTE" 2>/dev/null || git remote add origin "$REMOTE"

echo ""
echo "[1/3] 연결 확인..."
if ! git ls-remote origin >/dev/null 2>&1; then
  echo "[오류] 저장소에 연결할 수 없습니다."
  echo "  브라우저에서 저장소를 확인해 주세요:"
  echo "  https://github.com/${GITHUB_USER}/${REPO_NAME}"
  read -r -p "엔터 키를 누르면 창이 닫힙니다..."
  exit 1
fi

echo "[2/3] GitHub 와 합치는 중..."
git pull origin main --allow-unrelated-histories --no-edit 2>/dev/null || true

echo "[3/3] 업로드 중... (1~3분, KB 파일 포함)"
if git push -u origin main; then
  echo ""
  echo "================================================"
  echo "  업로드 성공!"
  echo "  https://github.com/${GITHUB_USER}/${REPO_NAME}"
  echo "================================================"
  echo ""
  echo "  Streamlit 배포 페이지를 엽니다..."
  sleep 2
  open "https://share.streamlit.io/deploy"
  echo ""
  echo "  Streamlit 화면에서:"
  echo "  - Repository: ${GITHUB_USER}/${REPO_NAME}"
  echo "  - Main file: app.py"
  echo "  - Deploy 클릭"
else
  echo ""
  echo "[오류] 업로드 실패. 이 창 캡처를 보내 주세요."
fi

echo ""
read -r -p "엔터 키를 누르면 창이 닫힙니다..."
