#!/usr/bin/env bash
set -eo pipefail

set +u
source ~/GO2_Project/go2_ros_env_lidar_wired.sh
set -u

python3 ~/GO2_Project/go2_bridge_ws/tools/timestamp_audit.py
