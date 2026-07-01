#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend_client_node.py

GO2 巡检机器人项目的机器人端中转节点。

第一版最小闭环：

    ROS2 topic /inspection_state
        -> backend_client_node
        -> WebSocket
        -> FastAPI 后台
        -> HTTP command 接口
        -> WebSocket
        -> ROS2 topic /backend_command

说明：
1. 本版本只使用 std_msgs/String。
2. 不依赖 Unitree 自定义消息。
3. 不接入真实导航、图像识别、SLAM 或 GO2 SDK。
4. 主要目的是验证 Jetson 与后台之间的通信链路。
"""

import asyncio
import json
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
        2026-06-30T09:30:00Z

    后台收到状态或应答时，可以用这个字段判断消息产生时间。
    """
    return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


class BackendClientNode(Node):
    """
    机器人端后台中转节点。

    ROS2 侧功能：
        订阅：
            /inspection_state  std_msgs/String
            表示机器人当前巡检状态，例如 IDLE、PATROLLING、PAUSED。

        发布：
            /backend_command   std_msgs/String
            用于把后台下发的 command 转发到 ROS2 内部。

    后台通信侧功能：
        通过 WebSocket 连接 FastAPI 后台：
            ws://<后台IP>:8000/ws/robot/GO2_001

        主动发送：
            register    机器人注册消息
            status      机器人状态消息

        被动接收：
            command     后台命令

        回复：
            command_ack 命令接收确认
    """

    def __init__(self):
        super().__init__('backend_client_node')

        # ============================================================
        # 1. 声明 ROS2 参数
        # ============================================================

        # 机器人编号。
        # 后台通过 robot_id 区分不同机器人。
        self.declare_parameter('robot_id', 'GO2_001')

        # 后台 WebSocket 地址。
        #
        # 如果后台 server.py 跑在 Jetson 本机：
        #     ws://127.0.0.1:8000/ws/robot/GO2_001
        #
        # 如果后台 server.py 跑在笔记本电脑：
        #     ws://笔记本IP:8000/ws/robot/GO2_001
        self.declare_parameter(
            'server_url',
            'ws://127.0.0.1:8000/ws/robot/GO2_001'
        )

        # 状态上传周期，单位：秒。
        # 第一版设置为 1 秒上传一次状态。
        self.declare_parameter('upload_period_sec', 1.0)

        # WebSocket 断开后的重连等待时间，单位：秒。
        self.declare_parameter('reconnect_delay_sec', 3.0)

        # 读取 ROS2 参数值。
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

        # ============================================================
        # 2. 节点内部状态缓存
        # ============================================================

        # 由于 rclpy 的 spin 在一个线程中运行，而 asyncio 的 WebSocket
        # 循环在另一个上下文中运行，所以这里用锁保护共享状态。
        self._lock = threading.Lock()

        # 机器人初始状态。
        # 后续如果收到 /inspection_state，就会更新这个值。
        self._state = 'INIT'

        # 最近一次收到 /inspection_state 的本地时间戳。
        self._last_state_update_time = None

        # ============================================================
        # 3. ROS2 topic 接口
        # ============================================================

        # 订阅机器人状态。
        # 第一版用 std_msgs/String 简化验证。
        self.state_sub = self.create_subscription(
            String,
            '/inspection_state',
            self.inspection_state_callback,
            10
        )

        # 发布后台命令。
        # 第一版直接把完整 command JSON 转成 String 发布出去。
        self.command_pub = self.create_publisher(
            String,
            '/backend_command',
            10
        )

        self.get_logger().info('backend_client_node initialized')
        self.get_logger().info('robot_id: {}'.format(self.robot_id))
        self.get_logger().info('server_url: {}'.format(self.server_url))

    def inspection_state_callback(self, msg):
        """
        /inspection_state 的回调函数。

        输入示例：
            ros2 topic pub /inspection_state std_msgs/String "{data: 'PATROLLING'}" -r 1

        收到后：
            self._state = 'PATROLLING'

        后续 status_upload_loop 会每秒把这个状态上传给后台。
        """
        with self._lock:
            self._state = msg.data
            self._last_state_update_time = time.time()

        self.get_logger().info(
            'Received /inspection_state: {}'.format(msg.data)
        )

    def make_register_payload(self):
        """
        生成机器人注册消息。

        这个消息在 WebSocket 每次连接成功后发送一次。
        后台可以通过它知道是哪台机器人上线了。
        """
        return {
            'type': 'register',
            'robot_id': self.robot_id,
            'timestamp': utc_timestamp(),
            'client': 'go2_backend_bridge',
            'version': '0.1.0',
        }

    def make_status_payload(self):
        """
        生成机器人状态消息。

        第一版字段：
            robot_id             机器人编号
            timestamp            时间戳
            state                当前状态
            battery              电池电量，第一版先写 None
            current_checkpoint   当前巡检点，第一版先写 None

        后续可以把 battery 接入 GO2 真实状态，把 current_checkpoint
        接入巡检任务状态机。
        """
        with self._lock:
            state = self._state
            last_state_update_time = self._last_state_update_time

        return {
            'type': 'status',
            'robot_id': self.robot_id,
            'timestamp': utc_timestamp(),
            'state': state,
            'battery': None,
            'current_checkpoint': None,
            'last_state_update_time': last_state_update_time,
        }

    def publish_backend_command(self, command_msg):
        """
        把后台下发的 command 转发到 ROS2 topic /backend_command。

        第一版为了简单，直接发布 JSON 字符串。
        后续如果命令类型稳定，可以改成自定义 ROS2 msg。
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

    功能：
        每隔 upload_period_sec 秒读取一次节点内部状态，
        然后通过 WebSocket 发送给后台。

    只要 ROS2 没有关闭，并且 WebSocket 没有断开，就一直循环发送。
    """
    while rclpy.ok():
        payload = node.make_status_payload()
        await websocket.send(json.dumps(payload, ensure_ascii=False))
        await asyncio.sleep(node.upload_period_sec)


async def command_receive_loop(node, websocket):
    """
    后台命令接收协程。

    后台下发命令的 JSON 格式示例：

        {
            "type": "command",
            "robot_id": "GO2_001",
            "timestamp": "2026-06-30T09:30:00Z",
            "command_id": "cmd-xxx",
            "command": "PAUSE_TASK",
            "payload": {}
        }

    本节点收到后会：
        1. 检查 type 是否为 command；
        2. 检查 command 字段；
        3. 如果没有 command_id，则自动生成；
        4. 发布到 ROS2 topic /backend_command；
        5. 回传 command_ack 给后台。
    """
    while rclpy.ok():
        raw_msg = await websocket.recv()

        # 尝试把收到的字符串解析为 JSON。
        try:
            data = json.loads(raw_msg)
        except json.JSONDecodeError:
            node.get_logger().warning(
                'Received non-JSON message: {}'.format(raw_msg)
            )
            continue

        msg_type = data.get('type')

        # 第一版只处理 type=command 的消息。
        if msg_type != 'command':
            node.get_logger().info(
                'Received non-command message: {}'.format(data)
            )
            continue

        command = data.get('command')
        command_id = data.get('command_id')

        # command 字段是必须的。
        if not command:
            node.get_logger().warning(
                'Received command without command field: {}'.format(data)
            )
            continue

        # 如果后台没有给 command_id，本地生成一个，便于后续追踪。
        if not command_id:
            command_id = str(uuid.uuid4())
            data['command_id'] = command_id

        # 保证转发到 ROS2 的命令里带 robot_id。
        if 'robot_id' not in data:
            data['robot_id'] = node.robot_id

        # 将后台命令发布到 ROS2 内部。
        node.publish_backend_command(data)

        # 生成命令确认消息。
        ack_payload = {
            'type': 'command_ack',
            'robot_id': node.robot_id,
            'timestamp': utc_timestamp(),
            'command_id': command_id,
            'command': command,
            'accepted': True,
            'message': 'Command received and published to /backend_command',
        }

        # 回传 command_ack。
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

    功能：
        1. 连接后台；
        2. 连接成功后发送 register；
        3. 同时启动状态上传协程和命令接收协程；
        4. 如果连接断开，则等待 reconnect_delay_sec 后自动重连。

    这保证了后台重启、网络波动时，Jetson 端节点不会直接退出。
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
                max_size=2 * 1024 * 1024,
            ) as websocket:
                node.get_logger().info('WebSocket connected')

                # 每次 WebSocket 建立连接后，先发注册消息。
                register_payload = node.make_register_payload()
                await websocket.send(
                    json.dumps(register_payload, ensure_ascii=False)
                )
                node.get_logger().info('Register message sent')

                # 同时运行两个任务：
                # 1. 周期性上传状态；
                # 2. 接收后台命令。
                status_task = asyncio.create_task(
                    status_upload_loop(node, websocket)
                )
                receive_task = asyncio.create_task(
                    command_receive_loop(node, websocket)
                )

                # 任意一个任务异常退出，就认为连接需要重建。
                done, pending = await asyncio.wait(
                    [status_task, receive_task],
                    return_when=asyncio.FIRST_EXCEPTION
                )

                # 取消还没结束的任务。
                for task in pending:
                    task.cancel()

                # 如果已结束的任务带异常，就抛出异常进入重连流程。
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

    setup.py 中的 console_scripts 会调用这里：

        backend_client_node = go2_backend_bridge.backend_client_node:main

    运行命令：

        ros2 run go2_backend_bridge backend_client_node

    这里采用：
        rclpy spin 放在线程中；
        asyncio WebSocket 主循环放在主线程中。
    """
    rclpy.init(args=args)

    node = BackendClientNode()

    executor = rclpy.executors.SingleThreadedExecutor()
    executor.add_node(node)

    # 用后台线程处理 ROS2 subscription / publisher 回调。
    spin_thread = threading.Thread(
        target=executor.spin,
        daemon=True
    )
    spin_thread.start()

    try:
        # 主线程运行 WebSocket 异步循环。
        asyncio.run(websocket_main_loop(node))

    except KeyboardInterrupt:
        node.get_logger().info('KeyboardInterrupt received, shutting down...')

    finally:
        # 退出时清理 ROS2 节点和 executor。
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()
        spin_thread.join(timeout=1.0)


if __name__ == '__main__':
    main()
