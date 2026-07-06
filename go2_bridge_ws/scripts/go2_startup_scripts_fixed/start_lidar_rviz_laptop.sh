#!/usr/bin/env bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/go2_network.env" ]; then
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/go2_network.env"
fi

# RViz runs on the laptop. Pick the laptop DDS interface.
# For current hotspot/WiFi mode, this is usually wlp2s0.
# For old wired GO2-network mode, run:
#   LAPTOP_DDS_IFACE=enx00e04c36178d bash scripts/start_lidar_rviz_laptop.sh
LAPTOP_DDS_IFACE="${LAPTOP_DDS_IFACE:-}"

if [ -z "$LAPTOP_DDS_IFACE" ]; then
  LAPTOP_DDS_IFACE="$(ip route get 8.8.8.8 2>/dev/null | awk '{for(i=1;i<=NF;i++){if($i=="dev"){print $(i+1); exit}}}')"
fi

if [ -z "$LAPTOP_DDS_IFACE" ]; then
  echo "[ERROR] Could not auto-detect laptop DDS interface."
  echo "Set it manually, for example:"
  echo "  LAPTOP_DDS_IFACE=wlp2s0 bash scripts/start_lidar_rviz_laptop.sh"
  exit 1
fi

LIDAR_TOPIC="${LIDAR_TOPIC:-/lidar_points}"
LIDAR_FIXED_FRAME="${LIDAR_FIXED_FRAME:-hesai_lidar}"

echo "============================================================"
echo " Laptop RViz2 for XT-16"
echo " ROS2: Humble"
echo " Interface: $LAPTOP_DDS_IFACE"
echo " Topic: $LIDAR_TOPIC"
echo " Fixed Frame: $LIDAR_FIXED_FRAME"
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
ros2 topic list | grep lidar || true

echo
echo "If $LIDAR_TOPIC exists, RViz2 will open."
echo "In RViz2:"
echo "  Fixed Frame = $LIDAR_FIXED_FRAME"
echo "  Add -> By topic -> $LIDAR_TOPIC -> PointCloud2"
echo

exec rviz2
