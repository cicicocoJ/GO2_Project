#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster

class OdomToTFBridgeNow(Node):
    def __init__(self):
        super().__init__("odom_to_tf_bridge_now")

        self.odom_topic = self.declare_parameter(
            "odom_topic", "/utlidar/robot_odom"
        ).get_parameter_value().string_value

        self.parent_frame = self.declare_parameter(
            "parent_frame", "odom"
        ).get_parameter_value().string_value

        self.child_frame = self.declare_parameter(
            "child_frame", "base_link"
        ).get_parameter_value().string_value

        self.br = TransformBroadcaster(self)
        self.sub = self.create_subscription(Odometry, self.odom_topic, self.cb, 10)
        self.count = 0

        self.get_logger().info(
            f"Subscribe {self.odom_topic}, publish TF {self.parent_frame} -> {self.child_frame}, stamp=now()"
        )

    def cb(self, msg: Odometry):
        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = self.parent_frame
        t.child_frame_id = self.child_frame

        t.transform.translation.x = msg.pose.pose.position.x
        t.transform.translation.y = msg.pose.pose.position.y
        t.transform.translation.z = msg.pose.pose.position.z
        t.transform.rotation = msg.pose.pose.orientation

        self.br.sendTransform(t)

        self.count += 1
        if self.count % 50 == 0:
            p = msg.pose.pose.position
            self.get_logger().info(
                f"TF now {self.parent_frame}->{self.child_frame}: x={p.x:.3f}, y={p.y:.3f}, z={p.z:.3f}"
            )

def main():
    rclpy.init()
    node = OdomToTFBridgeNow()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
