#!/usr/bin/env python3
import math
import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry

def yaw_from_q(q):
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny_cosp, cosy_cosp)

class OdomDriftTest(Node):
    def __init__(self):
        super().__init__("odom_static_drift_test")
        self.start = None
        self.latest = None
        self.count = 0
        self.sub = self.create_subscription(
            Odometry,
            "/utlidar/robot_odom",
            self.cb,
            10
        )
        self.timer = self.create_timer(1.0, self.report)
        self.get_logger().info("Keep robot completely still. Testing /utlidar/robot_odom drift...")

    def cb(self, msg):
        p = msg.pose.pose.position
        q = msg.pose.pose.orientation
        data = (p.x, p.y, p.z, yaw_from_q(q))
        if self.start is None:
            self.start = data
        self.latest = data
        self.count += 1

    def report(self):
        if self.start is None or self.latest is None:
            print("No odom message yet.")
            return
        sx, sy, sz, syaw = self.start
        x, y, z, yaw = self.latest
        dx = x - sx
        dy = y - sy
        dz = z - sz
        dyaw = math.degrees(yaw - syaw)
        dist = math.sqrt(dx * dx + dy * dy)
        print(
            f"count={self.count:5d} | "
            f"dx={dx:+.4f} m, dy={dy:+.4f} m, dz={dz:+.4f} m, "
            f"planar={dist:.4f} m, dyaw={dyaw:+.3f} deg"
        )

def main():
    rclpy.init()
    node = OdomDriftTest()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
