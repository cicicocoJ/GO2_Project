#!/usr/bin/env bash
set -euo pipefail

WS="/home/unitree/go2_bridge_ws"
PID_DIR="$WS/logs/pids"

echo "============================================================"
echo " GO2 Robot Side Stop"
echo "============================================================"

stop_one() {
  local name="$1"
  local pid_file="$PID_DIR/${name}.pid"

  if [ ! -f "$pid_file" ]; then
    echo "[SKIP] $name no pid file"
    return
  fi

  local pid
  pid="$(cat "$pid_file" || true)"

  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    echo "[STOP] $name pid=$pid"
    kill "$pid" 2>/dev/null || true
    sleep 0.5

    if kill -0 "$pid" 2>/dev/null; then
      echo "[KILL] $name pid=$pid"
      kill -9 "$pid" 2>/dev/null || true
    fi
  else
    echo "[SKIP] $name not running"
  fi

  rm -f "$pid_file"
}

stop_one "camera_stream"
stop_one "camera_capture"
stop_one "command_handler"
stop_one "backend_client"
stop_one "go2_state_reader"

if command -v fuser >/dev/null 2>&1; then
  fuser -k 8081/tcp >/dev/null 2>&1 || true
fi


echo "[STOP] XT-16 Hesai lidar"
/home/unitree/go2_bridge_ws/scripts/stop_hesai_lidar.sh || true

echo "[OK] Robot side stopped."


force_clean_go2_processes() {
  echo "[CLEAN] Force clean old GO2 robot-side processes"

  patterns=(
    "[g]o2_state_reader_node"
    "[b]ackend_client_node"
    "[b]ackend_command_handler_node"
    "[c]amera_capture_node"
    "[g]o2_camera_stream_server.py"
    "[h]esai_ros_driver"
  )

  for pat in "${patterns[@]}"; do
    pids=$(pgrep -f "$pat" || true)
    if [ -n "$pids" ]; then
      echo "[CLEAN] kill $pat -> $pids"
      echo "$pids" | xargs -r kill -9
    fi
  done

  fuser -k 8081/tcp 2>/dev/null || true
  rm -f /home/unitree/go2_bridge_ws/logs/pids/*.pid 2>/dev/null || true
  sleep 1
}


force_clean_go2_processes
