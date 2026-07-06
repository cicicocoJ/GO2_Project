#!/usr/bin/env bash
set -euo pipefail

WS="/home/unitree/hesai_ws"
LOG_DIR="$WS/logs/runtime"
PID_DIR="$WS/logs/pids"

mkdir -p "$LOG_DIR" "$PID_DIR"

echo "============================================================"
echo " XT-16 / Hesai Lidar Startup"
echo " WS=$WS"
echo " Topic=/lidar_points"
echo " Frame=hesai_lidar"
echo "============================================================"

# 停掉旧 Hesai 驱动
if [ -f "$PID_DIR/hesai_lidar.pid" ]; then
  OLD_PID="$(cat "$PID_DIR/hesai_lidar.pid" || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "[STOP] old hesai_lidar pid=$OLD_PID"
    kill "$OLD_PID" 2>/dev/null || true
    sleep 0.8
    if kill -0 "$OLD_PID" 2>/dev/null; then
      kill -9 "$OLD_PID" 2>/dev/null || true
    fi
  fi
  rm -f "$PID_DIR/hesai_lidar.pid"
fi

pkill -f "hesai_ros_driver" 2>/dev/null || true
pkill -f "rviz2" 2>/dev/null || true

# 增大 UDP 接收缓冲区，减少点云 UDP 丢包风险
# 一键启动时通过 SSH 后台执行，sudo 可能没有交互式终端。
# 因此这里使用 sudo -n：能免密 sudo 就设置；不能设置就跳过，但不影响雷达驱动启动。
if sudo -n true 2>/dev/null; then
  sudo -n sysctl -w net.core.rmem_max=134217728 >/dev/null || true
  sudo -n sysctl -w net.core.rmem_default=134217728 >/dev/null || true
  echo "[OK] UDP receive buffer enlarged."
else
  echo "[WARN] Skip UDP buffer setup: sudo requires password in non-interactive SSH."
  echo "[WARN] Lidar driver will still start. You can run sysctl manually later if needed."
fi

echo "[START] hesai_ros_driver"

nohup bash -lc "
  set -e
  cd '$WS'

  source /opt/ros/foxy/setup.bash
  source '$WS/install/setup.bash'

  export ROS_DOMAIN_ID=0
  export ROS_LOCALHOST_ONLY=0
  export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

  export CYCLONEDDS_URI='<CycloneDDS><Domain><General><Interfaces>
    <NetworkInterface name=\"eth0\" priority=\"default\" multicast=\"default\" />
  </Interfaces></General></Domain></CycloneDDS>'

  exec ros2 launch hesai_ros_driver start.py
" > "$LOG_DIR/hesai_lidar.log" 2>&1 &

echo $! > "$PID_DIR/hesai_lidar.pid"

echo "[OK] hesai_lidar pid=$(cat "$PID_DIR/hesai_lidar.pid")"
echo "[LOG] $LOG_DIR/hesai_lidar.log"
echo
echo "Check topic:"
echo "  source /opt/ros/foxy/setup.bash"
echo "  source $WS/install/setup.bash"
echo "  ros2 topic info /lidar_points"
echo
echo "Expected:"
echo "  /lidar_points"
echo "  sensor_msgs/msg/PointCloud2"
echo "  frame_id: hesai_lidar"
echo "  hz: about 10Hz"
echo "============================================================"
