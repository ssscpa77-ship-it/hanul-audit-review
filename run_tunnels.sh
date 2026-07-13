#!/usr/bin/env bash
# 단일 공개 URL 터널 (게이트웨이 8506 — 랜딩+앱 통합)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
"$ROOT/run_tunnel.sh" 8506 share
"$ROOT/sync_public_url.sh"
