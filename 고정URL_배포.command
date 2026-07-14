#!/bin/bash
# 고정 URL 배포 — 더블클릭 후 화면에서 Deploy 버튼만 누르세요
cd "$(dirname "$0")" || exit 1

GITHUB_USER="ssscpa77-ship-it"
REPO_NAME="hanul-audit-review"
APP_URL="https://${REPO_NAME}.streamlit.app"

clear
echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║   고정 URL 배포 (3번만 클릭)                 ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""
echo "  GitHub 업로드: GitHub_업로드_ship-it.command 먼저 실행"
echo "  배포 후 고정 URL:"
echo "  ${APP_URL}"
echo ""
echo "  ──────────────────────────────────────────────"
echo "  잠시 후 브라우저가 열립니다."
echo "  아래 3가지만 클릭하세요."
echo "  ──────────────────────────────────────────────"
echo ""
echo "  [클릭 1] GitHub 로그인 (ssscpa77-ship-it)"
echo "  [클릭 2] Repository 선택:"
echo "           ${GITHUB_USER}/${REPO_NAME}"
echo "  [클릭 3] Deploy (파란 버튼)"
echo ""
echo "  Main file 는 app.py 로 자동 선택됩니다."
echo "  Secrets 는 비워도 앱이 실행됩니다."
echo "  (AI 기능만 나중에 추가 가능)"
echo ""
read -r -p "  엔터 키를 누르면 배포 페이지가 열립니다..."

open "https://share.streamlit.io/deploy"
sleep 2
open "https://github.com/${GITHUB_USER}/${REPO_NAME}"

echo ""
echo "  배포가 끝나면 (5~10분) 아래 주소로 접속하세요:"
echo "  ${APP_URL}"
echo ""
echo "  ── 교수님 전달 메시지 (복사용) ──"
echo ""
cat <<EOF
[ABC 5기 신성섭 · 감사조서 Smart Reviewer]

한울회계법인 감사조서 자가검토 시스템 (검증용)

▶ 접속 링크 (고정)
${APP_URL}

• PDF·엑셀 조서 업로드 → 리뷰노트 자동 생성
• 규칙엔진 + Hanul DB + AI 심층 분석
• 절차누락·감리지적·4대중점 자동 점검

※ PC·태블릿 브라우저(Chrome, Safari) 권장
※ 검증용 샘플 조서로 테스트 부탁드립니다.
EOF
echo ""
echo "  ──────────────────────────────────────────────"
read -r -p "  엔터 키를 누르면 창이 닫힙니다..."
