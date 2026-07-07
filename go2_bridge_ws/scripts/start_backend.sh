#!/usr/bin/env bash
set -e

# ============================================================
# 启动 GO2 后台 Demo
# 运行位置：笔记本 Ubuntu 22.04
#
# 功能：
#   启动 FastAPI 后台 server.py
#
# 默认端口：
#   8000
#
# 使用方法：
#   bash scripts/start_backend.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -f "$SCRIPT_DIR/go2_network.env" ]; then
  source "$SCRIPT_DIR/go2_network.env"
fi

BACKEND_PORT="${BACKEND_PORT:-8000}"
JETSON_IP="${JETSON_IP:-192.168.7.149}"
JETSON_VIDEO_PORT="${JETSON_VIDEO_PORT:-8081}"
GO2_VIDEO_STREAM_URL="${GO2_VIDEO_STREAM_URL:-http://${JETSON_IP}:${JETSON_VIDEO_PORT}/video_feed}"

export JETSON_IP
export JETSON_VIDEO_PORT
export GO2_VIDEO_STREAM_URL

cd "$PROJECT_DIR"

echo "[INFO] Project dir: $PROJECT_DIR"
echo "[INFO] Starting FastAPI backend on 0.0.0.0:${BACKEND_PORT}"
echo "[INFO] GO2 video stream: ${GO2_VIDEO_STREAM_URL}"

python3 -m uvicorn server:app --host 0.0.0.0 --port "${BACKEND_PORT}"
