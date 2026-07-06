#!/usr/bin/env bash
set -euo pipefail

WS="$HOME/GO2_Project/go2_bridge_ws"
LOG_DIR="$WS/logs/runtime"
PID_DIR="$WS/logs/pids"

JETSON_USER="${JETSON_USER:-unitree}"
JETSON_IP="${JETSON_IP:-192.168.123.18}"
BACKEND_IP="${BACKEND_IP:-192.168.123.99}"

mkdir -p "$LOG_DIR" "$PID_DIR"

echo "============================================================"
echo " GO2 Full System Startup"
echo " Local WS:    $WS"
echo " Jetson:      $JETSON_USER@$JETSON_IP"
echo " Backend IP:  $BACKEND_IP"
echo "============================================================"

cd "$WS"

# 停掉旧后台
if [ -f "$PID_DIR/backend_server.pid" ]; then
  old_pid="$(cat "$PID_DIR/backend_server.pid" || true)"
  if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
    echo "[STOP] old backend_server pid=$old_pid"
    kill "$old_pid" 2>/dev/null || true
    sleep 0.5
  fi
  rm -f "$PID_DIR/backend_server.pid"
fi

# 防止 8000 端口占用
if command -v fuser >/dev/null 2>&1; then
  fuser -k 8000/tcp >/dev/null 2>&1 || true
fi

echo "[START] FastAPI backend"
nohup bash -lc "
  cd '$WS'
  exec bash scripts/start_backend.sh
" > "$LOG_DIR/backend_server.log" 2>&1 &

echo $! > "$PID_DIR/backend_server.pid"
echo "[OK] backend_server pid=$(cat "$PID_DIR/backend_server.pid") log=$LOG_DIR/backend_server.log"

sleep 3

echo "[START] Jetson robot side"
ssh "$JETSON_USER@$JETSON_IP" "bash /home/unitree/go2_bridge_ws/scripts/start_robot_side.sh $BACKEND_IP"

echo
echo "============================================================"
echo " GO2 system started."
echo
echo "Dashboard:"
echo "  http://127.0.0.1:8000/dashboard"
echo "  http://$BACKEND_IP:8000/dashboard"
echo
echo "D435i live video:"
echo "  http://$JETSON_IP:8081/"
echo
echo "Backend log:"
echo "  $LOG_DIR/backend_server.log"
echo
echo "Jetson logs:"
echo "  /home/unitree/go2_bridge_ws/logs/runtime/"
echo "============================================================"
