# GO2 Dashboard 控制系统启动流程

## 最常用命令

### 1. 一键启动完整系统

在笔记本 Ubuntu 执行：

```bash
cd ~/GO2_Project/go2_bridge_ws
bash scripts/start_all_go2_system.sh
```

启动内容包括：

```text
笔记本 FastAPI Dashboard 后台
Jetson backend_client
Jetson 状态读取节点 go2_state_reader
Jetson 运动/姿态控制节点 command_handler
Jetson D435i 拍照节点 camera_capture
Jetson D435i 视频流 camera_stream
Jetson XT-16 Hesai 雷达节点
```

---

### 2. 打开网页

Dashboard：

```text
http://127.0.0.1:8000/dashboard
http://192.168.7.124:8000/dashboard
```

D435i 视频流：

```text
http://192.168.7.149:8081/
http://192.168.7.149:8081/video_feed
```

注意：

```text
192.168.7.149 是 Jetson 的 WiFi / 手机热点 IP，用于浏览器访问视频流和 SSH。
192.168.123.18 是 Jetson 的 GO2 有线口 IP，主要用于 Jetson 和 GO2 本体通信，不要用它在笔记本浏览器打开视频流。
```

---

### 3. 一键停止完整系统

在笔记本 Ubuntu 执行：

```bash
cd ~/GO2_Project/go2_bridge_ws
bash scripts/stop_all_go2_system.sh
```

---

### 4. 启动 RViz2 / 雷达显示

在笔记本 Ubuntu 执行：

```bash
cd ~/GO2_Project/go2_bridge_ws
bash scripts/start_lidar_rviz_laptop.sh
```

---

### 5. SSH 到 Jetson

手机热点 / WiFi 模式：

```bash
ssh unitree@192.168.7.149
```

密码：

```text
123
```

GO2 有线网段模式：

```bash
ssh unitree@192.168.123.18
```

---

### 6. 检查 Jetson ROS2 节点

在笔记本执行：

```bash
ssh unitree@192.168.7.149 '
source ~/go2_test_env.sh
source /home/unitree/go2_bridge_ws/install/setup.bash
ros2 daemon stop || true
ros2 daemon start
sleep 2
ros2 node list
'
```

正常应看到：

```text
/backend_client_node
/backend_command_handler_node
/camera_capture_node
/go2_state_reader_node
/hesai_ros_driver/hesai_ros_driver_node
```

每个节点应该只出现一次。如果同名节点重复，先执行“一键停止”，再重新启动。

---

### 7. 检查 Dashboard 和视频流

在笔记本执行：

```bash
curl -s -o /dev/null -w "dashboard http_code=%{http_code}\n" http://127.0.0.1:8000/dashboard
curl -s http://127.0.0.1:8000/dashboard | grep -o "http://[^\"']*8081[^\"']*"
curl -s --max-time 3 http://192.168.7.149:8081/ | head -n 5
```

Dashboard 中的视频地址应为：

```text
http://192.168.7.149:8081/video_feed
```

不要用 `curl -I` 测试这些接口，因为当前 Dashboard 和视频流服务不支持 HEAD 请求，可能返回 `405` 或 `501`，这不代表服务没有启动。

---

## 当前网络配置说明

当前推荐网络结构：

```text
笔记本 WiFi / 手机热点 IP：192.168.7.124
Jetson WiFi / 手机热点 IP：192.168.7.149
Jetson eth0 / GO2 有线网段 IP：192.168.123.18
GO2 本体 IP：192.168.123.161
```

配置文件：

```bash
cd ~/GO2_Project/go2_bridge_ws
cat scripts/go2_network.env
```

关键配置应类似：

```bash
BACKEND_IP=192.168.7.124
BACKEND_PORT=8000
JETSON_USER=unitree
JETSON_IP=192.168.7.149
JETSON_VIDEO_PORT=8081
ROBOT_ID=GO2_001
GO2_DDS_IFACE=eth0
LAPTOP_DDS_IFACE=wlp2s0
```

以后更换热点或 WiFi 后，优先修改：

```text
BACKEND_IP：笔记本 IP
JETSON_IP：Jetson WiFi IP
```

---

## 推荐启动顺序

```text
1. 打开 GO2 电源，确认 Jetson 已启动。
2. 确认笔记本和 Jetson 连接同一个手机热点 / WiFi。
3. 确认 Jetson 的 eth0 仍连接 GO2 本体有线网段。
4. 在笔记本执行 bash scripts/start_all_go2_system.sh。
5. 浏览器打开 http://127.0.0.1:8000/dashboard。
6. 先看状态、电量、视频流是否正常。
7. 再测试急停、站立、平衡站立、移动等按钮。
```

---

## 推荐关闭顺序

```text
1. Dashboard 先点击“停止”或“急停”。
2. 在笔记本执行 bash scripts/stop_all_go2_system.sh。
3. 确认 Jetson 节点不再重复残留。
4. 再关闭浏览器或终端。
```

---

## 如果出现同名节点重复

现象：

```text
/backend_client_node 出现多个
/backend_command_handler_node 出现多个
/camera_capture_node 出现多个
```

处理方法：

```bash
cd ~/GO2_Project/go2_bridge_ws
bash scripts/stop_all_go2_system.sh
```

如果仍有残留，在笔记本执行：

```bash
ssh unitree@192.168.7.149 '
pkill -f "go2_state_reader_node" || true
pkill -f "backend_client_node" || true
pkill -f "backend_command_handler_node" || true
pkill -f "camera_capture_node" || true
pkill -f "go2_camera_stream_server.py" || true
pkill -f "hesai_ros_driver" || true
fuser -k 8081/tcp 2>/dev/null || true
rm -f /home/unitree/go2_bridge_ws/logs/pids/*.pid
'
```

然后重新启动：

```bash
cd ~/GO2_Project/go2_bridge_ws
bash scripts/start_all_go2_system.sh
```

---

## 如果 Dashboard 没有视频画面

先确认视频流服务是否打开：

```bash
curl -s --max-time 3 http://192.168.7.149:8081/ | head -n 5
```

再确认 Dashboard 实际嵌入的视频地址：

```bash
curl -s http://127.0.0.1:8000/dashboard | grep -o "http://[^\"']*8081[^\"']*"
```

正确结果应为：

```text
http://192.168.7.149:8081/video_feed
```

如果输出仍是 `192.168.123.18`，说明后台没有读取新配置，需要重启：

```bash
cd ~/GO2_Project/go2_bridge_ws
bash scripts/stop_all_go2_system.sh
bash scripts/start_all_go2_system.sh
```

---

## 关于视频卡顿

当前 Dashboard 视频使用 Jetson 侧 MJPEG 流，画面卡顿通常与以下因素有关：

```text
1. D435i 图像编码占用 Jetson CPU。
2. Dashboard 通过 WiFi / 手机热点访问 Jetson，网络带宽和延迟不稳定。
3. camera_capture_node 和 camera_stream 同时使用摄像头时，可能导致读取压力增大。
4. 当前图像参数为 640x480、JPEG 质量 90，画质较高但负载也更大。
```

临时使用时，只要画面能显示、状态和控制正常，可以先接受轻微卡顿。后续可以通过降低分辨率、降低 JPEG 质量、限制帧率或合并拍照/视频服务来优化。

---

## 备用：只启动 Dashboard 后台

如果只想打开网页，不启动 Jetson 机器人侧节点：

```bash
cd ~/GO2_Project/go2_bridge_ws
bash scripts/start_backend.sh
```

打开：

```text
http://127.0.0.1:8000/dashboard
```

注意：只启动 Dashboard 后台不会自动启动 Jetson 视频流、状态节点、运动控制节点和雷达节点。

---

## 备用：只启动 Jetson 雷达

```bash
ssh unitree@192.168.7.149 "bash /home/unitree/go2_bridge_ws/scripts/start_hesai_lidar.sh"
```

停止雷达：

```bash
ssh unitree@192.168.7.149 "bash /home/unitree/go2_bridge_ws/scripts/stop_hesai_lidar.sh"
```

---

## 备用：手动启动 Jetson 运动控制节点

一般不需要手动执行，优先使用一键启动脚本。只有调试时才使用：

```bash
ssh unitree@192.168.7.149
cd /home/unitree/go2_bridge_ws

source ~/go2_test_env.sh
source /home/unitree/go2_bridge_ws/install/setup.bash

ros2 run go2_command_control backend_command_handler_node \
  --ros-args \
  -p linear_speed_x:=0.30 \
  -p linear_speed_y:=0.25 \
  -p yaw_speed:=0.70 \
  -p move_duration_sec:=1.5 \
  -p control_period_sec:=0.1 \
  -p stop_before_posture:=true
```

---

## Dashboard 测试顺序

```text
1. 急停
2. 站立
3. 平衡站立
4. 前进
5. 停止
6. 后退
7. 左移
8. 右移
9. 左转
10. 右转
11. 卧倒
12. 站立
13. 坐下
14. 起坐
15. 阻尼保护 DAMP
16. 恢复站立
```

