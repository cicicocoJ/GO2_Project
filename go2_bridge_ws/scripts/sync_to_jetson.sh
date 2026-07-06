#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/go2_network.env" ]; then
  source "$SCRIPT_DIR/go2_network.env"
fi

# ============================================================
# 同步 GO2 backend bridge 源码到 Jetson
# 运行位置：笔记本 Ubuntu 22.04
#
# 功能：
#   1. 同步 ROS2 包 go2_backend_bridge
#   2. 同步后台 server.py
#   3. 同步 scripts 目录
#
# 注意：
#   只同步源码，不同步 build/install/log。
# ============================================================

JETSON_USER="${JETSON_USER:-unitree}"
JETSON_IP="${JETSON_IP:-192.168.7.149}"
JETSON_WS="${JETSON_WS:-/home/unitree/go2_bridge_ws}"

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "[INFO] Local project dir: $PROJECT_DIR"
echo "[INFO] Jetson target: ${JETSON_USER}@${JETSON_IP}:${JETSON_WS}"

echo "[INFO] Creating target directories on Jetson..."
ssh "${JETSON_USER}@${JETSON_IP}" "mkdir -p ${JETSON_WS}/src ${JETSON_WS}/scripts"

echo "[INFO] Syncing ROS2 package..."
rsync -avz --delete \
  --exclude build \
  --exclude install \
  --exclude log \
  "${PROJECT_DIR}/src/go2_backend_bridge" \
  "${JETSON_USER}@${JETSON_IP}:${JETSON_WS}/src/"

echo "[INFO] Syncing server.py..."
rsync -avz \
  "${PROJECT_DIR}/server.py" \
  "${JETSON_USER}@${JETSON_IP}:${JETSON_WS}/"

echo "[INFO] Syncing scripts..."
rsync -avz \
  "${PROJECT_DIR}/scripts/" \
  "${JETSON_USER}@${JETSON_IP}:${JETSON_WS}/scripts/"

echo "[INFO] Sync finished."
