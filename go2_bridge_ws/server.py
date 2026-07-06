#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server.py

GO2 巡检机器人项目的 FastAPI 后台 Demo + Dashboard 页面。

功能：
    1. 接收 Jetson backend_client_node 的 WebSocket 连接；
    2. 接收机器人 register / status / command_ack；
    3. 提供 HTTP command 接口；
    4. 提供 Dashboard 页面，用于查看 GO2 状态和下发命令。

运行命令：
    python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
"""

import json
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse


# ============================================================
# 1. 创建 FastAPI 应用
# ============================================================

app = FastAPI(title='GO2 Backend Demo')


# ============================================================
# 2. 后台内存状态缓存
# ============================================================

# 当前已连接的机器人。
connected_robots: Dict[str, WebSocket] = {}

# 每台机器人最近一次上传的状态。
last_status: Dict[str, Dict[str, Any]] = {}

# 每台机器人最近一次命令确认。
last_ack: Dict[str, Dict[str, Any]] = {}

# 每台机器人最近一次在线时间。
last_seen_time: Dict[str, float] = {}


def now_ts():
    """
    生成当前 UTC 时间戳。
    """
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def make_robot_summary(robot_id: str):
    """
    生成机器人摘要信息，供 Dashboard 和 API 使用。
    """
    status = last_status.get(robot_id)
    ack = last_ack.get(robot_id)

    connected = robot_id in connected_robots
    seen = last_seen_time.get(robot_id)

    age_sec = None
    if seen is not None:
        age_sec = time.time() - seen

    return {
        'robot_id': robot_id,
        'connected': connected,
        'last_seen_time': seen,
        'last_seen_age_sec': age_sec,
        'last_status': status,
        'last_ack': ack,
    }


# ============================================================
# 3. Dashboard 页面
# ============================================================

DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>GO2 Backend Dashboard</title>
  <style>
    :root {
      --bg: #f4f6f8;
      --card: #ffffff;
      --text: #1f2937;
      --muted: #6b7280;
      --dark: #111827;
      --blue: #2563eb;
      --blue-hover: #1d4ed8;
      --green: #059669;
      --orange: #f59e0b;
      --red: #dc2626;
      --gray: #4b5563;
      --border: #d1d5db;
    }

    body {
      margin: 0;
      font-family: Arial, "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--text);
    }

    header {
      background: var(--dark);
      color: white;
      padding: 18px 28px;
    }

    header h1 {
      margin: 0;
      font-size: 24px;
    }

    header p {
      margin: 6px 0 0;
      color: #cbd5e1;
      font-size: 14px;
    }

    main {
      padding: 20px 24px 28px;
      max-width: 1380px;
      margin: 0 auto;
    }

    .row {
      display: flex;
      gap: 14px;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }

    .card {
      background: var(--card);
      border-radius: 12px;
      padding: 16px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
      flex: 1;
      min-width: 180px;
      box-sizing: border-box;
    }

    .card h2 {
      margin: 0 0 10px;
      font-size: 17px;
      color: #111827;
    }

    .metric {
      font-size: 26px;
      font-weight: bold;
      margin: 6px 0;
    }

    .label {
      font-size: 13px;
      color: var(--muted);
    }

    .status-online {
      color: #16a34a;
    }

    .status-offline {
      color: var(--red);
    }

    .small {
      font-size: 13px;
      color: var(--muted);
      line-height: 1.45;
    }

    input {
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 9px 11px;
      font-size: 14px;
      min-width: 160px;
      box-sizing: border-box;
    }

    button {
      border: none;
      border-radius: 8px;
      padding: 10px 14px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 700;
      background: var(--blue);
      color: white;
    }

    button:hover {
      background: var(--blue-hover);
    }

    button:disabled {
      opacity: 0.65;
      cursor: not-allowed;
    }

    button.secondary { background: var(--gray); }
    button.secondary:hover { background: #374151; }
    button.warning { background: var(--orange); }
    button.warning:hover { background: #d97706; }
    button.danger { background: var(--red); }
    button.danger:hover { background: #b91c1c; }
    button.green { background: var(--green); }
    button.green:hover { background: #047857; }

    .teleop-layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 340px;
      gap: 16px;
      align-items: start;
      margin: 14px 0;
    }

    .video-card,
    .control-card {
      background: var(--card);
      border-radius: 14px;
      padding: 16px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
      box-sizing: border-box;
    }

    .video-card {
      min-width: 0;
    }

    .video-card h2,
    .control-card h2 {
      margin: 0 0 12px;
      font-size: 18px;
    }

    .camera-stream {
      display: block;
      width: 100%;
      max-width: 860px;
      height: auto;
      aspect-ratio: 4 / 3;
      object-fit: contain;
      background: #000;
      border-radius: 12px;
      border: 1px solid var(--border);
    }

    .control-card {
      position: sticky;
      top: 12px;
    }

    .control-section-title {
      font-weight: 700;
      margin: 12px 0 8px;
      color: #374151;
    }

    .move-grid {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 8px;
      margin-bottom: 10px;
    }

    .turn-row,
    .pose-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-bottom: 8px;
    }

    .single-row {
      display: grid;
      grid-template-columns: 1fr;
      gap: 8px;
      margin-bottom: 8px;
    }

    .ctrl-btn {
      min-height: 44px;
    }

    .ctrl-btn.stop {
      background: var(--orange);
    }

    .ctrl-btn.stop:hover {
      background: #d97706;
    }

    .ctrl-btn.emergency {
      background: var(--red);
      min-height: 52px;
      font-size: 18px;
    }

    .ctrl-btn.emergency:hover {
      background: #b91c1c;
    }

    .motion-status {
      margin-top: 10px;
      padding: 10px;
      border-radius: 8px;
      background: #f6f8fa;
      border: 1px solid var(--border);
      font-size: 13px;
      line-height: 1.45;
      color: #374151;
    }

    .grid-two {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-top: 14px;
    }

    pre {
      background: #0f172a;
      color: #e5e7eb;
      border-radius: 12px;
      padding: 16px;
      overflow-x: auto;
      max-height: 360px;
      font-size: 13px;
      line-height: 1.5;
      margin: 0;
    }

    .log {
      background: #111827;
      color: #e5e7eb;
      border-radius: 12px;
      padding: 12px;
      height: 180px;
      overflow-y: auto;
      font-size: 13px;
      line-height: 1.5;
    }

    @media (max-width: 1100px) {
      .teleop-layout {
        grid-template-columns: 1fr;
      }

      .control-card {
        position: static;
      }

      .camera-stream {
        max-width: 100%;
      }
    }

    @media (max-width: 800px) {
      main { padding: 16px; }
      .grid-two { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>GO2 巡检机器人后台 Dashboard</h1>
    <p>查看 Jetson 上传的真实 GO2 状态，并通过 HTTP/WebSocket 链路下发命令。</p>
  </header>

  <main>
    <div class="row">
      <div class="card">
        <h2>机器人选择</h2>
        <input id="robotIdInput" value="GO2_001" />
        <button onclick="refreshStatus()">刷新状态</button>
        <p class="small">默认 robot_id: GO2_001</p>
      </div>

      <div class="card">
        <h2>连接状态</h2>
        <div id="onlineStatus" class="metric status-offline">UNKNOWN</div>
        <div class="label">WebSocket 在线状态</div>
      </div>

      <div class="card">
        <h2>当前业务状态</h2>
        <div id="stateValue" class="metric">-</div>
        <div class="label">state / go2_simple_state</div>
      </div>

      <div class="card">
        <h2>电量</h2>
        <div id="batteryValue" class="metric">-</div>
        <div class="label">battery / battery_soc</div>
      </div>
    </div>

    <div class="row">
      <div class="card">
        <h2>速度</h2>
        <div id="speedValue" class="metric">-</div>
        <div class="label">speed_norm</div>
      </div>

      <div class="card">
        <h2>位置</h2>
        <div id="positionValue" class="metric" style="font-size: 18px;">-</div>
        <div class="label">position</div>
      </div>

      <div class="card">
        <h2>状态新鲜度</h2>
        <div id="ageValue" class="metric">-</div>
        <div class="label">距离最近一次状态更新</div>
      </div>
    </div>

    <div class="teleop-layout">
      <div class="video-card">
        <h2>实时画面 / D435i RGB</h2>
        <img
          class="camera-stream"
          src="http://192.168.123.18:8081/video_feed"
          alt="D435i Live Stream"
        />
      </div>

      <div class="control-card">
        <h2>常用控制</h2>

        <div class="control-section-title">移动控制</div>
        <div class="move-grid">
          <div></div>
          <button class="ctrl-btn" onclick="handleGo2MoveClick('MOVE_FORWARD')">前进</button>
          <div></div>

          <button class="ctrl-btn" onclick="handleGo2MoveClick('MOVE_LEFT')">左移</button>
          <button class="ctrl-btn stop" onclick="sendGo2MotionCommand('STOP_MOVE')">停止</button>
          <button class="ctrl-btn" onclick="handleGo2MoveClick('MOVE_RIGHT')">右移</button>

          <div></div>
          <button class="ctrl-btn" onclick="handleGo2MoveClick('MOVE_BACKWARD')">后退</button>
          <div></div>
        </div>

        <div class="turn-row">
          <button class="ctrl-btn" onclick="sendGo2MotionCommand('TURN_LEFT')">左转</button>
          <button class="ctrl-btn" onclick="sendGo2MotionCommand('TURN_RIGHT')">右转</button>
        </div>

        <div class="control-section-title">姿态控制</div>
        <div class="pose-row">
          <button class="ctrl-btn green" onclick="sendGo2MotionCommand('STAND_UP')">站立</button>
          <button class="ctrl-btn warning" onclick="sendGo2MotionCommand('STAND_DOWN')">卧倒</button>
        </div>

        <div class="pose-row">
          <button class="ctrl-btn green" onclick="sendGo2MotionCommand('BALANCE_STAND')">平衡站立</button>
          <button class="ctrl-btn green" onclick="sendGo2MotionCommand('RECOVERY_STAND')">恢复站立</button>
        </div>

        <div class="control-section-title">巡检采集</div>
        <div class="single-row">
          <button class="ctrl-btn green" onclick="sendGo2MotionCommand('CAPTURE_IMAGE')">📷 拍照</button>
        </div>

        <div class="control-section-title">安全</div>
        <div class="single-row">
          <button class="ctrl-btn emergency" onclick="sendGo2MotionCommand('EMERGENCY_STOP')">急停</button>
        </div>

        <div id="go2MotionStatus" class="motion-status">运动控制状态：等待操作</div>
      </div>
    </div>

    <div class="grid-two">
      <div class="card">
        <h2>完整状态 JSON</h2>
        <pre id="statusJson">{}</pre>
      </div>

      <div class="card">
        <h2>操作日志</h2>
        <div id="logBox" class="log"></div>
      </div>
    </div>
  </main>

  <script>
    let go2LastCommandTimeMs = 0;
    const go2CommandCooldownMs = 900;

    const go2DangerCommands = new Set([
      "DAMP",
      "STAND_DOWN",
      "SIT"
    ]);

    const go2CommandNameMap = {
      "MOVE_FORWARD": "前进",
      "MOVE_BACKWARD": "后退",
      "MOVE_LEFT": "左移",
      "MOVE_RIGHT": "右移",
      "TURN_LEFT": "左转",
      "TURN_RIGHT": "右转",
      "STOP_MOVE": "停止",
      "EMERGENCY_STOP": "急停",
      "STAND_DOWN": "卧倒",
      "STAND_UP": "站立",
      "BALANCE_STAND": "平衡站立",
      "RECOVERY_STAND": "恢复站立",
      "SIT": "坐下",
      "RISE_SIT": "起坐",
      "DAMP": "阻尼保护",
      "CAPTURE_IMAGE": "拍照",
      "MOVE_FORWARD_CONTINUOUS": "连续前进",
      "MOVE_BACKWARD_CONTINUOUS": "连续后退",
      "MOVE_LEFT_CONTINUOUS": "连续左移",
      "MOVE_RIGHT_CONTINUOUS": "连续右移"
    };

    function getRobotId() {
      return document.getElementById('robotIdInput').value.trim() || 'GO2_001';
    }

    // GO2_DOUBLE_CLICK_CONTINUOUS_V2
    // 单击：普通短动作；双击：连续运动，直到点击停止/急停。
    const go2DoubleClickWindowMs = 350;

    const go2ContinuousMoveMap = {
      "MOVE_FORWARD": "MOVE_FORWARD_CONTINUOUS",
      "MOVE_BACKWARD": "MOVE_BACKWARD_CONTINUOUS",
      "MOVE_LEFT": "MOVE_LEFT_CONTINUOUS",
      "MOVE_RIGHT": "MOVE_RIGHT_CONTINUOUS"
    };

    let go2MoveClickTimer = null;
    let go2LastMoveClickCommand = null;
    let go2LastMoveClickTimeMs = 0;

    function handleGo2MoveClick(command) {
      const nowMs = Date.now();

      // 第二次点击：如果还是同一个方向，并且间隔足够短，就认为是双击
      if (
        go2MoveClickTimer &&
        go2LastMoveClickCommand === command &&
        nowMs - go2LastMoveClickTimeMs <= go2DoubleClickWindowMs
      ) {
        clearTimeout(go2MoveClickTimer);
        go2MoveClickTimer = null;

        const continuousCommand = go2ContinuousMoveMap[command];
        const commandCn = go2CommandNameMap[command] || command;
        const continuousCn = go2CommandNameMap[continuousCommand] || continuousCommand;

        log("检测到双击：" + commandCn + "，切换为 " + continuousCn + "，直到点击停止。");

        // 双击连续运动必须绕过防连点，否则会被第一下点击时间挡住
        sendGo2MotionCommand(continuousCommand, { bypassCooldown: true });
        return;
      }

      // 如果点了另一个方向，取消上一个等待中的单击
      if (go2MoveClickTimer) {
        clearTimeout(go2MoveClickTimer);
        go2MoveClickTimer = null;
      }

      go2LastMoveClickCommand = command;
      go2LastMoveClickTimeMs = nowMs;

      // 延迟一点点发送单击命令，给双击判断留时间
      go2MoveClickTimer = setTimeout(() => {
        go2MoveClickTimer = null;
        sendGo2MotionCommand(command);
      }, go2DoubleClickWindowMs);
    }

    function log(message) {
      const box = document.getElementById('logBox');
      const ts = new Date().toLocaleTimeString();
      box.innerHTML += `[${ts}] ${message}<br>`;
      box.scrollTop = box.scrollHeight;
    }

    function formatNumber(value, digits = 3) {
      if (value === null || value === undefined) return '-';
      if (typeof value === 'number') return value.toFixed(digits);
      return String(value);
    }

    function formatPosition(value) {
      if (!Array.isArray(value)) return '-';
      return '[' + value.map(v => formatNumber(v, 3)).join(', ') + ']';
    }

    function updateCards(data) {
      const status = data.last_status || data;

      const connected = data.connected !== undefined
        ? data.connected
        : true;

      const onlineEl = document.getElementById('onlineStatus');
      onlineEl.textContent = connected ? 'ONLINE' : 'OFFLINE';
      onlineEl.className = connected
        ? 'metric status-online'
        : 'metric status-offline';

      const state = status.state || status.go2_simple_state || '-';
      document.getElementById('stateValue').textContent = state;

      const battery = status.battery !== undefined && status.battery !== null
        ? status.battery
        : (
          status.go2_status && status.go2_status.battery_soc !== undefined
            ? status.go2_status.battery_soc
            : null
        );

      document.getElementById('batteryValue').textContent =
        battery === null || battery === undefined ? '-' : `${battery}%`;

      document.getElementById('speedValue').textContent =
        formatNumber(status.speed_norm, 3);

      document.getElementById('positionValue').textContent =
        formatPosition(status.position);

      const age = data.last_seen_age_sec !== undefined && data.last_seen_age_sec !== null
        ? data.last_seen_age_sec
        : status.go2_status_age_sec;

      document.getElementById('ageValue').textContent =
        age === null || age === undefined ? '-' : `${formatNumber(age, 1)} s`;

      document.getElementById('statusJson').textContent =
        JSON.stringify(data, null, 2);
    }

    async function refreshStatus() {
      const robotId = getRobotId();

      try {
        const res = await fetch(`/api/robot/${encodeURIComponent(robotId)}/summary`);
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }

        const data = await res.json();
        updateCards(data);
      } catch (err) {
        document.getElementById('onlineStatus').textContent = 'OFFLINE';
        document.getElementById('onlineStatus').className = 'metric status-offline';
        document.getElementById('statusJson').textContent =
          JSON.stringify({ error: String(err) }, null, 2);
      }
    }

    function setGo2ButtonsDisabled(disabled) {
      const buttons = document.querySelectorAll("button[onclick*='sendGo2MotionCommand']");
      buttons.forEach((btn) => {
        const onclickText = btn.getAttribute("onclick") || "";
        const isEmergency = onclickText.includes("EMERGENCY_STOP");
        const isStop = onclickText.includes("STOP_MOVE");

        // 急停和停止永远不禁用
        if (!isEmergency && !isStop) {
          btn.disabled = disabled;
        }
      });
    }

    async function sendGo2MotionCommand(command, options = {}) {
      const commandCn = go2CommandNameMap[command] || command;
      const statusEl = document.getElementById("go2MotionStatus");
      const robotId = getRobotId();

      if (!robotId) {
        const msg = "Robot ID 为空，无法发送命令";
        statusEl.innerText = "运动控制状态：" + msg;
        log("发送失败：" + msg);
        return;
      }

      const nowMs = Date.now();
      const bypassCooldown = options && options.bypassCooldown === true;

      if (!bypassCooldown && command !== "EMERGENCY_STOP" && nowMs - go2LastCommandTimeMs < go2CommandCooldownMs) {
        const msg = "防连点生效，忽略过快命令：" + commandCn + " / " + command;
        statusEl.innerText = "运动控制状态：" + msg;
        log(msg);
        return;
      }

      if (go2DangerCommands.has(command)) {
        const ok = window.confirm(
          "确认执行危险姿态动作？\n\n" +
          "动作：" + commandCn + " / " + command + "\n\n" +
          "请确认 GO2 周围空旷、地面平整，并且手边保留遥控器/急停方式。"
        );

        if (!ok) {
          log("已取消危险命令：" + commandCn + " / " + command);
          return;
        }
      }

      go2LastCommandTimeMs = nowMs;
      statusEl.innerText = "运动控制状态：正在发送 " + commandCn + " / " + command + " ...";
      log("发送命令：" + commandCn + " / " + command + "，robot_id=" + robotId);

      if (command !== "EMERGENCY_STOP") {
        setGo2ButtonsDisabled(true);
      }

      try {
        const res = await fetch(
          `/api/robot/${encodeURIComponent(robotId)}/command/${encodeURIComponent(command)}`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({})
          }
        );

        const text = await res.text();
        let data = {};
        try {
          data = text ? JSON.parse(text) : {};
        } catch (e) {
          data = { raw: text };
        }

        if (!res.ok) {
          throw new Error(JSON.stringify(data));
        }

        const okMsg = "已发送：" + commandCn + " / " + command;
        statusEl.innerText = "运动控制状态：" + okMsg;
        log(`${okMsg}, command_id=${data.command_id || '-'}`);
        refreshStatus();
      } catch (err) {
        const msg = "发送失败：" + commandCn + " / " + command + "，" + String(err);
        statusEl.innerText = "运动控制状态：" + msg;
        log(msg);
      } finally {
        if (command !== "EMERGENCY_STOP") {
          setTimeout(() => {
            setGo2ButtonsDisabled(false);
          }, go2CommandCooldownMs);
        }
      }
    }

    refreshStatus();
    setInterval(refreshStatus, 1000);
    log("Dashboard 已加载：视频与常用控制按钮已合并到同一区域。");
  </script>
</body>
</html>
"""


@app.get('/dashboard', response_class=HTMLResponse)
async def dashboard():
    """
    Dashboard 页面。
    """
    return HTMLResponse(content=DASHBOARD_HTML)


# ============================================================
# 4. HTTP 接口：后台健康检查
# ============================================================

@app.get('/')
async def root():
    """
    后台健康检查接口。
    """
    return {
        'name': 'GO2 Backend Demo',
        'message': 'Backend is running',
        'dashboard': '/dashboard',
        'connected_robots': list(connected_robots.keys()),
    }


# ============================================================
# 5. WebSocket 接口：机器人连接入口
# ============================================================

@app.websocket('/ws/robot/{robot_id}')
async def robot_websocket(websocket: WebSocket, robot_id: str):
    """
    机器人 WebSocket 连接接口。
    """
    await websocket.accept()

    connected_robots[robot_id] = websocket
    last_seen_time[robot_id] = time.time()

    print('[WS] Robot connected: {}'.format(robot_id))

    try:
        while True:
            raw_msg = await websocket.receive_text()

            try:
                data = json.loads(raw_msg)
            except json.JSONDecodeError:
                print('[WS][{}] Non-JSON message: {}'.format(robot_id, raw_msg))
                continue

            msg_type = data.get('type')
            last_seen_time[robot_id] = time.time()

            if msg_type == 'register':
                print(
                    '[REGISTER][{}] {}'.format(
                        robot_id,
                        json.dumps(data, ensure_ascii=False)
                    )
                )

            elif msg_type == 'status':
                data['_server_received_at'] = now_ts()
                data['_server_received_time'] = time.time()
                last_status[robot_id] = data

                print(
                    '[STATUS][{}] {}'.format(
                        robot_id,
                        json.dumps(data, ensure_ascii=False)
                    )
                )

            elif msg_type == 'command_ack':
                data['_server_received_at'] = now_ts()
                data['_server_received_time'] = time.time()
                last_ack[robot_id] = data

                print(
                    '[ACK][{}] {}'.format(
                        robot_id,
                        json.dumps(data, ensure_ascii=False)
                    )
                )

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
        current_ws = connected_robots.get(robot_id)
        if current_ws is websocket:
            connected_robots.pop(robot_id, None)


# ============================================================
# 6. HTTP 接口：查看机器人状态
# ============================================================

@app.get('/api/robots')
async def list_robots():
    """
    查看机器人列表、最近状态、最近 ACK。
    """
    robot_ids = set()
    robot_ids.update(connected_robots.keys())
    robot_ids.update(last_status.keys())
    robot_ids.update(last_ack.keys())

    return {
        'connected_robots': list(connected_robots.keys()),
        'robots': {
            robot_id: make_robot_summary(robot_id)
            for robot_id in sorted(robot_ids)
        },
        'last_status': last_status,
        'last_ack': last_ack,
    }


@app.get('/api/robot/{robot_id}/summary')
async def get_robot_summary(robot_id: str):
    """
    查看某台机器人的摘要信息。
    Dashboard 使用这个接口。
    """
    return make_robot_summary(robot_id)


@app.get('/api/robot/{robot_id}/status')
async def get_robot_status(robot_id: str):
    """
    查看某台机器人最近一次 status。
    """
    if robot_id not in last_status:
        raise HTTPException(
            status_code=404,
            detail='No status received from robot {}'.format(robot_id)
        )

    return last_status[robot_id]


# ============================================================
# 7. HTTP 接口：向机器人发送命令
# ============================================================

@app.post('/api/robot/{robot_id}/command/{command}')
async def send_robot_command(
    robot_id: str,
    command: str,
    payload: Optional[Dict[str, Any]] = Body(default=None)
):
    """
    通过 HTTP 接口向机器人发送命令。

    示例：
        curl -X POST http://127.0.0.1:8000/api/robot/GO2_001/command/PAUSE_TASK
    """
    websocket = connected_robots.get(robot_id)

    if websocket is None:
        raise HTTPException(
            status_code=404,
            detail='Robot {} is not connected'.format(robot_id)
        )

    command_id = 'cmd-{}-{}'.format(
        int(time.time() * 1000),
        uuid.uuid4().hex[:8]
    )

    command_msg = {
        'type': 'command',
        'robot_id': robot_id,
        'timestamp': now_ts(),
        'command_id': command_id,
        'command': command,
        'payload': payload or {},
    }

    try:
        await websocket.send_text(json.dumps(command_msg, ensure_ascii=False))

    except Exception as exc:
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

    return {
        'sent': True,
        'robot_id': robot_id,
        'command': command,
        'command_id': command_id,
    }