#!/usr/bin/env python3
import math

import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster


def normalize_angle(a):
    while a > math.pi:
        a -= 2.0 * math.pi
    while a < -math.pi:
        a += 2.0 * math.pi
    return a


def yaw_from_quat(q):
    siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
    return math.atan2(siny_cosp, cosy_cosp)


def quat_from_yaw(yaw):
    return 0.0, 0.0, math.sin(yaw * 0.5), math.cos(yaw * 0.5)


class OdomToTfBridgeNow(Node):
    def __init__(self):
        super().__init__("odom_to_tf_bridge_now")

        self.declare_parameter("odom_topic", "/utlidar/robot_odom")
        self.declare_parameter("odom_frame", "odom")
        self.declare_parameter("base_frame", "base_link")
        self.declare_parameter("publish_period_sec", 0.02)

        # 静止判断阈值：
        # 你的静止 yaw 漂移约 0.0014 rad/s，远小于 0.01 rad/s，
        # 正常建图转向建议 > 0.05 rad/s，所以这个阈值比较安全。
        self.declare_parameter("stationary_linear_speed_threshold", 0.025)  # m/s
        self.declare_parameter("stationary_yaw_rate_threshold", 0.010)      # rad/s
        self.declare_parameter("stationary_hold_sec", 0.8)

        self.odom_topic = self.get_parameter("odom_topic").value
        self.odom_frame = self.get_parameter("odom_frame").value
        self.base_frame = self.get_parameter("base_frame").value
        self.publish_period_sec = float(self.get_parameter("publish_period_sec").value)

        self.v_static_th = float(self.get_parameter("stationary_linear_speed_threshold").value)
        self.w_static_th = float(self.get_parameter("stationary_yaw_rate_threshold").value)
        self.static_hold_sec = float(self.get_parameter("stationary_hold_sec").value)

        self.tf_broadcaster = TransformBroadcaster(self)

        self.prev_raw = None
        self.prev_time = None

        # 输出位姿 = 原始 odom 位姿 + offset
        # 静止时持续更新 offset，让输出位姿冻结不漂。
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.offset_yaw = 0.0

        self.out_x = None
        self.out_y = None
        self.out_yaw = None

        self.last_pub_x = None
        self.last_pub_y = None
        self.last_pub_yaw = None

        self.stationary_since = None
        self.freeze_active = False
        self.last_log_time = 0.0

        self.create_subscription(Odometry, self.odom_topic, self.odom_callback, 10)
        self.create_timer(self.publish_period_sec, self.publish_tf)

        self.get_logger().info("2D planar odom TF bridge with stationary freeze started.")
        self.get_logger().info(f"Subscribing: {self.odom_topic}")
        self.get_logger().info(f"Publishing TF: {self.odom_frame} -> {self.base_frame}")
        self.get_logger().info("Mode: x/y/yaw only, z=0, roll=0, pitch=0, stamp=now()")
        self.get_logger().info(
            f"Freeze thresholds: v<{self.v_static_th:.3f} m/s, "
            f"|yaw_rate|<{self.w_static_th:.3f} rad/s, hold>{self.static_hold_sec:.2f}s"
        )

    def odom_callback(self, msg):
        now = self.get_clock().now().nanoseconds * 1e-9

        p = msg.pose.pose.position
        q = msg.pose.pose.orientation

        raw_x = float(p.x)
        raw_y = float(p.y)
        raw_yaw = yaw_from_quat(q)

        if self.prev_raw is None:
            self.prev_raw = (raw_x, raw_y, raw_yaw)
            self.prev_time = now

            self.out_x = raw_x
            self.out_y = raw_y
            self.out_yaw = raw_yaw

            self.last_pub_x = self.out_x
            self.last_pub_y = self.out_y
            self.last_pub_yaw = self.out_yaw
            return

        dt = max(now - self.prev_time, 1e-3)
        prev_x, prev_y, prev_yaw = self.prev_raw

        dx = raw_x - prev_x
        dy = raw_y - prev_y
        dyaw = normalize_angle(raw_yaw - prev_yaw)

        raw_v = math.sqrt(dx * dx + dy * dy) / dt
        raw_w = abs(dyaw) / dt

        instant_stationary = (raw_v < self.v_static_th) and (raw_w < self.w_static_th)

        if instant_stationary:
            if self.stationary_since is None:
                self.stationary_since = now

            if (now - self.stationary_since) >= self.static_hold_sec:
                # 进入静止冻结：保持上一帧输出不动，同时更新 offset，
                # 抵消原始 odom 的静止漂移。
                if not self.freeze_active:
                    self.get_logger().info("Stationary freeze ON.")
                    self.freeze_active = True

                self.offset_x = self.last_pub_x - raw_x
                self.offset_y = self.last_pub_y - raw_y
                self.offset_yaw = normalize_angle(self.last_pub_yaw - raw_yaw)

                self.out_x = self.last_pub_x
                self.out_y = self.last_pub_y
                self.out_yaw = self.last_pub_yaw
            else:
                # 静止确认前，正常输出
                self.out_x = raw_x + self.offset_x
                self.out_y = raw_y + self.offset_y
                self.out_yaw = normalize_angle(raw_yaw + self.offset_yaw)
        else:
            # 检测到运动，解除冻结。保留 offset，避免从冻结状态跳变。
            if self.freeze_active:
                self.get_logger().info("Stationary freeze OFF. Robot is moving.")

            self.freeze_active = False
            self.stationary_since = None

            self.out_x = raw_x + self.offset_x
            self.out_y = raw_y + self.offset_y
            self.out_yaw = normalize_angle(raw_yaw + self.offset_yaw)

            self.last_pub_x = self.out_x
            self.last_pub_y = self.out_y
            self.last_pub_yaw = self.out_yaw

        if self.freeze_active:
            # 冻结时 last_pub 保持不变
            pass
        else:
            self.last_pub_x = self.out_x
            self.last_pub_y = self.out_y
            self.last_pub_yaw = self.out_yaw

        self.prev_raw = (raw_x, raw_y, raw_yaw)
        self.prev_time = now

        # 低频打印，方便确认冻结是否工作
        if now - self.last_log_time > 5.0:
            self.last_log_time = now
            self.get_logger().info(
                f"raw_v={raw_v:.4f} m/s raw_w={raw_w:.4f} rad/s "
                f"freeze={self.freeze_active}"
            )

    def publish_tf(self):
        if self.out_x is None:
            return

        qx, qy, qz, qw = quat_from_yaw(self.out_yaw)

        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = self.odom_frame
        t.child_frame_id = self.base_frame

        t.transform.translation.x = float(self.out_x)
        t.transform.translation.y = float(self.out_y)
        t.transform.translation.z = 0.0

        t.transform.rotation.x = qx
        t.transform.rotation.y = qy
        t.transform.rotation.z = qz
        t.transform.rotation.w = qw

        self.tf_broadcaster.sendTransform(t)


def main():
    rclpy.init()
    node = OdomToTfBridgeNow()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
