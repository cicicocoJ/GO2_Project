#!/usr/bin/env bash
set -eo pipefail

echo "============================================================"
echo " Laptop RViz2 for XT-16"
echo " ROS2: Humble"
echo " Interface: enx00e04c36178d"
echo " Topic: /lidar_points"
echo " Fixed Frame: hesai_lidar"
echo "============================================================"

source /opt/ros/humble/setup.bash

export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

export CYCLONEDDS_URI='<CycloneDDS><Domain><General><Interfaces>
  <NetworkInterface name="enx00e04c36178d" priority="default" multicast="default" />
</Interfaces></General></Domain></CycloneDDS>'

ros2 daemon stop >/dev/null 2>&1 || true
ros2 daemon start >/dev/null 2>&1 || true

echo "[CHECK] ROS2 topics containing lidar:"
ros2 topic list | grep lidar || true

echo
echo "If /lidar_points exists, RViz2 will open."
echo "In RViz2:"
echo "  Fixed Frame = hesai_lidar"
echo "  Add -> By topic -> /lidar_points -> PointCloud2"
echo

exec rviz2
