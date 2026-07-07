#!/usr/bin/env bash
set -eo pipefail

set +u
source ~/GO2_Project/go2_ros_env_local.sh
set -u

MAP_YAML="/home/ceci/GO2_Project/maps/go2_xt16_2d_map_latest.yaml"
RVIZ_CONFIG="/home/ceci/GO2_Project/go2_bridge_ws/config/rviz/map_view.rviz"
LOG_DIR="/home/ceci/GO2_Project/go2_bridge_ws/logs/map_view"

mkdir -p "$LOG_DIR"

echo "============================================================"
echo " GO2 2D Map Local Viewer"
echo "============================================================"
echo "Map:  $MAP_YAML"
echo "RViz: $RVIZ_CONFIG"
echo "============================================================"

pkill -f "nav2_map_server map_server" || true
pkill -f "map_server" || true
pkill -f rviz2 || true
sleep 2

echo "[1/4] Start map_server"
ros2 run nav2_map_server map_server \
  --ros-args \
  -p yaml_filename:="$MAP_YAML" \
  > "$LOG_DIR/map_server.log" 2>&1 &

MAP_PID=$!
echo "[OK] map_server pid=$MAP_PID"
sleep 2

echo "[2/4] Configure map_server"
ros2 lifecycle set /map_server configure
sleep 1

echo "[3/4] Activate map_server"
ros2 lifecycle set /map_server activate
sleep 1

echo "[4/4] Check /map"
ros2 lifecycle get /map_server
ros2 topic info -v /map | sed -n '1,35p'

echo ""
echo "[START] RViz2"
rviz2 -d "$RVIZ_CONFIG"
