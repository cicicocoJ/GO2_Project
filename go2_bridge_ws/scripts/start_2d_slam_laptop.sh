#!/usr/bin/env bash
set -e

source ~/GO2_Project/go2_ros_env.sh

LOG_DIR=~/GO2_Project/go2_bridge_ws/logs/slam2d
PID_FILE=/tmp/go2_2d_slam_pids.txt

mkdir -p "$LOG_DIR"
rm -f "$PID_FILE"

echo "============================================================"
echo " GO2 + XT-16 2D SLAM Laptop Pipeline"
echo "============================================================"
echo "[INFO] Logs: $LOG_DIR"
echo "[INFO] PID file: $PID_FILE"
echo ""

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
  -p angle_increment:=0.00436 \
  -p scan_time:=0.1 \
  -p range_min:=0.25 \
  -p range_max:=30.0 \
  -p use_inf:=true \
  > "$LOG_DIR/pointcloud_to_laserscan.log" 2>&1 &
echo $! >> "$PID_FILE"

sleep 2

echo "[2/5] Start scan_stamp_relay: /scan -> /scan_slam"
python3 ~/GO2_Project/go2_bridge_ws/tools/scan_stamp_relay.py \
  --ros-args \
  -p input_topic:=/scan \
  -p output_topic:=/scan_slam \
  -p frame_id:=hesai_lidar \
  > "$LOG_DIR/scan_stamp_relay.log" 2>&1 &
echo $! >> "$PID_FILE"

sleep 1

echo "[3/5] Start odom_to_tf_bridge_now: /utlidar/robot_odom -> odom -> base_link"
python3 ~/GO2_Project/go2_bridge_ws/tools/odom_to_tf_bridge_now.py \
  --ros-args \
  -p odom_topic:=/utlidar/robot_odom \
  -p parent_frame:=odom \
  -p child_frame:=base_link \
  > "$LOG_DIR/odom_to_tf_bridge_now.log" 2>&1 &
echo $! >> "$PID_FILE"

sleep 1

echo "[4/5] Start static TF: base_link -> hesai_lidar"
ros2 run tf2_ros static_transform_publisher \
  --x 0.20 \
  --y 0.00 \
  --z 0.25 \
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
  --params-file ~/GO2_Project/go2_bridge_ws/config/slam_2d/mapper_params_online_async.yaml \
  > "$LOG_DIR/slam_toolbox.log" 2>&1 &
echo $! >> "$PID_FILE"

sleep 3

echo ""
echo "============================================================"
echo "[OK] 2D SLAM pipeline started."
echo ""
echo "Check commands:"
echo "  source ~/GO2_Project/go2_ros_env.sh"
echo "  ros2 topic info /scan_slam"
echo "  ros2 topic info /map"
echo "  timeout 10s ros2 run tf2_ros tf2_echo map odom"
echo ""
echo "Logs:"
echo "  tail -f $LOG_DIR/slam_toolbox.log"
echo "============================================================"
