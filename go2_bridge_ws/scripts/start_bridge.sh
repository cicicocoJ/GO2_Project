#!/usr/bin/env bash
set -e

# ============================================================
# 启动 GO2 backend bridge 节点
# 运行位置：Jetson Ubuntu 20.04 + ROS2 Foxy
#
# 功能：
#   启动 backend_client_node
#
# 默认：
#   robot_id = GO2_001
#   backend_ip = 192.168.123.99
#   backend_port = 8000
#
# 使用方法：
#   bash scripts/start_bridge.sh
#
# 指定后台 IP：
#   bash scripts/start_bridge.sh 192.168.123.99
#
# 或者：
#   BACKEND_IP=192.168.123.99 bash scripts/start_bridge.sh
# ============================================================

ROBOT_ID="${ROBOT_ID:-GO2_001}"
BACKEND_IP="${1:-${BACKEND_IP:-192.168.123.99}}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
JETSON_WS="${JETSON_WS:-/home/unitree/go2_bridge_ws}"

SERVER_URL="ws://${BACKEND_IP}:${BACKEND_PORT}/ws/robot/${ROBOT_ID}"

cd "$JETSON_WS"

echo "[INFO] Workspace: $JETSON_WS"
echo "[INFO] Robot ID: $ROBOT_ID"
echo "[INFO] Backend URL: $SERVER_URL"

source /opt/ros/foxy/setup.bash
source ~/cyclonedds_ws/install/setup.bash
source install/setup.bash

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI='<CycloneDDS><Domain><General><Interfaces>
    <NetworkInterface name="eth0" priority="default" multicast="default" />
</Interfaces></General></Domain></CycloneDDS>'

ros2 run go2_backend_bridge backend_client_node \
  --ros-args \
  -p robot_id:="${ROBOT_ID}" \
  -p server_url:="${SERVER_URL}"
