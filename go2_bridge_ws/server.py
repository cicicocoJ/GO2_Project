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
    body {
      margin: 0;
      font-family: Arial, "Microsoft YaHei", sans-serif;
      background: #f4f6f8;
      color: #1f2937;
    }

    header {
      background: #111827;
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
      padding: 24px;
      max-width: 1200px;
      margin: 0 auto;
    }

    .row {
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      margin-bottom: 16px;
    }

    .card {
      background: white;
      border-radius: 12px;
      padding: 18px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
      flex: 1;
      min-width: 220px;
    }

    .card h2 {
      margin: 0 0 12px;
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
      color: #6b7280;
    }

    .status-online {
      color: #16a34a;
    }

    .status-offline {
      color: #dc2626;
    }

    .button-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }

    button {
      border: none;
      border-radius: 8px;
      padding: 10px 14px;
      cursor: pointer;
      font-size: 14px;
      background: #2563eb;
      color: white;
    }

    button:hover {
      background: #1d4ed8;
    }

    button.secondary {
      background: #4b5563;
    }

    button.secondary:hover {
      background: #374151;
    }

    button.warning {
      background: #f59e0b;
    }

    button.warning:hover {
      background: #d97706;
    }

    button.danger {
      background: #dc2626;
    }

    button.danger:hover {
      background: #b91c1c;
    }

    input {
      border: 1px solid #d1d5db;
      border-radius: 8px;
      padding: 10px 12px;
      font-size: 14px;
      min-width: 180px;
    }

    pre {
      background: #0f172a;
      color: #e5e7eb;
      border-radius: 12px;
      padding: 16px;
      overflow-x: auto;
      max-height: 460px;
      font-size: 13px;
      line-height: 1.5;
    }

    .log {
      background: #111827;
      color: #e5e7eb;
      border-radius: 12px;
      padding: 12px;
      height: 150px;
      overflow-y: auto;
      font-size: 13px;
    }

    .small {
      font-size: 13px;
      color: #6b7280;
    }

    .grid-two {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }

    @media (max-width: 800px) {
      .grid-two {
        grid-template-columns: 1fr;
      }
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

    <div class="card">
      <h2>命令控制</h2>
      <div class="button-row">
        <button class="secondary" onclick="sendCommand('PING')">PING</button>
        <button onclick="sendCommand('START_TASK')">START_TASK</button>
        <button class="warning" onclick="sendCommand('PAUSE_TASK')">PAUSE_TASK</button>
        <button onclick="sendCommand('RESUME_TASK')">RESUME_TASK</button>
        <button class="warning" onclick="sendCommand('STOP_TASK')">STOP_TASK</button>
        <button class="danger" onclick="sendCommand('EMERGENCY_STOP')">EMERGENCY_STOP</button>
      </div>
      <p class="small">
        当前按钮只调用后台 command 接口。真正运动控制由 Jetson 后续的 command handler 节点决定。
      </p>
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
    function getRobotId() {
      return document.getElementById('robotIdInput').value.trim() || 'GO2_001';
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

    async function sendCommand(command) {
      const robotId = getRobotId();

      if (command === 'EMERGENCY_STOP') {
        const ok = confirm('确认发送 EMERGENCY_STOP？');
        if (!ok) return;
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

        const data = await res.json();

        if (!res.ok) {
          throw new Error(JSON.stringify(data));
        }

        log(`命令已发送：${command}, command_id=${data.command_id}`);
        refreshStatus();
      } catch (err) {
        log(`命令发送失败：${command}, error=${String(err)}`);
      }
    }

    refreshStatus();
    setInterval(refreshStatus, 1000);
  </script>

<!-- GO2_MOTION_CONTROL_PANEL_V1 -->
<style>
  .go2-motion-panel {
    margin: 20px 0;
    padding: 16px;
    border: 1px solid #d0d7de;
    border-radius: 12px;
    background: #f6f8fa;
  }

  .go2-motion-panel h2 {
    margin: 0 0 12px 0;
    font-size: 20px;
  }

  .go2-motion-hint {
    margin: 8px 0 14px 0;
    color: #57606a;
    font-size: 14px;
    line-height: 1.5;
  }

  .go2-motion-grid {
    display: grid;
    grid-template-columns: repeat(3, 110px);
    grid-template-rows: repeat(4, 52px);
    gap: 10px;
    align-items: center;
  }

  .go2-motion-btn {
    height: 48px;
    border: none;
    border-radius: 10px;
    background: #0969da;
    color: white;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
  }

  .go2-motion-btn:hover {
    background: #0550ae;
  }

  .go2-motion-btn.stop {
    background: #6e7781;
  }

  .go2-motion-btn.stop:hover {
    background: #57606a;
  }

  .go2-motion-btn.estop {
    background: #cf222e;
  }

  .go2-motion-btn.estop:hover {
    background: #a40e26;
  }

  .go2-motion-status {
    margin-top: 12px;
    font-size: 14px;
    color: #24292f;
  }
</style>

<div class="go2-motion-panel">
  <h2>GO2 安全运动控制</h2>
  <div class="go2-motion-hint">
    当前模式：点击一次按钮，执行一小段动作，然后自动停止。测试前请保证 GO2 周围空旷，手边保留遥控器/急停方式。
  </div>

  <div style="margin-bottom: 12px;">
    <label for="go2RobotIdInput">Robot ID：</label>
    <input id="go2RobotIdInput" value="GO2_001" style="height: 30px; padding: 4px 8px; border-radius: 6px; border: 1px solid #d0d7de;">
    <span style="font-size: 13px; color: #57606a;">如果按钮无效，把这里改成你后台实际的 robot_id。</span>
  </div>

  <div class="go2-motion-grid">
    <div></div>
    <button class="go2-motion-btn" onclick="sendGo2MotionCommand('MOVE_FORWARD')">前进</button>
    <div></div>

    <button class="go2-motion-btn" onclick="sendGo2MotionCommand('MOVE_LEFT')">左移</button>
    <button class="go2-motion-btn stop" onclick="sendGo2MotionCommand('STOP_MOVE')">停止</button>
    <button class="go2-motion-btn" onclick="sendGo2MotionCommand('MOVE_RIGHT')">右移</button>

    <div></div>
    <button class="go2-motion-btn" onclick="sendGo2MotionCommand('MOVE_BACKWARD')">后退</button>
    <div></div>

    <button class="go2-motion-btn" onclick="sendGo2MotionCommand('TURN_LEFT')">左转</button>
    <button class="go2-motion-btn estop" onclick="sendGo2MotionCommand('EMERGENCY_STOP')">急停</button>
    <button class="go2-motion-btn" onclick="sendGo2MotionCommand('TURN_RIGHT')">右转</button>
  </div>

  <div id="go2MotionStatus" class="go2-motion-status">运动控制状态：等待操作</div>
</div>

<script>
  async function sendGo2MotionCommand(command) {
    const statusEl = document.getElementById("go2MotionStatus");
    const robotIdInput = document.getElementById("go2RobotIdInput");

    const robotId = robotIdInput && robotIdInput.value
      ? robotIdInput.value.trim()
      : "GO2_001";

    if (!robotId) {
      statusEl.innerText = "运动控制状态：Robot ID 为空，无法发送命令";
      return;
    }

    statusEl.innerText = "运动控制状态：正在发送 " + command + " ...";

    try {
      const response = await fetch("/api/robot/" + encodeURIComponent(robotId) + "/command/" + encodeURIComponent(command), {
        method: "POST"
      });

      let responseText = "";
      try {
        responseText = await response.text();
      } catch (e) {
        responseText = "";
      }

      if (!response.ok) {
        statusEl.innerText = "运动控制状态：发送失败 " + command + "，HTTP " + response.status + "，" + responseText;
        console.error("GO2 command failed:", command, response.status, responseText);
        return;
      }

      statusEl.innerText = "运动控制状态：已发送 " + command;
      console.log("GO2 command sent:", command, responseText);
    } catch (error) {
      statusEl.innerText = "运动控制状态：发送异常 " + command + "，" + error;
      console.error("GO2 command error:", command, error);
    }
  }
</script>


<!-- GO2_POSTURE_CONTROL_PANEL_V1 -->
<style>
  .go2-posture-panel {
    margin: 20px 0;
    padding: 16px;
    border: 1px solid #d0d7de;
    border-radius: 12px;
    background: #fff8c5;
  }

  .go2-posture-panel h2 {
    margin: 0 0 12px 0;
    font-size: 20px;
  }

  .go2-posture-hint {
    margin: 8px 0 14px 0;
    color: #57606a;
    font-size: 14px;
    line-height: 1.5;
  }

  .go2-posture-grid {
    display: grid;
    grid-template-columns: repeat(4, 120px);
    gap: 10px;
    align-items: center;
  }

  .go2-posture-btn {
    height: 48px;
    border: none;
    border-radius: 10px;
    background: #8250df;
    color: white;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
  }

  .go2-posture-btn:hover {
    background: #6639ba;
  }

  .go2-posture-btn.safe {
    background: #1a7f37;
  }

  .go2-posture-btn.safe:hover {
    background: #116329;
  }

  .go2-posture-btn.warn {
    background: #bf8700;
  }

  .go2-posture-btn.warn:hover {
    background: #9a6700;
  }

  .go2-posture-btn.danger {
    background: #cf222e;
  }

  .go2-posture-btn.danger:hover {
    background: #a40e26;
  }
</style>

<div class="go2-posture-panel">
  <h2>GO2 姿态控制</h2>

  <div class="go2-posture-hint">
    当前区域用于第二批高层姿态动作。测试前请保证 GO2 周围空旷、地面平整，手边保留遥控器/急停方式。
    建议顺序：站立 → 平衡站立 → 恢复站立 → 卧倒 → 站立 → 坐下 → 起坐。
    阻尼保护 DAMP 请谨慎使用。
  </div>

  <div class="go2-posture-grid">
    <button class="go2-posture-btn safe" onclick="sendGo2MotionCommand('STAND_UP')">站立</button>
    <button class="go2-posture-btn safe" onclick="sendGo2MotionCommand('BALANCE_STAND')">平衡站立</button>
    <button class="go2-posture-btn safe" onclick="sendGo2MotionCommand('RECOVERY_STAND')">恢复站立</button>
    <button class="go2-posture-btn warn" onclick="sendGo2MotionCommand('STAND_DOWN')">卧倒</button>

    <button class="go2-posture-btn" onclick="sendGo2MotionCommand('SIT')">坐下</button>
    <button class="go2-posture-btn" onclick="sendGo2MotionCommand('RISE_SIT')">起坐</button>
    <button class="go2-posture-btn danger" onclick="sendGo2MotionCommand('DAMP')">阻尼保护</button>
    <button class="go2-posture-btn danger" onclick="sendGo2MotionCommand('EMERGENCY_STOP')">急停</button>
  </div>
</div>


<!-- GO2_DASHBOARD_SAFETY_V1 -->
<style>
  .go2-command-log-panel {
    margin: 20px 0;
    padding: 16px;
    border: 1px solid #d0d7de;
    border-radius: 12px;
    background: #ffffff;
  }

  .go2-command-log-panel h2 {
    margin: 0 0 12px 0;
    font-size: 20px;
  }

  .go2-command-log {
    height: 180px;
    overflow-y: auto;
    padding: 10px;
    border: 1px solid #d0d7de;
    border-radius: 8px;
    background: #f6f8fa;
    font-family: monospace;
    font-size: 13px;
    line-height: 1.5;
    white-space: pre-wrap;
  }

  .go2-command-log-tip {
    color: #57606a;
    font-size: 14px;
    margin-bottom: 10px;
  }
</style>

<div class="go2-command-log-panel">
  <h2>GO2 命令日志</h2>
  <div class="go2-command-log-tip">
    这里记录 Dashboard 发出的运动/姿态命令。急停不受防连点限制；危险姿态动作会二次确认。
  </div>
  <div id="go2CommandLog" class="go2-command-log">等待命令...</div>
</div>

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
    "DAMP": "阻尼保护"
  };

  function go2NowText() {
    const d = new Date();
    return d.toLocaleTimeString();
  }

  function appendGo2CommandLog(text) {
    const logEl = document.getElementById("go2CommandLog");
    if (!logEl) {
      return;
    }

    if (logEl.innerText === "等待命令...") {
      logEl.innerText = "";
    }

    logEl.innerText += "[" + go2NowText() + "] " + text + "\n";
    logEl.scrollTop = logEl.scrollHeight;
  }

  function setGo2ButtonsDisabled(disabled) {
    const buttons = document.querySelectorAll("button[onclick*='sendGo2MotionCommand']");
    buttons.forEach((btn) => {
      const onclickText = btn.getAttribute("onclick") || "";
      const isEmergency = onclickText.includes("EMERGENCY_STOP");

      // 急停按钮永远不禁用
      if (!isEmergency) {
        btn.disabled = disabled;
        btn.style.opacity = disabled ? "0.65" : "1.0";
        btn.style.cursor = disabled ? "not-allowed" : "pointer";
      }
    });
  }

  async function sendGo2MotionCommand(command) {
    const commandCn = go2CommandNameMap[command] || command;
    const statusEl = document.getElementById("go2MotionStatus");
    const robotIdInput = document.getElementById("go2RobotIdInput");

    const robotId = robotIdInput && robotIdInput.value
      ? robotIdInput.value.trim()
      : "GO2_001";

    if (!robotId) {
      const msg = "Robot ID 为空，无法发送命令";
      if (statusEl) {
        statusEl.innerText = "运动控制状态：" + msg;
      }
      appendGo2CommandLog("发送失败：" + msg);
      return;
    }

    // 急停不受防连点限制，其他命令限制连续点击
    const nowMs = Date.now();
    if (command !== "EMERGENCY_STOP" && nowMs - go2LastCommandTimeMs < go2CommandCooldownMs) {
      const msg = "防连点生效，忽略过快命令：" + commandCn + " / " + command;
      if (statusEl) {
        statusEl.innerText = "运动控制状态：" + msg;
      }
      appendGo2CommandLog(msg);
      return;
    }

    if (go2DangerCommands.has(command)) {
      const ok = window.confirm(
        "确认执行危险姿态动作？\n\n" +
        "动作：" + commandCn + " / " + command + "\n\n" +
        "请确认 GO2 周围空旷、地面平整，并且手边保留遥控器/急停方式。"
      );

      if (!ok) {
        appendGo2CommandLog("已取消危险命令：" + commandCn + " / " + command);
        return;
      }
    }

    go2LastCommandTimeMs = nowMs;

    if (statusEl) {
      statusEl.innerText = "运动控制状态：正在发送 " + commandCn + " / " + command + " ...";
    }
    appendGo2CommandLog("发送命令：" + commandCn + " / " + command + "，robot_id=" + robotId);

    if (command !== "EMERGENCY_STOP") {
      setGo2ButtonsDisabled(true);
    }

    try {
      const response = await fetch(
        "/api/robot/" + encodeURIComponent(robotId) + "/command/" + encodeURIComponent(command),
        { method: "POST" }
      );

      let responseText = "";
      try {
        responseText = await response.text();
      } catch (e) {
        responseText = "";
      }

      if (!response.ok) {
        const msg = "发送失败：" + commandCn + " / " + command + "，HTTP " + response.status + "，" + responseText;
        if (statusEl) {
          statusEl.innerText = "运动控制状态：" + msg;
        }
        appendGo2CommandLog(msg);
        console.error("GO2 command failed:", command, response.status, responseText);
        return;
      }

      const okMsg = "已发送：" + commandCn + " / " + command;
      if (statusEl) {
        statusEl.innerText = "运动控制状态：" + okMsg;
      }
      appendGo2CommandLog(okMsg);
      console.log("GO2 command sent:", command, responseText);
    } catch (error) {
      const msg = "发送异常：" + commandCn + " / " + command + "，" + error;
      if (statusEl) {
        statusEl.innerText = "运动控制状态：" + msg;
      }
      appendGo2CommandLog(msg);
      console.error("GO2 command error:", command, error);
    } finally {
      if (command !== "EMERGENCY_STOP") {
        setTimeout(() => {
          setGo2ButtonsDisabled(false);
        }, go2CommandCooldownMs);
      }
    }
  }

  appendGo2CommandLog("Dashboard 安全增强已启用：防连点、命令日志、危险动作确认。");
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
