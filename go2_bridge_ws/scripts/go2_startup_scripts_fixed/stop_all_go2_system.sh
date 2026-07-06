#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WS="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -f "$SCRIPT_DIR/go2_network.env" ]; then
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/go2_network.env"
fi

PID_DIR="$WS/logs/pids"

JETSON_USER="${JETSON_USER:-unitree}"
JETSON_IP="${JETSON_IP:-192.168.7.149}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
JETSON_VIDEO_PORT="${JETSON_VIDEO_PORT:-8081}"

echo "============================================================"
echo " GO2 Full System Stop"
echo " Local WS: $WS"
echo " Jetson:   $JETSON_USER@$JETSON_IP"
echo "============================================================"

echo "[STOP] Jetson robot side"
ssh "$JETSON_USER@$JETSON_IP" \
  "env BACKEND_PORT='$BACKEND_PORT' JETSON_VIDEO_PORT='$JETSON_VIDEO_PORT' bash /home/unitree/go2_bridge_ws/scripts/stop_robot_side.sh" || true

echo "[STOP] local backend"

if [ -f "$PID_DIR/backend_server.pid" ]; then
  pid="$(cat "$PID_DIR/backend_server.pid" || true)"

  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    echo "[STOP] backend_server pid=$pid"
    kill "$pid" 2>/dev/null || true
    sleep 0.5

    if kill -0 "$pid" 2>/dev/null; then
      echo "[KILL] backend_server pid=$pid"
      kill -9 "$pid" 2>/dev/null || true
    fi
  fi

  rm -f "$PID_DIR/backend_server.pid"
fi

if command -v fuser >/dev/null 2>&1; then
  fuser -k "${BACKEND_PORT}/tcp" >/dev/null 2>&1 || true
fi

echo "[OK] GO2 full system stopped."
