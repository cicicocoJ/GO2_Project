#!/usr/bin/env bash
set -euo pipefail

WS="/home/unitree/hesai_ws"
PID_DIR="$WS/logs/pids"

echo "============================================================"
echo " XT-16 / Hesai Lidar Stop"
echo "============================================================"

if [ -f "$PID_DIR/hesai_lidar.pid" ]; then
  PID="$(cat "$PID_DIR/hesai_lidar.pid" || true)"

  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    echo "[STOP] hesai_lidar pid=$PID"
    kill "$PID" 2>/dev/null || true
    sleep 0.8

    if kill -0 "$PID" 2>/dev/null; then
      echo "[KILL] hesai_lidar pid=$PID"
      kill -9 "$PID" 2>/dev/null || true
    fi
  fi

  rm -f "$PID_DIR/hesai_lidar.pid"
fi

pkill -f "hesai_ros_driver" 2>/dev/null || true
pkill -f "rviz2" 2>/dev/null || true

echo "[OK] Hesai lidar stopped."
