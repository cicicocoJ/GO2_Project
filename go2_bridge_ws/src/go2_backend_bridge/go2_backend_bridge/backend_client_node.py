#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend_client_node.py

GO2 巡检机器人项目的机器人端后台中转节点。

升级版功能：

    1. 订阅 /inspection_state
       获取机器人简单业务状态，例如 IDLE、PATROLLING、ERROR。

    2. 订阅 /go2_status_json
       获取 GO2 真实状态读取节点发布的详细 JSON，
       包括电量、速度、位置、姿态、底层状态等。

    3. 通过 WebSocket 周期性上传完整状态到 FastAPI 后台。

    4. 接收后台 command，并转发到 ROS2 /backend_command。

注意：
    本节点仍然不直接控制 GO2。
    它只是“后台通信中转站”。
"""

import asyncio
import json
import os
import threading
import time
import uuid
from datetime import datetime

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

import websockets


def utc_timestamp():
    """
    生成 UTC 时间戳字符串。

    示例：
        2026-07-01T09:30:00Z
    """
    return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


class BackendClientNode(Node):
    """
    机器人端后台中转节点。

    ROS2 侧：
        订阅：
            /inspection_state     std_msgs/String
            /go2_status_json      std_msgs/String

        发布：
            /backend_command      std_msgs/String

    后台通信侧：
        WebSocket 连接 FastAPI 后台。
    """

    def __init__(self):
        super().__init__('backend_client_node')

        # ============================================================
        # 1. ROS2 参数
        # ============================================================

        self.declare_parameter('robot_id', 'GO2_001')

        default_server_url = os.environ.get(
            'GO2_BACKEND_SERVER_URL',
            'ws://127.0.0.1:8000/ws/robot/GO2_001'
        )

        self.declare_parameter(
            'server_url',
            default_server_url
        )

        self.declare_parameter('upload_period_sec', 1.0)
        self.declare_parameter('reconnect_delay_sec', 3.0)

        # 简单状态输入话题。
        self.declare_parameter(
            'inspection_state_topic',
            '/inspection_state'
        )

        # GO2 详细状态 JSON 输入话题。
        self.declare_parameter(
            'go2_status_json_topic',
            '/go2_status_json'
        )

        self.robot_id = self.get_parameter(
            'robot_id'
        ).get_parameter_value().string_value

        self.server_url = self.get_parameter(
            'server_url'
        ).get_parameter_value().string_value

        self.upload_period_sec = self.get_parameter(
            'upload_period_sec'
        ).get_parameter_value().double_value

        self.reconnect_delay_sec = self.get_parameter(
            'reconnect_delay_sec'
        ).get_parameter_value().double_value

        self.inspection_state_topic = self.get_parameter(
            'inspection_state_topic'
        ).get_parameter_value().string_value

        self.go2_status_json_topic = self.get_parameter(
            'go2_status_json_topic'
        ).get_parameter_value().string_value

        # ============================================================
        # 2. 节点内部状态缓存
        # ============================================================

        self._lock = threading.Lock()

        # 简单业务状态。
        self._state = 'INIT'
        self._last_state_update_time = None

        # GO2 详细状态 JSON。
        self._go2_status = None
        self._last_go2_status_update_time = None
        self._last_go2_status_raw = None

        # ============================================================
        # 3. ROS2 topic 接口
        # ============================================================

        self.state_sub = self.create_subscription(
            String,
            self.inspection_state_topic,
            self.inspection_state_callback,
            10
        )

        self.go2_status_sub = self.create_subscription(
            String,
            self.go2_status_json_topic,
            self.go2_status_json_callback,
            10
        )

        self.command_pub = self.create_publisher(
            String,
            '/backend_command',
            10
        )

        self.get_logger().info('backend_client_node initialized')
        self.get_logger().info('robot_id: {}'.format(self.robot_id))
        self.get_logger().info('server_url: {}'.format(self.server_url))
        self.get_logger().info(
            'inspection_state_topic: {}'.format(
                self.inspection_state_topic
            )
        )
        self.get_logger().info(
            'go2_status_json_topic: {}'.format(
                self.go2_status_json_topic
            )
        )

    def inspection_state_callback(self, msg):
        """
        /inspection_state 回调函数。

        输入示例：
            IDLE
            PATROLLING
            ERROR

        这个状态会作为后台 status 的主 state 字段。
        """
        with self._lock:
            self._state = msg.data
            self._last_state_update_time = time.time()

        self.get_logger().info(
            'Received {}: {}'.format(
                self.inspection_state_topic,
                msg.data
            )
        )

    def go2_status_json_callback(self, msg):
        """
        /go2_status_json 回调函数。

        go2_state_reader_node 会把 GO2 真实状态整理成 JSON 字符串，
        本节点收到后缓存起来，下一次状态上传时一起发送给后台。
        """
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warning(
                'Received invalid go2_status_json: {}'.format(msg.data)
            )
            return

        with self._lock:
            self._go2_status = data
            self._last_go2_status_update_time = time.time()
            self._last_go2_status_raw = msg.data

        simple_state = data.get('simple_state')
        battery_soc = data.get('battery_soc')
        speed_norm = data.get('speed_norm')

        self.get_logger().debug(
            'Received go2_status_json: simple_state={}, battery_soc={}, speed_norm={}'.format(
                simple_state,
                battery_soc,
                speed_norm
            )
        )

    def make_register_payload(self):
        """
        生成机器人注册消息。
        """
        return {
            'type': 'register',
            'robot_id': self.robot_id,
            'timestamp': utc_timestamp(),
            'client': 'go2_backend_bridge',
            'version': '0.2.0',
            'features': [
                'inspection_state',
                'go2_status_json',
                'backend_command',
                'command_ack',
            ],
        }

    def make_status_payload(self):
        """
        生成上传给后台的机器人状态消息。

        第一层字段给后台快速显示：
            state
            battery
            speed_norm
            position
            yaw_speed

        go2_status 字段保留完整详细状态，后续后台需要更多信息时可直接使用。
        """
        with self._lock:
            state = self._state
            last_state_update_time = self._last_state_update_time
            go2_status = self._go2_status
            last_go2_status_update_time = self._last_go2_status_update_time

        now = time.time()

        state_age_sec = None
        if last_state_update_time is not None:
            state_age_sec = now - last_state_update_time

        go2_status_age_sec = None
        if last_go2_status_update_time is not None:
            go2_status_age_sec = now - last_go2_status_update_time

        battery = None
        speed_norm = None
        position = None
        velocity = None
        yaw_speed = None
        go2_simple_state = None
        sport_received = False
        lowstate_received = False

        if isinstance(go2_status, dict):
            battery = go2_status.get('battery_soc')
            speed_norm = go2_status.get('speed_norm')
            go2_simple_state = go2_status.get('simple_state')
            sport_received = bool(go2_status.get('sport_received', False))
            lowstate_received = bool(go2_status.get('lowstate_received', False))

            sport = go2_status.get('sport')
            if isinstance(sport, dict):
                position = sport.get('position')
                velocity = sport.get('velocity')
                yaw_speed = sport.get('yaw_speed')

            # 如果 /inspection_state 暂时没有更新，但详细状态里有 simple_state，
            # 可以作为兜底状态。
            if state in ('INIT', '', None) and go2_simple_state:
                state = go2_simple_state

        return {
            'type': 'status',
            'robot_id': self.robot_id,
            'timestamp': utc_timestamp(),

            # 后台原有字段。
            'state': state,
            'battery': battery,
            'current_checkpoint': None,

            # 新增真实 GO2 状态摘要。
            'speed_norm': speed_norm,
            'position': position,
            'velocity': velocity,
            'yaw_speed': yaw_speed,
            'go2_simple_state': go2_simple_state,
            'sport_received': sport_received,
            'lowstate_received': lowstate_received,

            # 状态新鲜度。
            'last_state_update_time': last_state_update_time,
            'state_age_sec': state_age_sec,
            'last_go2_status_update_time': last_go2_status_update_time,
            'go2_status_age_sec': go2_status_age_sec,
            'go2_status_received': go2_status is not None,

            # 完整详细状态。
            'go2_status': go2_status,
        }

    def publish_backend_command(self, command_msg):
        """
        把后台下发的 command 转发到 ROS2 topic /backend_command。
        """
        ros_msg = String()
        ros_msg.data = json.dumps(command_msg, ensure_ascii=False)
        self.command_pub.publish(ros_msg)

        command = command_msg.get('command', '')
        command_id = command_msg.get('command_id', '')

        self.get_logger().info(
            'Published /backend_command: command={}, command_id={}'.format(
                command,
                command_id
            )
        )


async def status_upload_loop(node, websocket):
    """
    状态上传协程。
    """
    while rclpy.ok():
        payload = node.make_status_payload()
        await websocket.send(json.dumps(payload, ensure_ascii=False))
        await asyncio.sleep(node.upload_period_sec)


async def command_receive_loop(node, websocket):
    """
    后台命令接收协程。

    收到后台 command 后：
        1. 发布到 /backend_command
        2. 回传 command_ack
    """
    while rclpy.ok():
        raw_msg = await websocket.recv()

        try:
            data = json.loads(raw_msg)
        except json.JSONDecodeError:
            node.get_logger().warning(
                'Received non-JSON message: {}'.format(raw_msg)
            )
            continue

        msg_type = data.get('type')

        if msg_type != 'command':
            node.get_logger().info(
                'Received non-command message: {}'.format(data)
            )
            continue

        command = data.get('command')
        command_id = data.get('command_id')

        if not command:
            node.get_logger().warning(
                'Received command without command field: {}'.format(data)
            )
            continue

        if not command_id:
            command_id = str(uuid.uuid4())
            data['command_id'] = command_id

        if 'robot_id' not in data:
            data['robot_id'] = node.robot_id

        node.publish_backend_command(data)

        ack_payload = {
            'type': 'command_ack',
            'robot_id': node.robot_id,
            'timestamp': utc_timestamp(),
            'command_id': command_id,
            'command': command,
            'accepted': True,
            'message': 'Command received and published to /backend_command',
        }

        try:
            await websocket.send(json.dumps(ack_payload, ensure_ascii=False))
            node.get_logger().info(
                'Sent command_ack: command={}, command_id={}'.format(
                    command,
                    command_id
                )
            )
        except Exception as exc:
            node.get_logger().warning(
                'Failed to send command_ack: {}'.format(exc)
            )


async def websocket_main_loop(node):
    """
    WebSocket 主循环。

    连接后台，发送 register，上传 status，接收 command。
    断线后自动重连。
    """
    while rclpy.ok():
        try:
            node.get_logger().info(
                'Connecting to backend: {}'.format(node.server_url)
            )

            async with websockets.connect(
                node.server_url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
                max_size=4 * 1024 * 1024,
            ) as websocket:
                node.get_logger().info('WebSocket connected')

                register_payload = node.make_register_payload()
                await websocket.send(
                    json.dumps(register_payload, ensure_ascii=False)
                )
                node.get_logger().info('Register message sent')

                status_task = asyncio.create_task(
                    status_upload_loop(node, websocket)
                )
                receive_task = asyncio.create_task(
                    command_receive_loop(node, websocket)
                )

                done, pending = await asyncio.wait(
                    [status_task, receive_task],
                    return_when=asyncio.FIRST_EXCEPTION
                )

                for task in pending:
                    task.cancel()

                for task in done:
                    exc = task.exception()
                    if exc:
                        raise exc

        except asyncio.CancelledError:
            break

        except Exception as exc:
            node.get_logger().warning(
                'WebSocket disconnected or failed: {}. '
                'Reconnecting in {:.1f}s...'.format(
                    exc,
                    node.reconnect_delay_sec
                )
            )
            await asyncio.sleep(node.reconnect_delay_sec)


def main(args=None):
    """
    ROS2 节点入口函数。
    """
    rclpy.init(args=args)

    node = BackendClientNode()

    executor = rclpy.executors.SingleThreadedExecutor()
    executor.add_node(node)

    spin_thread = threading.Thread(
        target=executor.spin,
        daemon=True
    )
    spin_thread.start()

    try:
        asyncio.run(websocket_main_loop(node))

    except KeyboardInterrupt:
        node.get_logger().info('KeyboardInterrupt received, shutting down...')

    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()
        spin_thread.join(timeout=1.0)


if __name__ == '__main__':
    main()
