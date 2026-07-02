#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
go2_state_reader_node.py

GO2 真实状态读取节点。

功能：
    1. 订阅 Unitree GO2 的真实状态话题：
        /lf/sportmodestate
        /lf/lowstate

    2. 提取机器人运动状态、电量、IMU 等信息；

    3. 发布简单状态到：
        /inspection_state

       这个话题继续给现有 backend_client_node 使用，
       因此 backend_client_node 不需要大改。

    4. 发布详细 JSON 状态到：
        /go2_status_json

       后续后台可以从这里扩展显示电量、速度、姿态等信息。

注意：
    本节点只读取状态，不发送任何控制命令。
"""

import json
import math
import threading
import time
from datetime import datetime

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSProfile,
    QoSHistoryPolicy,
    QoSReliabilityPolicy,
    QoSDurabilityPolicy,
)
from std_msgs.msg import String

from unitree_go.msg import SportModeState
from unitree_go.msg import LowState


def utc_timestamp():
    """
    生成 UTC 时间戳字符串。
    """
    return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def safe_get(obj, name, default=None):
    """
    安全读取对象字段。

    不同 Unitree 消息版本中，字段可能略有差异。
    使用 getattr 可以避免因为字段不存在导致节点崩溃。
    """
    return getattr(obj, name, default)


def to_plain_list(value):
    """
    把 ROS2 消息中的数组、tuple、array 转成普通 Python list。

    JSON 序列化时普通 list 更稳定。
    """
    if value is None:
        return None

    try:
        result = list(value)
    except TypeError:
        return value

    plain = []
    for item in result:
        if isinstance(item, (int, float, str, bool)) or item is None:
            plain.append(item)
        else:
            # 如果遇到复杂对象，先转成字符串，避免 JSON 序列化失败。
            plain.append(str(item))
    return plain


def to_number(value, default=None):
    """
    尽量把字段转换成 int 或 float。
    """
    if value is None:
        return default

    if isinstance(value, (int, float)):
        return value

    try:
        return float(value)
    except Exception:
        return default


class Go2StateReaderNode(Node):
    """
    GO2 状态读取节点。

    订阅：
        /lf/sportmodestate
        /lf/lowstate

    发布：
        /inspection_state
        /go2_status_json
    """

    def __init__(self):
        super().__init__('go2_state_reader_node')

        # ============================================================
        # 1. 参数
        # ============================================================

        self.declare_parameter('sport_topic', '/lf/sportmodestate')
        self.declare_parameter('lowstate_topic', '/lf/lowstate')
        self.declare_parameter('inspection_state_topic', '/inspection_state')
        self.declare_parameter('status_json_topic', '/go2_status_json')

        # 状态发布周期，单位：秒。
        self.declare_parameter('publish_period_sec', 1.0)

        # 判断机器人是否在移动的速度阈值，单位大致为 m/s。
        self.declare_parameter('moving_speed_threshold', 0.05)

        # 如果超过这个时间没有收到 sportmodestate，就认为状态过期。
        self.declare_parameter('state_timeout_sec', 3.0)

        self.sport_topic = self.get_parameter(
            'sport_topic'
        ).get_parameter_value().string_value

        self.lowstate_topic = self.get_parameter(
            'lowstate_topic'
        ).get_parameter_value().string_value

        self.inspection_state_topic = self.get_parameter(
            'inspection_state_topic'
        ).get_parameter_value().string_value

        self.status_json_topic = self.get_parameter(
            'status_json_topic'
        ).get_parameter_value().string_value

        self.publish_period_sec = self.get_parameter(
            'publish_period_sec'
        ).get_parameter_value().double_value

        self.moving_speed_threshold = self.get_parameter(
            'moving_speed_threshold'
        ).get_parameter_value().double_value

        self.state_timeout_sec = self.get_parameter(
            'state_timeout_sec'
        ).get_parameter_value().double_value

        # ============================================================
        # 2. 内部缓存
        # ============================================================

        self._lock = threading.Lock()

        self._last_sport_msg = None
        self._last_sport_time = None

        self._last_lowstate_msg = None
        self._last_lowstate_time = None

        self._last_simple_state = None

        # ============================================================
        # 3. QoS 设置
        # ============================================================

        # Unitree 状态话题属于传感器/状态类数据。
        # 用 BEST_EFFORT 更稳，避免 QoS 不兼容导致收不到消息。
        state_qos = QoSProfile(
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            durability=QoSDurabilityPolicy.VOLATILE,
        )

        # ============================================================
        # 4. 订阅真实 GO2 状态
        # ============================================================

        self.sport_sub = self.create_subscription(
            SportModeState,
            self.sport_topic,
            self.sport_callback,
            state_qos
        )

        self.lowstate_sub = self.create_subscription(
            LowState,
            self.lowstate_topic,
            self.lowstate_callback,
            state_qos
        )

        # ============================================================
        # 5. 发布给 backend bridge 和调试端
        # ============================================================

        self.inspection_state_pub = self.create_publisher(
            String,
            self.inspection_state_topic,
            10
        )

        self.status_json_pub = self.create_publisher(
            String,
            self.status_json_topic,
            10
        )

        self.timer = self.create_timer(
            self.publish_period_sec,
            self.publish_status
        )

        self.get_logger().info('go2_state_reader_node initialized')
        self.get_logger().info('sport_topic: {}'.format(self.sport_topic))
        self.get_logger().info('lowstate_topic: {}'.format(self.lowstate_topic))
        self.get_logger().info(
            'inspection_state_topic: {}'.format(self.inspection_state_topic)
        )
        self.get_logger().info(
            'status_json_topic: {}'.format(self.status_json_topic)
        )

    def sport_callback(self, msg):
        """
        /lf/sportmodestate 回调。
        """
        with self._lock:
            self._last_sport_msg = msg
            self._last_sport_time = time.time()

    def lowstate_callback(self, msg):
        """
        /lf/lowstate 回调。
        """
        with self._lock:
            self._last_lowstate_msg = msg
            self._last_lowstate_time = time.time()

    def get_msg_age(self, msg_time):
        """
        获取某条消息距离当前的时间差。
        """
        if msg_time is None:
            return None
        return time.time() - msg_time

    def extract_speed_norm(self, sport_msg):
        """
        从 SportModeState 中提取速度模长。

        常见字段：
            velocity: [vx, vy, vz]
        """
        if sport_msg is None:
            return 0.0

        velocity = safe_get(sport_msg, 'velocity', None)
        velocity_list = to_plain_list(velocity)

        if not isinstance(velocity_list, list) or len(velocity_list) < 2:
            return 0.0

        vx = to_number(velocity_list[0], 0.0)
        vy = to_number(velocity_list[1], 0.0)
        vz = 0.0

        if len(velocity_list) >= 3:
            vz = to_number(velocity_list[2], 0.0)

        return math.sqrt(vx * vx + vy * vy + vz * vz)

    def extract_battery_soc(self, lowstate_msg):
        """
        提取电池电量百分比。

        不同版本可能存在两种情况：
            1. lowstate_msg.battery_soc
            2. lowstate_msg.bms_state.soc
        """
        if lowstate_msg is None:
            return None

        battery_soc = safe_get(lowstate_msg, 'battery_soc', None)
        if battery_soc is not None:
            return to_number(battery_soc, None)

        bms_state = safe_get(lowstate_msg, 'bms_state', None)
        if bms_state is not None:
            soc = safe_get(bms_state, 'soc', None)
            if soc is not None:
                return to_number(soc, None)

        return None

    def estimate_simple_state(self, sport_msg, sport_age_sec):
        """
        估计简单业务状态。

        第一版规则：
            1. 没收到 sportmodestate：INIT
            2. sportmodestate 超时：ERROR
            3. 速度超过阈值：PATROLLING
            4. 否则：IDLE

        注意：
            PATROLLING 这里表示“机器人正在运动”。
            后续接入巡检任务状态机后，可以再区分：
                MOVING
                PATROLLING
                PAUSED
                STOPPED
        """
        if sport_msg is None:
            return 'INIT'

        if sport_age_sec is not None and sport_age_sec > self.state_timeout_sec:
            return 'ERROR'

        speed_norm = self.extract_speed_norm(sport_msg)

        if speed_norm > self.moving_speed_threshold:
            return 'PATROLLING'

        return 'IDLE'

    def build_status_json(self, sport_msg, lowstate_msg, sport_age_sec, lowstate_age_sec):
        """
        构造详细状态 JSON。

        这个 JSON 会发布到 /go2_status_json。
        后续后台可扩展显示这些字段。
        """
        simple_state = self.estimate_simple_state(sport_msg, sport_age_sec)
        speed_norm = self.extract_speed_norm(sport_msg)
        battery_soc = self.extract_battery_soc(lowstate_msg)

        status = {
            'type': 'go2_status',
            'timestamp': utc_timestamp(),
            'simple_state': simple_state,
            'sport_topic': self.sport_topic,
            'lowstate_topic': self.lowstate_topic,
            'sport_received': sport_msg is not None,
            'lowstate_received': lowstate_msg is not None,
            'sport_age_sec': sport_age_sec,
            'lowstate_age_sec': lowstate_age_sec,
            'speed_norm': speed_norm,
            'battery_soc': battery_soc,
        }

        if sport_msg is not None:
            status['sport'] = {
                'mode': to_number(safe_get(sport_msg, 'mode', None), None),
                'progress': to_number(safe_get(sport_msg, 'progress', None), None),
                'gait_type': to_number(safe_get(sport_msg, 'gait_type', None), None),
                'foot_raise_height': to_number(
                    safe_get(sport_msg, 'foot_raise_height', None),
                    None
                ),
                'body_height': to_number(
                    safe_get(sport_msg, 'body_height', None),
                    None
                ),
                'position': to_plain_list(
                    safe_get(sport_msg, 'position', None)
                ),
                'velocity': to_plain_list(
                    safe_get(sport_msg, 'velocity', None)
                ),
                'yaw_speed': to_number(
                    safe_get(sport_msg, 'yaw_speed', None),
                    None
                ),
                'range_obstacle': to_plain_list(
                    safe_get(sport_msg, 'range_obstacle', None)
                ),
                'foot_position_body': to_plain_list(
                    safe_get(sport_msg, 'foot_position_body', None)
                ),
                'foot_speed_body': to_plain_list(
                    safe_get(sport_msg, 'foot_speed_body', None)
                ),
            }
        else:
            status['sport'] = None

        if lowstate_msg is not None:
            imu_state = safe_get(lowstate_msg, 'imu_state', None)

            if imu_state is not None:
                imu_json = {
                    'quaternion': to_plain_list(
                        safe_get(imu_state, 'quaternion', None)
                    ),
                    'gyroscope': to_plain_list(
                        safe_get(imu_state, 'gyroscope', None)
                    ),
                    'accelerometer': to_plain_list(
                        safe_get(imu_state, 'accelerometer', None)
                    ),
                    'rpy': to_plain_list(
                        safe_get(imu_state, 'rpy', None)
                    ),
                    'temperature': to_number(
                        safe_get(imu_state, 'temperature', None),
                        None
                    ),
                }
            else:
                imu_json = None

            bms_state = safe_get(lowstate_msg, 'bms_state', None)
            if bms_state is not None:
                bms_json = {
                    'soc': to_number(safe_get(bms_state, 'soc', None), None),
                    'current': to_number(safe_get(bms_state, 'current', None), None),
                    'cycle': to_number(safe_get(bms_state, 'cycle', None), None),
                    'status': to_number(safe_get(bms_state, 'status', None), None),
                }
            else:
                bms_json = None

            status['lowstate'] = {
                'battery_soc': battery_soc,
                'power_v': to_number(safe_get(lowstate_msg, 'power_v', None), None),
                'power_a': to_number(safe_get(lowstate_msg, 'power_a', None), None),
                'foot_force': to_plain_list(
                    safe_get(lowstate_msg, 'foot_force', None)
                ),
                'foot_force_est': to_plain_list(
                    safe_get(lowstate_msg, 'foot_force_est', None)
                ),
                'imu_state': imu_json,
                'bms_state': bms_json,
            }
        else:
            status['lowstate'] = None

        return status

    def publish_status(self):
        """
        周期性发布简单状态和详细 JSON 状态。
        """
        with self._lock:
            sport_msg = self._last_sport_msg
            sport_time = self._last_sport_time
            lowstate_msg = self._last_lowstate_msg
            lowstate_time = self._last_lowstate_time

        sport_age_sec = self.get_msg_age(sport_time)
        lowstate_age_sec = self.get_msg_age(lowstate_time)

        status = self.build_status_json(
            sport_msg,
            lowstate_msg,
            sport_age_sec,
            lowstate_age_sec
        )

        simple_state = status.get('simple_state', 'INIT')

        # 发布给 backend_client_node。
        simple_msg = String()
        simple_msg.data = simple_state
        self.inspection_state_pub.publish(simple_msg)

        # 发布详细 JSON。
        json_msg = String()
        json_msg.data = json.dumps(status, ensure_ascii=False)
        self.status_json_pub.publish(json_msg)

        # 只有状态变化时才打印，避免刷屏。
        if simple_state != self._last_simple_state:
            self.get_logger().info(
                'Simple state changed: {} -> {}'.format(
                    self._last_simple_state,
                    simple_state
                )
            )
            self._last_simple_state = simple_state


def main(args=None):
    """
    ROS2 节点入口。
    """
    rclpy.init(args=args)

    node = Go2StateReaderNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('KeyboardInterrupt received, shutting down...')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
