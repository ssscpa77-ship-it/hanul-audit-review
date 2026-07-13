#!/bin/bash
# 감사조서 자가검토 — 더블클릭 실행 파일 (macOS)
# 이 파일을 더블클릭하면 앱이 실행되고 브라우저가 열립니다.

# 스크립트가 있는 폴더로 이동 (어디서 실행하든 동작)
cd "$(dirname "$0")" || exit 1

echo "================================================"
echo "  감사조서 자가검토 시스템을 시작합니다"
echo "================================================"
echo "  실행 후 브라우저가 자동으로 열립니다."
echo "  종료하려면 이 창에서 Control(^) + C 를 누르세요."
echo "------------------------------------------------"

# 가상환경(VENV) 확인
if [ -x "VENV/bin/streamlit" ]; then
    STREAMLIT="VENV/bin/streamlit"
elif command -v streamlit >/dev/null 2>&1; then
    STREAMLIT="streamlit"
else
    echo "[오류] streamlit 을 찾을 수 없습니다."
    echo "       아래 명령으로 먼저 설치하세요:"
    echo "       python3 -m venv VENV && VENV/bin/pip install -r requirements.txt"
    echo ""
    read -r -p "엔터 키를 누르면 창이 닫힙니다..."
    exit 1
fi

# 앱 실행 (기본적으로 브라우저가 자동으로 열립니다)
"$STREAMLIT" run app.py

# 서버 종료 후 창이 바로 닫히지 않도록 대기
echo ""
read -r -p "앱이 종료되었습니다. 엔터 키를 누르면 창이 닫힙니다..."
