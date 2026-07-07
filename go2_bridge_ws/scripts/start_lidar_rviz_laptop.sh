#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -f "$SCRIPT_DIR/go2_network.env" ]; then
  source "$SCRIPT_DIR/go2_network.env"
fi

JETSON_IP="${JETSON_IP:-192.168.7.149}"
LAPTOP_DDS_IFACE="${LAPTOP_DDS_IFACE:-}"
LIDAR_TOPIC="${LIDAR_TOPIC:-/lidar_points}"
LIDAR_FIXED_FRAME="${LIDAR_FIXED_FRAME:-hesai_lidar}"

# 如果没有在 go2_network.env 里指定 LAPTOP_DDS_IFACE，
# 就自动选择访问 Jetson IP 时使用的本机网卡。
if [ -z "$LAPTOP_DDS_IFACE" ]; then
  LAPTOP_DDS_IFACE="$(ip route get "$JETSON_IP" 2>/dev/null | awk '
    {
      for (i=1; i<=NF; i++) {
        if ($i == "dev") {
          print $(i+1);
          exit;
        }
      }
    }
  ')"
fi

# 再兜底选择默认上网网卡
if [ -z "$LAPTOP_DDS_IFACE" ]; then
  LAPTOP_DDS_IFACE="$(ip route get 8.8.8.8 2>/dev/null | awk '
    {
      for (i=1; i<=NF; i++) {
        if ($i == "dev") {
          print $(i+1);
          exit;
        }
      }
    }
  ')"
fi

if [ -z "$LAPTOP_DDS_IFACE" ] || ! ip link show "$LAPTOP_DDS_IFACE" >/dev/null 2>&1; then
  echo "[ERROR] Invalid LAPTOP_DDS_IFACE: ${LAPTOP_DDS_IFACE:-empty}"
  echo
  echo "Available interfaces:"
  ip -br addr
  echo
  echo "Please set LAPTOP_DDS_IFACE in scripts/go2_network.env, for example:"
  echo "  LAPTOP_DDS_IFACE=wlp2s0"
  exit 1
fi

echo "============================================================"
echo " Laptop RViz2 for XT-16"
echo " ROS2: Humble"
echo " Interface: $LAPTOP_DDS_IFACE"
echo " Topic: $LIDAR_TOPIC"
echo " Fixed Frame: $LIDAR_FIXED_FRAME"
echo " Jetson IP: $JETSON_IP"
echo "============================================================"

source /opt/ros/humble/setup.bash

export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

export CYCLONEDDS_URI="<CycloneDDS><Domain><General><Interfaces>
  <NetworkInterface name=\"$LAPTOP_DDS_IFACE\" priority=\"default\" multicast=\"default\" />
</Interfaces></General></Domain></CycloneDDS>"

ros2 daemon stop >/dev/null 2>&1 || true
ros2 daemon start >/dev/null 2>&1 || true

echo "[CHECK] ROS2 topics containing lidar:"
timeout 5s ros2 topic list | grep lidar || true

echo
echo "If $LIDAR_TOPIC exists, RViz2 will open."
echo "In RViz2:"
echo "  Fixed Frame = $LIDAR_FIXED_FRAME"
echo "  Add -> By topic -> $LIDAR_TOPIC -> PointCloud2"
echo

exec rviz2
