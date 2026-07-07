#!/usr/bin/env python3
import copy
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan

class ScanStampRelay(Node):
    def __init__(self):
        super().__init__("scan_stamp_relay")

        self.input_topic = self.declare_parameter("input_topic", "/scan").value
        self.output_topic = self.declare_parameter("output_topic", "/scan_slam").value
        self.frame_id = self.declare_parameter("frame_id", "hesai_lidar").value

        # publish_every_n=3 means 10Hz -> about 3.3Hz
        self.publish_every_n = int(self.declare_parameter("publish_every_n", 3).value)

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
        self.pub_count = 0

        self.get_logger().info(
            f"Relay {self.input_topic} -> {self.output_topic}, "
            f"stamp=now(), frame_id={self.frame_id}, "
            f"publish_every_n={self.publish_every_n}"
        )

    def cb(self, msg: LaserScan):
        self.count += 1

        if self.publish_every_n > 1 and (self.count % self.publish_every_n) != 0:
            return

        out = copy.deepcopy(msg)
        out.header.stamp = self.get_clock().now().to_msg()
        out.header.frame_id = self.frame_id

        self.pub.publish(out)

        self.pub_count += 1
        if self.pub_count % 30 == 0:
            self.get_logger().info(
                f"published {self.pub_count} scans to {self.output_topic}"
            )

def main():
    rclpy.init()
    node = ScanStampRelay()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
