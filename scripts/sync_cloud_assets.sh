#!/bin/bash
# Hanul DB-SSS → 클라우드 배포용 자산 동기화 (Mac에서 실행)
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1

SRC="${HANUL_DB_PATH:-$HOME/Desktop/Hanul DB-SSS}"
if [[ ! -d "$SRC" ]]; then
  echo "❌ Hanul DB 폴더 없음: $SRC"
  exit 1
fi

echo "원본: $SRC"
mkdir -p share/exports share/assets/hanul_db

# 4대 중점 PDF (원문보기)
LISTED=$(find "$SRC/4대 중점사항 감리대상" -name '상장_4대 중점사항_2026년.pdf' 2>/dev/null | head -1)
UNLISTED=$(find "$SRC/4대 중점사항 감리대상" -name '비상장_4대 중점사항_2026년.pdf' 2>/dev/null | head -1)
[[ -n "$LISTED" ]] && cp "$LISTED" share/exports/focus_listed.pdf && echo "✓ focus_listed.pdf"
[[ -n "$UNLISTED" ]] && cp "$UNLISTED" share/exports/focus_unlisted.pdf && echo "✓ focus_unlisted.pdf"

# 4대 중점 폴더 미러 (선택)
rsync -a "$SRC/4대 중점사항 감리대상/" "share/assets/hanul_db/4대 중점사항 감리대상/"
echo "✓ share/assets/hanul_db/4대 중점사항 감리대상"

echo ""
echo "다음: GitHub_업로드_ship-it.command 실행 → Streamlit 자동 재배포"
