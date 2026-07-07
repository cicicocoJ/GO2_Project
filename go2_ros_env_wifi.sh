source /opt/ros/humble/setup.bash
export ROS_LOCALHOST_ONLY=0
export ROS_DOMAIN_ID=0
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

# Wi-Fi 模式：不强行绑定有线雷达网卡
unset CYCLONEDDS_URI
