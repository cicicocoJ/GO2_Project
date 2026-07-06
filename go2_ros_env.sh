source /opt/ros/humble/setup.bash
export ROS_LOCALHOST_ONLY=0
export ROS_DOMAIN_ID=0
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI='<CycloneDDS><Domain><General><Interfaces>
<NetworkInterface name="enx00e04c36178d" priority="default" multicast="default" />
</Interfaces></General></Domain></CycloneDDS>'
