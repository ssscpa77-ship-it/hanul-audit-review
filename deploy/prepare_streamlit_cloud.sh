#!/usr/bin/env bash
# Streamlit Community Cloud 배포 준비 (Mac에서 1회)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Streamlit Cloud 배포 준비 ==="

for cmd in git git-lfs; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "필요: $cmd — brew install git git-lfs" >&2
    exit 1
  fi
done

if [[ ! -f "${ROOT}/kb_store/hanul_kb.sqlite" ]]; then
  echo "KB 없음: kb_store/hanul_kb.sqlite" >&2
  echo "로컬에서 build_index.py 실행 후 다시 시도하세요." >&2
  exit 1
fi

KB_MB="$(du -m "${ROOT}/kb_store/hanul_kb.sqlite" | awk '{print $1}')"
echo "KB 크기: ${KB_MB}MB (Git LFS 사용)"

git init -b main 2>/dev/null || git checkout -B main 2>/dev/null || true
git lfs install --local 2>/dev/null || git lfs install

git add .gitattributes .gitignore packages.txt requirements.txt
git add app.py config.py knowledge_base.py share_gateway.py 2>/dev/null || true
git add *.py scripts/ share/ .streamlit/ deploy/ 2>/dev/null || true
git add kb_store/hanul_kb.sqlite

# 나머지 추적 파일
git add -A
git status --short | head -40

echo ""
echo "=== 다음 단계 (직접 진행) ==="
echo ""
echo "1) GitHub 에 **비공개(Private)** 저장소 생성"
echo "   예: hanul-audit-review"
echo ""
echo "2) 커밋 & 푸시:"
echo "   git commit -m \"Streamlit Cloud 배포\""
echo "   git remote add origin https://github.com/YOUR_ID/hanul-audit-review.git"
echo "   git push -u origin main"
echo ""
echo "3) https://share.streamlit.io 접속 → New app"
echo "   - Repository: YOUR_ID/hanul-audit-review"
echo "   - Branch: main"
echo "   - Main file: app.py"
echo ""
echo "4) Advanced settings → Secrets"
echo "   .streamlit/secrets.toml.example 내용 붙여넣기 + OPENAI_API_KEY 입력"
echo ""
echo "5) Deploy → 고정 URL:"
echo "   https://YOUR-APP-NAME.streamlit.app"
echo ""
echo "자세한 안내: deploy/STREAMLIT_CLOUD.md"
