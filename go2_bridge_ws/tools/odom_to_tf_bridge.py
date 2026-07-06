#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster

class OdomToTFBridge(Node):
    def __init__(self):
        super().__init__("odom_to_tf_bridge")

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

        # /utlidar/robot_odom 是 RELIABLE，所以这里用默认 QoS，避免 QoS 不匹配
        self.sub = self.create_subscription(
            Odometry,
            self.odom_topic,
            self.cb,
            10
        )

        self.count = 0

        self.get_logger().info(
            f"Subscribe {self.odom_topic}, publish TF {self.parent_frame} -> {self.child_frame}"
        )

    def cb(self, msg: Odometry):
        t = TransformStamped()

        # 使用 odom 消息自己的时间戳
        t.header.stamp = msg.header.stamp

        # 强制统一 frame 名，避免上游 frame 名变化影响后续 SLAM
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
            q = msg.pose.pose.orientation
            self.get_logger().info(
                f"TF {self.parent_frame}->{self.child_frame}: "
                f"x={p.x:.3f}, y={p.y:.3f}, z={p.z:.3f}, "
                f"q=({q.x:.3f}, {q.y:.3f}, {q.z:.3f}, {q.w:.3f})"
            )

def main():
    rclpy.init()
    node = OdomToTFBridge()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
