#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan

class ScanStampRelay(Node):
    def __init__(self):
        super().__init__("scan_stamp_relay")

        self.input_topic = self.declare_parameter(
            "input_topic", "/scan"
        ).get_parameter_value().string_value

        self.output_topic = self.declare_parameter(
            "output_topic", "/scan_slam"
        ).get_parameter_value().string_value

        self.frame_id = self.declare_parameter(
            "frame_id", "hesai_lidar"
        ).get_parameter_value().string_value

        self.pub = self.create_publisher(
            LaserScan,
            self.output_topic,
            qos_profile_sensor_data
        )

        self.sub = self.create_subscription(
            LaserScan,
            self.input_topic,
            self.cb,
            qos_profile_sensor_data
        )

        self.count = 0

        self.get_logger().info(
            f"Relay {self.input_topic} -> {self.output_topic}, stamp=now(), frame_id={self.frame_id}"
        )

    def cb(self, msg: LaserScan):
        out = msg
        out.header.stamp = self.get_clock().now().to_msg()
        out.header.frame_id = self.frame_id
        self.pub.publish(out)

        self.count += 1
        if self.count % 50 == 0:
            self.get_logger().info("republished /scan_slam with current timestamp")

def main():
    rclpy.init()
    node = ScanStampRelay()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
