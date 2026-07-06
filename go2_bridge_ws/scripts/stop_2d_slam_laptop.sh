#!/usr/bin/env bash

PID_FILE=/tmp/go2_2d_slam_pids.txt

echo "============================================================"
echo " Stop GO2 + XT-16 2D SLAM Laptop Pipeline"
echo "============================================================"

if [ -f "$PID_FILE" ]; then
  echo "[INFO] Kill PIDs from $PID_FILE"
  while read -r pid; do
    if [ -n "$pid" ]; then
      kill "$pid" 2>/dev/null || true
    fi
  done < "$PID_FILE"
  rm -f "$PID_FILE"
fi

pkill -f pointcloud_to_laserscan_node || true
pkill -f scan_stamp_relay.py || true
pkill -f odom_to_tf_bridge_now.py || true
pkill -f async_slam_toolbox_node || true
pkill -f "static_transform_publisher.*hesai_lidar" || true

echo "[OK] 2D SLAM pipeline stopped."
echo "============================================================"
