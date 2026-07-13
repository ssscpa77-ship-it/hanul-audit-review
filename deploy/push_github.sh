#!/usr/bin/env bash
# GitHub 푸시 (저장소 생성 후 Mac 터미널에서 실행)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

GITHUB_USER="${GITHUB_USER:-ssscpa77}"
REPO_NAME="${REPO_NAME:-hanul-audit-review}"
REMOTE="https://github.com/${GITHUB_USER}/${REPO_NAME}.git"

echo "=== GitHub 푸시 ==="
echo "대상: ${GITHUB_USER}/${REPO_NAME}"
echo ""

HTTP_CODE="$(curl -s -o /dev/null -w "%{http_code}" "https://api.github.com/repos/${GITHUB_USER}/${REPO_NAME}")"
if [[ "$HTTP_CODE" != "200" ]]; then
  echo "GitHub 저장소가 아직 없습니다 (HTTP ${HTTP_CODE})."
  echo ""
  echo "먼저 브라우저에서 저장소를 만드세요:"
  echo "  https://github.com/new"
  echo "  - Repository name: ${REPO_NAME}"
  echo "  - Private 선택"
  echo "  - README / .gitignore 추가하지 않기"
  echo ""
  exit 1
fi

if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "$REMOTE"
else
  git remote add origin "$REMOTE"
fi

echo "origin → $REMOTE"
echo ""
echo "푸시 중... (KB 145MB — 1~3분 소요)"
git push -u origin main

echo ""
echo "푸시 완료. 다음: https://share.streamlit.io → Create app"
