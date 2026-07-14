#!/bin/bash
# 교수님 검증용 — Mac 터미널에서 실행 (Cursor 종료해도 유지)
cd "$(dirname "$0")" || exit 1

echo "================================================"
echo "  감사조서 자가검토 — 상시 실행"
echo "  이 창을 닫지 마세요 (종료 시 접속 불가)"
echo "================================================"
echo ""

chmod +x keep_alive.sh sync_public_url.sh 2>/dev/null || true
./keep_alive.sh
