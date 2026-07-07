#!/usr/bin/env bash
set -euo pipefail

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
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/go2_network.env" ]; then
  source "$SCRIPT_DIR/go2_network.env"
fi

BACKEND_IP="${1:-${BACKEND_IP:-192.168.7.124}}"

WS="/home/unitree/go2_bridge_ws"
LOG_DIR="$WS/logs/runtime"
PID_DIR="$WS/logs/pids"

mkdir -p "$LOG_DIR" "$PID_DIR" /home/unitree/go2_captures

source_ros_env() {
  source /opt/ros/foxy/setup.bash
  source /home/unitree/cyclonedds_ws/install/setup.bash
  source "$WS/install/setup.bash"

  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
  export CYCLONEDDS_URI='<CycloneDDS><Domain><General><Interfaces>
    <NetworkInterface name="eth0" priority="default" multicast="default" />
</Interfaces></General></Domain></CycloneDDS>'
}

stop_if_running() {
  local name="$1"
  local pid_file="$PID_DIR/${name}.pid"

  if [ -f "$pid_file" ]; then
    local pid
    pid="$(cat "$pid_file" || true)"

    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      echo "[STOP] $name old pid=$pid"
      kill "$pid" 2>/dev/null || true
      sleep 0.5
    fi

    rm -f "$pid_file"
  fi
}

start_node() {
  local name="$1"
  local cmd="$2"

  stop_if_running "$name"

  echo "[START] $name"
  echo "        $cmd"

  nohup bash -lc "
    set -e
    cd '$WS'
    source /opt/ros/foxy/setup.bash
    source /home/unitree/cyclonedds_ws/install/setup.bash
    source '$WS/install/setup.bash'
    export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
    export CYCLONEDDS_URI='<CycloneDDS><Domain><General><Interfaces>
      <NetworkInterface name=\"eth0\" priority=\"default\" multicast=\"default\" />
    </Interfaces></General></Domain></CycloneDDS>'
    exec $cmd
  " > "$LOG_DIR/${name}.log" 2>&1 &

  echo $! > "$PID_DIR/${name}.pid"
  echo "[OK] $name pid=$(cat "$PID_DIR/${name}.pid") log=$LOG_DIR/${name}.log"
}

echo "============================================================"
echo " GO2 Robot Side Startup"
echo " BACKEND_IP=$BACKEND_IP"
echo " WS=$WS"
echo "============================================================"

# 防止旧的视频流占用 8081
if command -v fuser >/dev/null 2>&1; then
  fuser -k 8081/tcp >/dev/null 2>&1 || true
fi

start_node "go2_state_reader" \
  "ros2 run go2_backend_bridge go2_state_reader_node"

sleep 1

start_node "backend_client" \
  "env BACKEND_PORT=$BACKEND_PORT bash scripts/start_bridge.sh $BACKEND_IP"

sleep 1

start_node "command_handler" \
  "ros2 run go2_command_control backend_command_handler_node \
    --ros-args \
    -p linear_speed_x:=0.30 \
    -p linear_speed_y:=0.25 \
    -p yaw_speed:=0.70 \
    -p move_duration_sec:=1.5 \
    -p control_period_sec:=0.1 \
    -p mapping_cmd_vx:=0.22 \
    -p mapping_cmd_vy:=0.0 \
    -p mapping_yaw_deadband_deg:=1.5 \
    -p mapping_yaw_trigger_deg:=2.0 \
    -p mapping_yaw_correction_rate:=0.50 \
    -p mapping_yaw_correction_max:=0.70 \
    -p mapping_control_period_sec:=0.10 \
    -p mapping_yaw_pulse_cycles:=1 \
    -p mapping_forward_step_duration_sec:=1.2 \
    -p mapping_small_turn_rate:=0.70 \
    -p mapping_small_turn_duration_sec:=0.20 \
    -p mapping_log_interval_sec:=1.0"

sleep 1

start_node "camera_capture" \
  "ros2 run go2_camera_capture camera_capture_node \
    --ros-args \
    -p camera_index:=4 \
    -p image_dir:=/home/unitree/go2_captures \
    -p image_width:=640 \
    -p image_height:=480 \
    -p jpeg_quality:=90"

sleep 1

start_node "camera_stream" \
  "python3 /home/unitree/go2_camera_stream_server.py"

echo
echo "============================================================"

echo
echo "[START] XT-16 Hesai lidar"
/home/unitree/go2_bridge_ws/scripts/start_hesai_lidar.sh

echo " Robot side started."
echo " Logs:"
echo "   $LOG_DIR"
echo " Video:"
echo "   http://$JETSON_IP:$JETSON_VIDEO_PORT/"
echo "============================================================"
