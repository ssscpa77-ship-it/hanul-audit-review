#!/bin/bash
# GitHub 업로드 — ssscpa77-ship-it 계정용
cd "$(dirname "$0")" || exit 1

GITHUB_USER="ssscpa77-ship-it"
REPO_NAME="hanul-audit-review"
REMOTE="https://github.com/${GITHUB_USER}/${REPO_NAME}.git"

clear
echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║   GitHub 업로드 (${GITHUB_USER})           ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""
echo "  먼저 브라우저에서 저장소를 만드세요:"
echo "  https://github.com/new"
echo "  - 이름: hanul-audit-review"
echo "  - Private"
echo "  - README 추가하지 않기"
echo ""
read -r -p "  저장소 만든 뒤 엔터..."

if ! command -v gh >/dev/null 2>&1; then
  echo "  gh 설치: brew install gh"
  read -r -p "  엔터..."
  exit 1
fi

echo ""
echo "  GitHub 로그인 (ssscpa77-ship-it 계정으로!)"
gh auth login -h github.com -p https -w

echo ""
echo "  KB 압축 파일 준비 (Streamlit Cloud용)..."
if [[ -f kb_store/hanul_kb.sqlite ]] && [[ ! -f kb_store/hanul_kb.sqlite.gz || kb_store/hanul_kb.sqlite -nt kb_store/hanul_kb.sqlite.gz ]]; then
  gzip -9 -k -f kb_store/hanul_kb.sqlite
fi

git remote set-url origin "$REMOTE" 2>/dev/null || git remote add origin "$REMOTE"

echo ""
echo "  업로드 중... (1~3분)"
git add knowledge_base.py requirements.txt .streamlit/config.toml .gitignore .gitattributes kb_store/hanul_kb.sqlite.gz
git rm --cached kb_store/hanul_kb.sqlite 2>/dev/null || true
git rm packages.txt 2>/dev/null || true
git add -A
git commit -m "Streamlit Cloud: KB gzip 배포 수정" 2>/dev/null || true
if git push -u origin main; then
  echo ""
  echo "  ✅ 업로드 완료!"
  echo "  https://github.com/${GITHUB_USER}/${REPO_NAME}"
  echo ""
  echo "  다음: 고정URL_배포.command 실행"
else
  echo ""
  echo "  ❌ 실패 — ssscpa77-ship-it 로 로그인했는지 확인"
fi
echo ""
read -r -p "  엔터..."
