#!/usr/bin/env bash
set -eo pipefail

# 不能在 source ROS setup.bash 时开启 set -u
# 否则会出现 AMENT_TRACE_SETUP_FILES: 未绑定的变量
set +u
if [ -f "$HOME/GO2_Project/go2_ros_env_lidar_wired.sh" ]; then
  source "$HOME/GO2_Project/go2_ros_env_lidar_wired.sh"
else
  source "$HOME/GO2_Project/go2_ros_env.sh"
fi
set -u

WS="$HOME/GO2_Project/go2_bridge_ws"
LOG_DIR="$WS/logs/slam2d"
PID_FILE="/tmp/go2_2d_slam_pids.txt"
PARAM_FILE="$WS/config/slam_2d/mapper_params_online_async.yaml"

mkdir -p "$LOG_DIR"
rm -f "$PID_FILE"

echo "============================================================"
echo " GO2 + XT-16 2D SLAM Laptop Pipeline"
echo "============================================================"
echo "WS:         $WS"
echo "Logs:       $LOG_DIR"
echo "Param file: $PARAM_FILE"
echo "============================================================"

if [ ! -f "$PARAM_FILE" ]; then
  echo "[ERROR] Param file not found: $PARAM_FILE"
  echo "Please create mapper_params_online_async.yaml first."
  exit 1
fi

echo "[1/5] Start pointcloud_to_laserscan: /lidar_points -> /scan"
ros2 run pointcloud_to_laserscan pointcloud_to_laserscan_node \
  --ros-args \
  -r cloud_in:=/lidar_points \
  -r scan:=/scan \
  -p transform_tolerance:=0.05 \
  -p min_height:=-0.50 \
  -p max_height:=0.50 \
  -p angle_min:=-3.14159 \
  -p angle_max:=3.14159 \
  -p angle_increment:=0.00872 \
  -p scan_time:=0.1 \
  -p range_min:=0.45 \
  -p range_max:=6.0 \
  -p use_inf:=true \
  > "$LOG_DIR/pointcloud_to_laserscan.log" 2>&1 &
echo $! >> "$PID_FILE"

sleep 2

echo "[2/5] Start scan_stamp_relay: /scan -> /scan_slam, downsample 3:1"
python3 "$WS/tools/scan_stamp_relay.py" \
  --ros-args \
  -p input_topic:=/scan \
  -p output_topic:=/scan_slam \
  -p frame_id:=hesai_lidar \
  -p publish_every_n:=3 \
  > "$LOG_DIR/scan_stamp_relay.log" 2>&1 &
echo $! >> "$PID_FILE"

sleep 1

echo "[3/5] Start odom_to_tf_bridge_now: /utlidar/robot_odom -> odom -> base_link"
python3 "$WS/tools/odom_to_tf_bridge_now.py" \
  --ros-args \
  -p odom_topic:=/utlidar/robot_odom \
  -p parent_frame:=odom \
  -p child_frame:=base_link \
  > "$LOG_DIR/odom_to_tf_bridge_now.log" 2>&1 &
echo $! >> "$PID_FILE"

sleep 1

echo "[4/5] Start static TF: base_link -> hesai_lidar"
ros2 run tf2_ros static_transform_publisher \
  --x 0.171 \
  --y 0.00 \
  --z 0.0908 \
  --roll 0.00 \
  --pitch 0.00 \
  --yaw 0.00 \
  --frame-id base_link \
  --child-frame-id hesai_lidar \
  > "$LOG_DIR/static_tf_base_to_hesai.log" 2>&1 &
echo $! >> "$PID_FILE"

sleep 2

echo "[5/5] Start slam_toolbox: /scan_slam -> /map"
ros2 run slam_toolbox async_slam_toolbox_node \
  --ros-args \
  --params-file "$PARAM_FILE" \
  > "$LOG_DIR/slam_toolbox.log" 2>&1 &
echo $! >> "$PID_FILE"

sleep 3

echo ""
echo "============================================================"
echo "[OK] 2D SLAM pipeline started."
echo ""
echo "Check:"
echo "  source ~/GO2_Project/go2_ros_env_lidar_wired.sh"
echo "  ros2 topic info /scan_slam"
echo "  timeout 10s ros2 topic hz /scan_slam"
echo "  timeout 10s ros2 run tf2_ros tf2_echo map odom"
echo ""
echo "Logs:"
echo "  tail -f $LOG_DIR/slam_toolbox.log"
echo "============================================================"
