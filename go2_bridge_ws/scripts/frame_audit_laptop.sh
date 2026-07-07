#!/usr/bin/env bash
set -eo pipefail

set +u
source ~/GO2_Project/go2_ros_env_lidar_wired.sh
set -u

echo "============================================================"
echo " GO2 + XT-16 Frame Audit"
echo "============================================================"

echo ""
echo "===== ROS nodes ====="
ros2 node list || true

echo ""
echo "===== Topic list: lidar / scan / odom / tf ====="
ros2 topic list | grep -E "lidar|scan|odom|tf|map|utlidar" || true

echo ""
echo "===== /lidar_points header ====="
timeout 5s ros2 topic echo /lidar_points --once | sed -n '1,25p' || true

echo ""
echo "===== /scan header ====="
timeout 5s ros2 topic echo /scan --once | sed -n '1,25p' || true

echo ""
echo "===== /scan_slam header ====="
timeout 5s ros2 topic echo /scan_slam --once | sed -n '1,25p' || true

echo ""
echo "===== /utlidar/robot_odom header ====="
timeout 5s ros2 topic echo /utlidar/robot_odom --once | sed -n '1,35p' || true

echo ""
echo "===== TF: odom -> base_link ====="
timeout 5s ros2 run tf2_ros tf2_echo odom base_link || true

echo ""
echo "===== TF: base_link -> hesai_lidar ====="
timeout 5s ros2 run tf2_ros tf2_echo base_link hesai_lidar || true

echo ""
echo "===== TF: odom -> hesai_lidar ====="
timeout 5s ros2 run tf2_ros tf2_echo odom hesai_lidar || true

echo ""
echo "============================================================"
echo " Frame audit finished."
echo "============================================================"
