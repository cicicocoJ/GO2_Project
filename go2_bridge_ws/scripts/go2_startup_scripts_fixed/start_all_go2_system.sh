#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WS="$(cd "$SCRIPT_DIR/.." && pwd)"

# Unified network config. Override by editing scripts/go2_network.env
# or by exporting variables before running this script.
if [ -f "$SCRIPT_DIR/go2_network.env" ]; then
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/go2_network.env"
fi

LOG_DIR="$WS/logs/runtime"
PID_DIR="$WS/logs/pids"

JETSON_USER="${JETSON_USER:-unitree}"
JETSON_IP="${JETSON_IP:-192.168.7.149}"
BACKEND_IP="${BACKEND_IP:-192.168.7.124}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
JETSON_VIDEO_PORT="${JETSON_VIDEO_PORT:-8081}"
ROBOT_ID="${ROBOT_ID:-GO2_001}"

mkdir -p "$LOG_DIR" "$PID_DIR"

echo "============================================================"
echo " GO2 Full System Startup"
echo " Local WS:      $WS"
echo " Jetson:        $JETSON_USER@$JETSON_IP"
echo " Backend:       $BACKEND_IP:$BACKEND_PORT"
echo " Robot ID:      $ROBOT_ID"
echo " Jetson video:  $JETSON_IP:$JETSON_VIDEO_PORT"
echo "============================================================"

cd "$WS"

# Stop old local backend by pid file.
if [ -f "$PID_DIR/backend_server.pid" ]; then
  old_pid="$(cat "$PID_DIR/backend_server.pid" || true)"
  if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
    echo "[STOP] old backend_server pid=$old_pid"
    kill "$old_pid" 2>/dev/null || true
    sleep 0.5
    if kill -0 "$old_pid" 2>/dev/null; then
      echo "[KILL] old backend_server pid=$old_pid"
      kill -9 "$old_pid" 2>/dev/null || true
    fi
  fi
  rm -f "$PID_DIR/backend_server.pid"
fi

# Prevent backend port conflict.
if command -v fuser >/dev/null 2>&1; then
  fuser -k "${BACKEND_PORT}/tcp" >/dev/null 2>&1 || true
fi

echo "[START] FastAPI backend"
nohup env \
  BACKEND_PORT="$BACKEND_PORT" \
  ROBOT_ID="$ROBOT_ID" \
  bash "$WS/scripts/start_backend.sh" \
  > "$LOG_DIR/backend_server.log" 2>&1 &

echo $! > "$PID_DIR/backend_server.pid"
echo "[OK] backend_server pid=$(cat "$PID_DIR/backend_server.pid") log=$LOG_DIR/backend_server.log"

sleep 3

echo "[START] Jetson robot side"
ssh "$JETSON_USER@$JETSON_IP" \
  "env BACKEND_IP='$BACKEND_IP' BACKEND_PORT='$BACKEND_PORT' JETSON_IP='$JETSON_IP' JETSON_VIDEO_PORT='$JETSON_VIDEO_PORT' ROBOT_ID='$ROBOT_ID' bash /home/unitree/go2_bridge_ws/scripts/start_robot_side.sh '$BACKEND_IP'"

echo
echo "============================================================"
echo " GO2 system started."
echo
echo "Dashboard:"
echo "  http://127.0.0.1:${BACKEND_PORT}/dashboard"
echo "  http://${BACKEND_IP}:${BACKEND_PORT}/dashboard"
echo
echo "D435i live video:"
echo "  http://${JETSON_IP}:${JETSON_VIDEO_PORT}/"
echo
echo "Backend log:"
echo "  $LOG_DIR/backend_server.log"
echo
echo "Jetson logs:"
echo "  /home/unitree/go2_bridge_ws/logs/runtime/"
echo "============================================================"
