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

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"

cd "$PROJECT_DIR"

echo "[INFO] Project dir: $PROJECT_DIR"
echo "[INFO] Starting FastAPI backend on 0.0.0.0:${BACKEND_PORT}"

python3 -m uvicorn server:app --host 0.0.0.0 --port "${BACKEND_PORT}"
