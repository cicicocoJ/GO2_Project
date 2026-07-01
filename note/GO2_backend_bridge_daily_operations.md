# GO2 Backend Bridge 日常操作手册

本文档用于以后快速运行 GO2 EDU 巡检机器人端中转站 Demo。

当前推荐架构：

```text
Jetson ROS2 Foxy backend_client_node
    ↓ WebSocket
笔记本 Ubuntu 22.04 FastAPI server.py
```

笔记本后台 IP：

```text
192.168.123.99
```

Jetson IP：

```text
192.168.123.18
```

---

## 1. 本地代码目录

笔记本本地项目目录：

```bash
~/GO2_Project/go2_bridge_ws
```

用 VS Code 打开：

```bash
code ~/GO2_Project/go2_bridge_ws
```

主要文件：

```text
server.py
src/go2_backend_bridge/go2_backend_bridge/backend_client_node.py
src/go2_backend_bridge/setup.py
src/go2_backend_bridge/setup.cfg
src/go2_backend_bridge/package.xml
```

---

## 2. 每次修改代码后的同步命令

以下命令在**笔记本**执行。

### 2.1 同步 ROS2 包

```bash
rsync -avz --delete \
  --exclude build \
  --exclude install \
  --exclude log \
  ~/GO2_Project/go2_bridge_ws/src/go2_backend_bridge \
  unitree@192.168.123.18:/home/unitree/go2_bridge_ws/src/
```

### 2.2 同步 FastAPI 后台

```bash
rsync -avz \
  ~/GO2_Project/go2_bridge_ws/server.py \
  unitree@192.168.123.18:/home/unitree/go2_bridge_ws/
```

如果只在笔记本运行后台，则 `server.py` 不一定需要同步到 Jetson。

---

## 3. Jetson 编译命令

SSH 登录 Jetson：

```bash
ssh unitree@192.168.123.18
```

出现：

```text
ros:foxy(1) noetic(2) ?
```

输入：

```text
1
```

进入工作空间：

```bash
cd ~/go2_bridge_ws
```

设置 ROS2 Foxy + CycloneDDS 环境：

```bash
source /opt/ros/foxy/setup.bash
source ~/cyclonedds_ws/install/setup.bash

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI='<CycloneDDS><Domain><General><Interfaces>
    <NetworkInterface name="eth0" priority="default" multicast="default" />
</Interfaces></General></Domain></CycloneDDS>'
```

如果需要干净重新编译：

```bash
rm -rf build install log
```

编译：

```bash
colcon build --packages-select go2_backend_bridge --symlink-install
source install/setup.bash
```

检查节点是否存在：

```bash
ros2 pkg list | grep go2_backend_bridge
find install -name backend_client_node -type f -o -type l
```

正常应能看到：

```text
install/go2_backend_bridge/lib/go2_backend_bridge/backend_client_node
```

---

## 4. 启动后台

后台推荐先跑在笔记本上。

在**笔记本**执行：

```bash
cd ~/GO2_Project/go2_bridge_ws
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

正常输出：

```text
Uvicorn running on http://0.0.0.0:8000
```

如果缺依赖：

```bash
python3 -m pip install fastapi==0.95.2 "uvicorn[standard]==0.22.0" websockets==10.4
```

测试后台是否运行：

```bash
curl http://127.0.0.1:8000/
```

正常返回类似：

```json
{
  "name": "GO2 Backend Demo",
  "message": "Backend is running",
  "connected_robots": []
}
```

---

## 5. Jetson 启动 bridge 节点

在 **Jetson** 上执行：

```bash
cd ~/go2_bridge_ws

source /opt/ros/foxy/setup.bash
source ~/cyclonedds_ws/install/setup.bash
source install/setup.bash

ros2 run go2_backend_bridge backend_client_node \
  --ros-args \
  -p robot_id:=GO2_001 \
  -p server_url:=ws://192.168.123.99:8000/ws/robot/GO2_001
```

如果连接成功，Jetson 终端会看到：

```text
WebSocket connected
Register message sent
```

笔记本后台终端会看到：

```text
[WS] Robot connected: GO2_001
[REGISTER][GO2_001] ...
[STATUS][GO2_001] ...
```

---

## 6. 模拟机器人状态

新开一个 Jetson SSH 终端：

```bash
ssh unitree@192.168.123.18
```

选择 Foxy 后执行：

```bash
cd ~/go2_bridge_ws

source /opt/ros/foxy/setup.bash
source ~/cyclonedds_ws/install/setup.bash
source install/setup.bash

ros2 topic pub /inspection_state std_msgs/String "{data: 'PATROLLING'}" -r 1
```

后台应该持续看到：

```text
"state": "PATROLLING"
```

可测试其他状态：

```bash
ros2 topic pub /inspection_state std_msgs/String "{data: 'IDLE'}" -1
ros2 topic pub /inspection_state std_msgs/String "{data: 'PAUSED'}" -1
ros2 topic pub /inspection_state std_msgs/String "{data: 'EMERGENCY_STOP'}" -1
```

---

## 7. 监听后台命令

新开一个 Jetson SSH 终端：

```bash
ssh unitree@192.168.123.18
```

选择 Foxy 后执行：

```bash
cd ~/go2_bridge_ws

source /opt/ros/foxy/setup.bash
source ~/cyclonedds_ws/install/setup.bash
source install/setup.bash

ros2 topic echo /backend_command
```

---

## 8. 从后台发送命令

在**笔记本**执行：

```bash
curl -X POST http://127.0.0.1:8000/api/robot/GO2_001/command/PAUSE_TASK
```

正常返回：

```json
{
  "sent": true,
  "robot_id": "GO2_001",
  "command": "PAUSE_TASK",
  "command_id": "cmd-..."
}
```

Jetson 的 `/backend_command` 终端应收到：

```yaml
data: '{"type": "command", "robot_id": "GO2_001", "timestamp": "...", "command_id": "cmd-...", "command": "PAUSE_TASK", "payload": {}}'
```

后台终端应看到：

```text
[COMMAND][GO2_001] ...
[ACK][GO2_001] ...
```

---

## 9. 常用测试命令

### 9.1 查看所有 ROS2 topic

```bash
ros2 topic list
```

### 9.2 查看状态 topic

```bash
ros2 topic echo /inspection_state
```

### 9.3 查看后台命令 topic

```bash
ros2 topic echo /backend_command
```

### 9.4 手动发布状态

```bash
ros2 topic pub /inspection_state std_msgs/String "{data: 'PATROLLING'}" -r 1
```

### 9.5 查看后台已连接机器人

在笔记本执行：

```bash
curl http://127.0.0.1:8000/api/robots
```

### 9.6 查看某台机器人最近状态

```bash
curl http://127.0.0.1:8000/api/robot/GO2_001/status
```

### 9.7 下发暂停命令

```bash
curl -X POST http://127.0.0.1:8000/api/robot/GO2_001/command/PAUSE_TASK
```

### 9.8 下发带 payload 的任务命令

```bash
curl -X POST http://127.0.0.1:8000/api/robot/GO2_001/command/START_TASK \
  -H "Content-Type: application/json" \
  -d '{"route_id": "factory_route_001", "task_id": "task_demo_001"}'
```

---

## 10. 常见问题排查

### 10.1 bridge 节点连接不上后台

Jetson 终端出现：

```text
Connect call failed
```

检查笔记本后台是否启动：

```bash
curl http://127.0.0.1:8000/
```

检查 Jetson 是否能 ping 通笔记本：

```bash
ping -c 3 192.168.123.99
```

检查 Jetson 是否能访问后台端口：

```bash
curl http://192.168.123.99:8000/
```

如果不通，检查笔记本防火墙：

```bash
sudo ufw status
```

允许 8000 端口：

```bash
sudo ufw allow 8000/tcp
```

---

### 10.2 `ros2 run` 提示 No executable found

检查 `setup.cfg`：

```bash
cat ~/go2_bridge_ws/src/go2_backend_bridge/setup.cfg
```

必须是：

```ini
[develop]
script_dir=$base/lib/go2_backend_bridge

[install]
install_scripts=$base/lib/go2_backend_bridge
```

检查 `setup.py`：

```bash
grep -n "console_scripts" -A 5 ~/go2_bridge_ws/src/go2_backend_bridge/setup.py
```

必须包含：

```python
'backend_client_node = go2_backend_bridge.backend_client_node:main'
```

检查 `main()`：

```bash
grep -n "def main" ~/go2_bridge_ws/src/go2_backend_bridge/go2_backend_bridge/backend_client_node.py
```

然后重新编译：

```bash
cd ~/go2_bridge_ws
rm -rf build install log
colcon build --packages-select go2_backend_bridge --symlink-install
source install/setup.bash
```

---

### 10.3 Jetson 缺少 websockets

报错：

```text
DistributionNotFound: The 'websockets' distribution was not found
```

检查：

```bash
python3 -c "import websockets; print(websockets.__version__)"
```

如果没有安装，需安装 Jetson 可用的 aarch64 + Python3.8 wheel。

正确文件名类似：

```text
websockets-10.4-cp38-cp38-manylinux_2_17_aarch64.manylinux2014_aarch64.whl
```

安装：

```bash
python3 -m pip install --user /home/unitree/websockets-10.4-cp38-cp38-manylinux_2_17_aarch64.manylinux2014_aarch64.whl
```

---

## 11. 一键式日常运行顺序

### 笔记本终端 1：启动后台

```bash
cd ~/GO2_Project/go2_bridge_ws
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

### Jetson 终端 1：启动 bridge

```bash
cd ~/go2_bridge_ws
source /opt/ros/foxy/setup.bash
source ~/cyclonedds_ws/install/setup.bash
source install/setup.bash

ros2 run go2_backend_bridge backend_client_node \
  --ros-args \
  -p robot_id:=GO2_001 \
  -p server_url:=ws://192.168.123.99:8000/ws/robot/GO2_001
```

### Jetson 终端 2：模拟状态

```bash
cd ~/go2_bridge_ws
source /opt/ros/foxy/setup.bash
source ~/cyclonedds_ws/install/setup.bash
source install/setup.bash

ros2 topic pub /inspection_state std_msgs/String "{data: 'PATROLLING'}" -r 1
```

### Jetson 终端 3：监听命令

```bash
cd ~/go2_bridge_ws
source /opt/ros/foxy/setup.bash
source ~/cyclonedds_ws/install/setup.bash
source install/setup.bash

ros2 topic echo /backend_command
```

### 笔记本终端 2：发送命令

```bash
curl -X POST http://127.0.0.1:8000/api/robot/GO2_001/command/PAUSE_TASK
```

如果以上全部正常，说明最小闭环运行成功。
