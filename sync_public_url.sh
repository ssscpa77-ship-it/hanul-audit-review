#!/usr/bin/env bash
# 공개 URL 고정·카톡 메시지 동기화
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=tunnel_lib.sh
source "${ROOT}/tunnel_lib.sh"

CURRENT="${ROOT}/.tunnel.url"
STABLE="${ROOT}/.tunnel.url.stable"
KAKAO="${ROOT}/.kakao_message_ready.txt"
TEMPLATE="${ROOT}/share/kakao_message.txt"

if tunnel_is_named; then
  url="$(tunnel_public_url)"
  echo "$url" > "$CURRENT"
  echo "$url" > "$STABLE"
  echo "고정 URL (Named Tunnel): $url"
else
  url=""
  [[ -f "$CURRENT" ]] && url="$(tr -d '[:space:]' < "$CURRENT")"
  if [[ -z "$url" ]]; then
    echo "공개 URL 없음 — ./run_tunnel.sh 8506 share 또는 ./setup_named_tunnel.sh" >&2
    exit 1
  fi
  if [[ ! -f "$STABLE" ]]; then
    echo "$url" > "$STABLE"
    echo "고정 URL 저장: $url"
  else
    stable="$(tr -d '[:space:]' < "$STABLE")"
    if [[ "$stable" != "$url" ]]; then
      echo "⚠ 임시 터널 URL 변경됨"
      echo "  이전(교수님 전달): $stable"
      echo "  현재: $url"
      echo "  ※ 영구 고정: ./setup_named_tunnel.sh"
    else
      echo "임시 URL 유지: $stable"
    fi
  fi
fi

share_url="$(tr -d '[:space:]' < "$STABLE")"
kakao_url="${share_url}/?share=1"
if [[ -f "$TEMPLATE" ]]; then
  sed "s|{{SHARE_URL}}|$kakao_url|" "$TEMPLATE" > "$KAKAO"
  echo "카톡 메시지 갱신: $KAKAO"
fi

echo ""
echo "교수님 URL: $kakao_url"
echo "앱 바로가기: ${share_url}?app=1"
