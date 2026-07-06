# GO2 Dashboard 控制系统启动流程
ssh unitree@192.168.123.18
手机热点:
ssh unitree@192.168.7.149

一键打开
cd ~/GO2_Project/go2_bridge_ws
bash scripts/start_all_go2_system.sh

网址
http://127.0.0.1:8000/dashboard
http://192.168.123.18:8081/

一键停止
cd ~/GO2_Project/go2_bridge_ws
bash scripts/stop_all_go2_system.sh

rviz2启动
cd ~/GO2_Project/go2_bridge_ws
bash scripts/start_lidar_rviz_laptop.sh

## 0. 启动顺序

```text
1. 笔记本：启动 Dashboard 后台
2. Jetson：启动 bridge，连接笔记本后台
3. Jetson：启动运动/姿态控制节点
4. 浏览器：打开 Dashboard 页面测试按钮
```

---

## 1. 笔记本终端 1：启动 Dashboard 后台

在笔记本 Ubuntu 执行：

```bash
cd ~/GO2_Project/go2_bridge_ws
bash scripts/start_dashboard_backend.sh
```

如果没有这个脚本，用原始命令：

```bash
cd ~/GO2_Project/go2_bridge_ws
bash scripts/start_backend.sh
```

---

## 2. Jetson 终端 1：启动 bridge

先从笔记本 SSH 到 Jetson：

```bash
ssh unitree@192.168.123.18
```

密码：

```text
123
```

然后在 Jetson 执行：

```bash
cd /home/unitree/go2_bridge_ws
bash scripts/start_bridge_to_laptop.sh
```

如果没有这个脚本，用原始命令：

```bash
cd /home/unitree/go2_bridge_ws
bash scripts/start_bridge.sh 192.168.123.99
```

---

## 3. Jetson 终端 2：启动运动/姿态控制节点

重新打开一个终端，再 SSH 到 Jetson：

```bash
ssh unitree@192.168.123.18
```

然后执行：

```bash
cd /home/unitree/go2_bridge_ws
bash scripts/start_motion_control.sh
```

如果没有这个脚本，用原始命令：

```bash
cd /home/unitree/go2_bridge_ws

source /opt/ros/foxy/setup.bash
source /home/unitree/cyclonedds_ws/install/setup.bash
source install/setup.bash

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI='<CycloneDDS><Domain><General><Interfaces>
    <NetworkInterface name="eth0" priority="default" multicast="default" />
</Interfaces></General></Domain></CycloneDDS>'

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

启动雷达
ssh unitree@192.168.123.18 "bash /home/unitree/go2_bridge_ws/scripts/start_hesai_lidar.sh"

## 4. 浏览器：打开 Dashboard

在笔记本浏览器打开后台页面。

常见地址可能是：

```text
http://127.0.0.1:8000
```

或：

```text
http://192.168.123.99:8000
```

页面中的 Robot ID 使用：

```text
GO2_001
```

---

## 5. 测试顺序

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

---

## 6. 关闭顺序

```text
1. Dashboard 先点急停
2. 关闭 Jetson 运动/姿态控制节点：Ctrl + C
3. 关闭 Jetson bridge：Ctrl + C
4. 关闭笔记本 Dashboard 后台：Ctrl + C
```

