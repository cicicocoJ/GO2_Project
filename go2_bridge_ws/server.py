#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server.py

GO2 巡检机器人项目的最小 FastAPI 后台 Demo。

第一版通信闭环：

    HTTP command 接口
        -> FastAPI 后台
        -> WebSocket
        -> Jetson backend_client_node
        -> ROS2 topic /backend_command

同时，Jetson 会通过 WebSocket 周期性上传机器人状态：

    ROS2 topic /inspection_state
        -> backend_client_node
        -> WebSocket
        -> FastAPI 后台

说明：
1. 本文件只是最小后台 Demo。
2. 不包含数据库。
3. 不包含登录鉴权。
4. 不包含前端页面。
5. 只用于验证 Jetson 与后台之间的通信闭环。
"""

import json
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect


# ============================================================
# 1. 创建 FastAPI 应用
# ============================================================

# Uvicorn 启动命令：
#
#     python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
#
# 其中：
#     server 表示 server.py
#     app    表示下面这个 FastAPI 对象
app = FastAPI(title='GO2 Backend Demo')


# ============================================================
# 2. 后台内存状态缓存
# ============================================================

# 当前已连接的机器人。
#
# key:
#     robot_id，例如 "GO2_001"
#
# value:
#     WebSocket 连接对象
connected_robots: Dict[str, WebSocket] = {}


# 每台机器人最近一次上传的状态。
#
# key:
#     robot_id
#
# value:
#     status JSON
last_status: Dict[str, Dict[str, Any]] = {}


# 每台机器人最近一次命令确认。
#
# key:
#     robot_id
#
# value:
#     command_ack JSON
last_ack: Dict[str, Dict[str, Any]] = {}


def now_ts():
    """
    生成当前 UTC 时间戳。

    后台下发 command 时会带上这个时间戳。
    """
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


# ============================================================
# 3. HTTP 接口：后台健康检查
# ============================================================

@app.get('/')
async def root():
    """
    后台健康检查接口。

    浏览器访问：
        http://127.0.0.1:8000/

    返回当前后台是否运行，以及已经连接的机器人列表。
    """
    return {
        'name': 'GO2 Backend Demo',
        'message': 'Backend is running',
        'connected_robots': list(connected_robots.keys()),
    }


# ============================================================
# 4. WebSocket 接口：机器人连接入口
# ============================================================

@app.websocket('/ws/robot/{robot_id}')
async def robot_websocket(websocket: WebSocket, robot_id: str):
    """
    机器人 WebSocket 连接接口。

    Jetson 上的 backend_client_node 会连接到：

        ws://<后台IP>:8000/ws/robot/GO2_001

    后台通过这个 WebSocket 接收：
        1. register
        2. status
        3. command_ack

    后台也通过这个 WebSocket 下发：
        1. command
    """
    await websocket.accept()

    # 保存当前机器人连接。
    # 如果同一个 robot_id 重新连接，会覆盖旧连接。
    connected_robots[robot_id] = websocket

    print('[WS] Robot connected: {}'.format(robot_id))

    try:
        while True:
            # 接收机器人发来的文本消息。
            raw_msg = await websocket.receive_text()

            # 尝试解析 JSON。
            try:
                data = json.loads(raw_msg)
            except json.JSONDecodeError:
                print('[WS][{}] Non-JSON message: {}'.format(robot_id, raw_msg))
                continue

            msg_type = data.get('type')

            # 机器人注册消息。
            if msg_type == 'register':
                print(
                    '[REGISTER][{}] {}'.format(
                        robot_id,
                        json.dumps(data, ensure_ascii=False)
                    )
                )

            # 机器人状态消息。
            elif msg_type == 'status':
                last_status[robot_id] = data
                print(
                    '[STATUS][{}] {}'.format(
                        robot_id,
                        json.dumps(data, ensure_ascii=False)
                    )
                )

            # 命令确认消息。
            elif msg_type == 'command_ack':
                last_ack[robot_id] = data
                print(
                    '[ACK][{}] {}'.format(
                        robot_id,
                        json.dumps(data, ensure_ascii=False)
                    )
                )

            # 其他消息暂时只打印，不做处理。
            else:
                print(
                    '[WS][{}] {}'.format(
                        robot_id,
                        json.dumps(data, ensure_ascii=False)
                    )
                )

    except WebSocketDisconnect:
        print('[WS] Robot disconnected: {}'.format(robot_id))

    except Exception as exc:
        print('[WS] Robot {} error: {}'.format(robot_id, exc))

    finally:
        # 如果当前断开的 websocket 正是已保存的连接，则从字典中删除。
        # 这样可以避免旧连接关闭时误删新连接。
        current_ws = connected_robots.get(robot_id)
        if current_ws is websocket:
            connected_robots.pop(robot_id, None)


# ============================================================
# 5. HTTP 接口：查看机器人列表与缓存状态
# ============================================================

@app.get('/api/robots')
async def list_robots():
    """
    查看当前连接机器人、最近状态、最近 ACK。

    示例：
        curl http://127.0.0.1:8000/api/robots
    """
    return {
        'connected_robots': list(connected_robots.keys()),
        'last_status': last_status,
        'last_ack': last_ack,
    }


@app.get('/api/robot/{robot_id}/status')
async def get_robot_status(robot_id: str):
    """
    查看某台机器人最近一次状态。

    示例：
        curl http://127.0.0.1:8000/api/robot/GO2_001/status
    """
    if robot_id not in last_status:
        raise HTTPException(
            status_code=404,
            detail='No status received from robot {}'.format(robot_id)
        )

    return last_status[robot_id]


# ============================================================
# 6. HTTP 接口：向机器人发送命令
# ============================================================

@app.post('/api/robot/{robot_id}/command/{command}')
async def send_robot_command(
    robot_id: str,
    command: str,
    payload: Optional[Dict[str, Any]] = Body(default=None)
):
    """
    通过 HTTP 接口向机器人发送命令。

    后台收到 HTTP 请求后，会通过 WebSocket 把 command 发给机器人。

    示例 1：不带 payload

        curl -X POST http://127.0.0.1:8000/api/robot/GO2_001/command/PAUSE_TASK

    示例 2：带 payload

        curl -X POST http://127.0.0.1:8000/api/robot/GO2_001/command/START_TASK \\
          -H "Content-Type: application/json" \\
          -d '{"route_id": "factory_route_001", "task_id": "task_demo_001"}'
    """
    websocket = connected_robots.get(robot_id)

    # 如果机器人没有连接，无法下发命令。
    if websocket is None:
        raise HTTPException(
            status_code=404,
            detail='Robot {} is not connected'.format(robot_id)
        )

    # 为每条命令生成唯一 command_id，方便后续追踪 ACK。
    command_id = 'cmd-{}-{}'.format(
        int(time.time() * 1000),
        uuid.uuid4().hex[:8]
    )

    # 后台下发给机器人的命令 JSON。
    command_msg = {
        'type': 'command',
        'robot_id': robot_id,
        'timestamp': now_ts(),
        'command_id': command_id,
        'command': command,
        'payload': payload or {},
    }

    try:
        # 通过 WebSocket 发送给对应机器人。
        await websocket.send_text(json.dumps(command_msg, ensure_ascii=False))

    except Exception as exc:
        # 如果发送失败，说明连接可能已经断开，删除缓存连接。
        connected_robots.pop(robot_id, None)

        raise HTTPException(
            status_code=503,
            detail='Failed to send command to robot {}: {}'.format(
                robot_id,
                exc
            )
        )

    print(
        '[COMMAND][{}] {}'.format(
            robot_id,
            json.dumps(command_msg, ensure_ascii=False)
        )
    )

    # HTTP 接口返回发送结果和 command_id。
    return {
        'sent': True,
        'robot_id': robot_id,
        'command': command,
        'command_id': command_id,
    }
