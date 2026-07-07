#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import PointCloud2, LaserScan
from nav_msgs.msg import Odometry

def stamp_to_sec(stamp):
    return float(stamp.sec) + float(stamp.nanosec) * 1e-9

class TimestampAudit(Node):
    def __init__(self):
        super().__init__("timestamp_audit")

        self.latest = {}

        self.create_subscription(
            PointCloud2,
            "/lidar_points",
            lambda msg: self.save("/lidar_points", msg.header.stamp, msg.header.frame_id),
            qos_profile_sensor_data,
        )

        self.create_subscription(
            LaserScan,
            "/scan",
            lambda msg: self.save("/scan", msg.header.stamp, msg.header.frame_id),
            qos_profile_sensor_data,
        )

        self.create_subscription(
            LaserScan,
            "/scan_slam",
            lambda msg: self.save("/scan_slam", msg.header.stamp, msg.header.frame_id),
            qos_profile_sensor_data,
        )

        self.create_subscription(
            Odometry,
            "/utlidar/robot_odom",
            lambda msg: self.save(
                "/utlidar/robot_odom",
                msg.header.stamp,
                f"{msg.header.frame_id}->{msg.child_frame_id}",
            ),
            qos_profile_sensor_data,
        )

        self.timer = self.create_timer(1.0, self.print_report)

        self.get_logger().info("Timestamp audit started.")

    def save(self, topic, stamp, frame):
        self.latest[topic] = (stamp_to_sec(stamp), frame)

    def print_report(self):
        now_sec = self.get_clock().now().nanoseconds * 1e-9
        print("\n================ Timestamp Audit ================")
        print(f"ROS now: {now_sec:.6f}")

        for topic in ["/lidar_points", "/scan", "/scan_slam", "/utlidar/robot_odom"]:
            if topic not in self.latest:
                print(f"{topic:22s} no message")
                continue

            msg_time, frame = self.latest[topic]
            delay = now_sec - msg_time
            print(
                f"{topic:22s} stamp={msg_time:.6f}  "
                f"now-stamp={delay:.6f}s  frame={frame}"
            )

def main():
    rclpy.init()
    node = TimestampAudit()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
