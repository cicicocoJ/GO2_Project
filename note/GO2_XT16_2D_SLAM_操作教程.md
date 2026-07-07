# GO2 + XT-16 2D SLAM 操作教程

> 适用场景：Unitree GO2 EDU + Jetson + Hesai XT-16 外接激光雷达，在笔记本侧完成 2D 建图、保存地图、重新加载地图测试。本文重点记录命令顺序，方便后续更换地图后完整复测。

---

## 1. 当前网络与数据链路

### 1.1 网络分工

```text
Wi-Fi 网络 192.168.7.x：
  - 笔记本 FastAPI 后台
  - Dashboard
  - WebSocket 控制
  - D435i 视频流
  - 普通机器人状态上传 / 运动控制

有线雷达网络 192.168.123.x：
  - Jetson 有线口：192.168.123.18
  - XT-16 雷达：192.168.123.20
  - Hesai UDP 点云
  - /lidar_points
  - 2D SLAM 调试链路
```

### 1.2 SLAM 数据流

```text
XT-16 雷达
  ↓
/lidar_points
  ↓ pointcloud_to_laserscan
/scan
  ↓ scan_stamp_relay.py，修正时间戳并降频
/scan_slam
  ↓ slam_toolbox
/map
  ↓ map_saver_cli
.yaml + .pgm 地图文件
```

### 1.3 TF 链路

```text
/utlidar/robot_odom
  ↓ odom_to_tf_bridge_now.py
odom -> base_link
  ↓ static_transform_publisher
base_link -> hesai_lidar
  ↓ slam_toolbox
map -> odom
```

最终 TF：

```text
map -> odom -> base_link -> hesai_lidar
```

---

## 2. 环境文件

建议保留三个环境文件，避免 Wi-Fi、雷达有线、本机地图查看互相干扰。

### 2.1 Wi-Fi 控制环境

文件：

```bash
~/GO2_Project/go2_ros_env_wifi.sh
```

内容：

```bash
source /opt/ros/humble/setup.bash
export ROS_LOCALHOST_ONLY=0
export ROS_DOMAIN_ID=0
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
unset CYCLONEDDS_URI
```

用途：后台、Dashboard、WebSocket、普通控制链路。

### 2.2 雷达有线 / SLAM 环境

文件：

```bash
~/GO2_Project/go2_ros_env_lidar_wired.sh
```

内容：

```bash
source /opt/ros/humble/setup.bash
export ROS_LOCALHOST_ONLY=0
export ROS_DOMAIN_ID=0
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

export CYCLONEDDS_URI='<CycloneDDS><Domain><General><Interfaces>
<NetworkInterface name="enx00e04c36178d" priority="default" multicast="default" />
</Interfaces></General></Domain></CycloneDDS>'
```

用途：`/lidar_points`、`/scan`、`/scan_slam`、`slam_toolbox`、SLAM RViz。

如果有线网卡名字变了，先查：

```bash
ip -br addr
```

然后把 `enx00e04c36178d` 改成实际网卡名。

### 2.3 本机地图查看环境

文件：

```bash
~/GO2_Project/go2_ros_env_local.sh
```

内容：

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=1
unset CYCLONEDDS_URI
unset RMW_IMPLEMENTATION
```

用途：单独加载 `.yaml + .pgm` 地图，不连接 GO2，不连接雷达。

---

## 3. 完整测试流程总览

```text
1. 检查 Wi-Fi 和有线雷达网络
2. 启动 GO2 基础系统
3. 检查 /lidar_points
4. 启动 2D SLAM 管线
5. 检查 /scan_slam、/map、TF
6. 打开 RViz2 实时看图
7. 慢速采集地图
8. 保存地图
9. 复制为 latest 固定地图
10. 停止 SLAM
11. 单独加载 latest 地图
12. RViz2 验证地图能否重新显示
```

---

## 4. 启动前检查

### 4.1 检查有线雷达网络

笔记本执行：

```bash
source ~/GO2_Project/go2_ros_env_lidar_wired.sh

ip -br addr | grep -E "enx00e04c36178d|192.168.123"
ping -c 3 192.168.123.18
ping -c 3 192.168.123.20
```

期望：

```text
192.168.123.18  Jetson 有线口可 ping 通
192.168.123.20  XT-16 雷达可 ping 通
```

### 4.2 检查 Wi-Fi 控制网络

```bash
ping -c 3 192.168.7.149
ping -c 3 192.168.7.124
```

其中：

```text
192.168.7.149  Jetson Wi-Fi IP
192.168.7.124  笔记本 Wi-Fi / Backend IP
```

实际 IP 以 `~/GO2_Project/go2_bridge_ws/scripts/go2_network.env` 为准。

---

## 5. 启动 GO2 基础系统

### 5.1 终端 1：启动完整基础系统

笔记本执行：

```bash
cd ~/GO2_Project/go2_bridge_ws
bash scripts/start_all_go2_system.sh
```

这个脚本负责启动：

```text
- 笔记本 FastAPI backend
- Dashboard
- Jetson robot side
- GO2 状态上传
- 运动控制节点
- D435i 视频 / 拍照
- Hesai XT-16 雷达驱动
```

这个终端不要关闭。

### 5.2 检查雷达点云话题

新终端执行：

```bash
source ~/GO2_Project/go2_ros_env_lidar_wired.sh

ros2 topic list | grep lidar
ros2 topic info /lidar_points
timeout 10s ros2 topic hz /lidar_points
```

期望：

```text
/lidar_points
sensor_msgs/msg/PointCloud2
频率约 10Hz
```

---

## 6. 启动 2D SLAM 管线

### 6.1 终端 2：启动 2D SLAM

```bash
cd ~/GO2_Project/go2_bridge_ws
bash scripts/start_2d_slam_laptop.sh
```

当前启动脚本应包含：

```text
1. pointcloud_to_laserscan：/lidar_points -> /scan
2. scan_stamp_relay.py：/scan -> /scan_slam，修正时间戳并降频
3. odom_to_tf_bridge_now.py：/utlidar/robot_odom -> odom -> base_link
4. static_transform_publisher：base_link -> hesai_lidar
5. slam_toolbox：/scan_slam -> /map
```

### 6.2 查看 slam_toolbox 日志

```bash
tail -f ~/GO2_Project/go2_bridge_ws/logs/slam2d/slam_toolbox.log
```

正常应看到：

```text
Registering sensor: [Custom Described Lidar]
```

如果偶尔出现：

```text
discarding message because the queue is full
```

可以暂时忽略。如果持续刷屏，见第 13 节。

---

## 7. 检查 SLAM 话题与 TF

### 7.1 检查 `/scan_slam`

```bash
source ~/GO2_Project/go2_ros_env_lidar_wired.sh

ros2 topic info -v /scan_slam
timeout 10s ros2 topic hz /scan_slam
```

降负载后推荐频率：

```text
2Hz ~ 4Hz
```

### 7.2 检查 `/map`

```bash
ros2 topic info -v /map
timeout 10s ros2 topic hz /map
```

### 7.3 检查 TF

```bash
timeout 10s ros2 run tf2_ros tf2_echo odom base_link

timeout 10s ros2 run tf2_ros tf2_echo base_link hesai_lidar

timeout 10s ros2 run tf2_ros tf2_echo map odom
```

如果 `map -> odom` 有连续输出，说明 slam_toolbox 已经正常发布地图坐标变换。

---

## 8. RViz2 实时查看建图

### 8.1 终端 3：打开 RViz2

```bash
source ~/GO2_Project/go2_ros_env_lidar_wired.sh
rviz2
```

### 8.2 RViz2 设置

```text
Global Options:
  Fixed Frame = map

Add:
  TF
  Map，Topic = /map
  LaserScan，Topic = /scan_slam
```

也可以添加：

```text
PointCloud2，Topic = /lidar_points
```

### 8.3 观察重点

采集时观察：

```text
/map 是否持续扩展
/scan_slam 是否贴合地图边缘
TF 是否平滑
墙体是否出现双层重影
地图是否突然旋转或跳变
```

---

## 9. 建图采集技巧

推荐动作：

```text
1. 原地静止 5~10 秒
2. 慢速前进 0.5~1 m
3. 停 1~2 秒
4. 小角度转向 15~30 度
5. 停 1~2 秒
6. 再慢速前进
7. 走一个小矩形或小回环
8. 尽量回到接近起点的位置
9. 地图稳定后保存
```

建议速度：

```text
前进速度：0.10 ~ 0.15 m/s
横移速度：0.05 ~ 0.10 m/s，尽量少用
转向速度：0.20 ~ 0.35 rad/s
```

不建议：

```text
不要快速原地旋转
不要高速连续前进
不要大幅横移
不要边走边快速转弯
不要一开始就走很大范围
```

---

## 10. 保存地图

地图看起来稳定后，新开终端保存：

```bash
source ~/GO2_Project/go2_ros_env_lidar_wired.sh

mkdir -p ~/GO2_Project/maps

ros2 run nav2_map_server map_saver_cli \
  -f ~/GO2_Project/maps/go2_xt16_2d_map_$(date +%Y%m%d_%H%M%S)
```

保存成功时应看到：

```text
Map saved successfully
```

检查文件：

```bash
ls -lah ~/GO2_Project/maps
```

会生成：

```text
go2_xt16_2d_map_时间戳.yaml
go2_xt16_2d_map_时间戳.pgm
```

查看 yaml：

```bash
cat ~/GO2_Project/maps/go2_xt16_2d_map_时间戳.yaml
```

示例：

```yaml
image: go2_xt16_2d_map_20260706_165740.pgm
mode: trinary
resolution: 0.05
origin: [-7.61, -11.4, 0]
negate: 0
occupied_thresh: 0.65
free_thresh: 0.25
```

---

## 11. 生成 latest 固定地图名

为了后续 AMCL / Nav2 不频繁改路径，建议把效果最好的地图复制成固定名字。

假设当前地图名为：

```text
go2_xt16_2d_map_20260706_165740
```

先查看原始 yaml：

```bash
cat ~/GO2_Project/maps/go2_xt16_2d_map_20260706_165740.yaml
```

记住其中的 `origin`。然后执行：

```bash
cd ~/GO2_Project/maps

cp go2_xt16_2d_map_20260706_165740.pgm go2_xt16_2d_map_latest.pgm

cat > go2_xt16_2d_map_latest.yaml <<'MAPYAML'
image: /home/ceci/GO2_Project/maps/go2_xt16_2d_map_latest.pgm
mode: trinary
resolution: 0.05
origin: [-7.61, -11.4, 0]
negate: 0
occupied_thresh: 0.65
free_thresh: 0.25
MAPYAML
```

注意：如果原始 yaml 的 `origin` 不是 `[-7.61, -11.4, 0]`，要把 latest yaml 里的 `origin` 改成实际值。

检查 latest：

```bash
ls -lah ~/GO2_Project/maps/go2_xt16_2d_map_latest.*
cat ~/GO2_Project/maps/go2_xt16_2d_map_latest.yaml
```

---

## 12. 重新加载地图测试

### 12.1 停止 SLAM 管线

```bash
cd ~/GO2_Project/go2_bridge_ws
bash scripts/stop_2d_slam_laptop.sh
```

### 12.2 使用一键地图查看脚本

如果已经创建了 `start_map_view_local.sh`，直接执行：

```bash
cd ~/GO2_Project/go2_bridge_ws
bash scripts/start_map_view_local.sh
```

该脚本会自动：

```text
1. 关闭旧 map_server / RViz2
2. 启动 map_server
3. configure map_server
4. activate map_server
5. 使用固定 RViz 配置打开 /map
```

### 12.3 手动加载地图

终端 1：

```bash
source ~/GO2_Project/go2_ros_env_local.sh

ros2 run nav2_map_server map_server \
  --ros-args \
  -p yaml_filename:=/home/ceci/GO2_Project/maps/go2_xt16_2d_map_latest.yaml
```

保持终端 1 运行。

终端 2：

```bash
source ~/GO2_Project/go2_ros_env_local.sh

ros2 lifecycle get /map_server
ros2 lifecycle set /map_server configure
ros2 lifecycle get /map_server
ros2 lifecycle set /map_server activate
ros2 lifecycle get /map_server
```

最终应看到：

```text
active [3]
```

检查 `/map`：

```bash
ros2 topic info -v /map

timeout 5s ros2 topic echo --once \
  --qos-durability transient_local \
  --qos-reliability reliable \
  /map | sed -n '1,40p'
```

期望：

```text
Publisher count: 1
Reliability: RELIABLE
Durability: TRANSIENT_LOCAL
width: 地图宽度
height: 地图高度
```

终端 3：

```bash
source ~/GO2_Project/go2_ros_env_local.sh
rviz2
```

RViz2 设置：

```text
Fixed Frame = map
Add -> Map
Topic = /map
```

---

## 13. `queue is full` 持续刷屏处理

### 13.1 报错含义

日志：

```text
Message Filter dropping message: frame 'hesai_lidar' ... reason 'discarding message because the queue is full'
```

含义：

```text
/scan_slam 数据进入 slam_toolbox 的速度太快，slam_toolbox 处理不过来，内部队列堆满，所以丢弃部分 LaserScan。
```

偶尔出现可以忽略，持续刷屏需要降负载。

### 13.2 推荐降负载参数

在 `start_2d_slam_laptop.sh` 中，`pointcloud_to_laserscan` 推荐使用：

```bash
-p angle_increment:=0.00872 \
-p range_min:=0.45 \
-p range_max:=12.0 \
```

含义：

```text
angle_increment 0.00872：约 0.5°，比 0.25° 点数少一半
range_min 0.45：过滤太近的机身/腿部干扰
range_max 12.0：减少远距离杂点和匹配压力
```

在 `scan_stamp_relay.py` 启动参数中使用：

```bash
-p publish_every_n:=3
```

含义：

```text
每 3 帧发布 1 帧，约 10Hz -> 3.3Hz
```

如果还刷屏，改成：

```bash
-p publish_every_n:=5
```

即约 2Hz。

### 13.3 slam_toolbox 参数文件

文件：

```bash
~/GO2_Project/go2_bridge_ws/config/slam_2d/mapper_params_online_async.yaml
```

推荐关键参数：

```yaml
slam_toolbox:
  ros__parameters:
    use_sim_time: false

    odom_frame: odom
    map_frame: map
    base_frame: base_link
    scan_topic: /scan_slam
    mode: mapping

    throttle_scans: 1
    minimum_time_interval: 0.30
    map_update_interval: 4.0
    transform_publish_period: 0.05

    resolution: 0.05
    max_laser_range: 12.0

    transform_timeout: 0.5
    tf_buffer_duration: 30.0
    stack_size_to_use: 40000000

    minimum_travel_distance: 0.10
    minimum_travel_heading: 0.10

    use_scan_matching: true
    use_scan_barycenter: true
    scan_buffer_size: 5
    scan_buffer_maximum_scan_distance: 8.0

    do_loop_closing: false

    solver_plugin: solver_plugins::CeresSolver
    ceres_linear_solver: SPARSE_NORMAL_CHOLESKY
    ceres_preconditioner: SCHUR_JACOBI
    ceres_trust_strategy: LEVENBERG_MARQUARDT
    ceres_dogleg_type: TRADITIONAL_DOGLEG
    ceres_loss_function: None

    correlation_search_space_dimension: 0.3
    correlation_search_space_resolution: 0.01
    correlation_search_space_smear_deviation: 0.1

    distance_variance_penalty: 0.5
    angle_variance_penalty: 1.0
    fine_search_angle_offset: 0.00349
    coarse_search_angle_offset: 0.349
    coarse_angle_resolution: 0.0349
    minimum_angle_penalty: 0.9
    minimum_distance_penalty: 0.5
    use_response_expansion: true

    debug_logging: false
    enable_interactive_mode: true
```

---

## 14. 常见问题处理

### 14.1 `/opt/ros/humble/setup.bash: AMENT_TRACE_SETUP_FILES: 未绑定的变量`

原因：脚本开启了 `set -u`，然后 source ROS2 setup.bash，ROS 内部变量未定义导致报错。

解决：

```bash
set +u
source /opt/ros/humble/setup.bash
set -u
```

所以脚本里 source 环境文件时应写成：

```bash
set +u
source ~/GO2_Project/go2_ros_env_lidar_wired.sh
set -u
```

### 14.2 `enx00e04c36178d does not match an available interface`

原因：当前没有这个有线网卡，或者网卡名变了，但 `CYCLONEDDS_URI` 还绑定了它。

检查：

```bash
ip -br addr
```

如果只是本机加载地图，用：

```bash
source ~/GO2_Project/go2_ros_env_local.sh
```

不要用：

```bash
source ~/GO2_Project/go2_ros_env_lidar_wired.sh
```

### 14.3 `No map received`

先命令行检查：

```bash
source ~/GO2_Project/go2_ros_env_local.sh

ros2 lifecycle get /map_server
ros2 topic info -v /map

timeout 5s ros2 topic echo --once \
  --qos-durability transient_local \
  --qos-reliability reliable \
  /map | sed -n '1,40p'
```

判断：

```text
Publisher count: 0
  -> map_server 没启动或没激活

Subscription count: 0
  -> RViz 没订阅 /map

Publisher count: 1，Subscription count: 1
  -> 通信正常，检查 RViz Fixed Frame 和 Map Topic
```

### 14.4 `bad file: xxx.yaml`

原因通常是：

```text
yaml 内容格式坏了
image 指向的 pgm 不存在
相对路径解析失败
```

建议 latest yaml 使用绝对路径：

```yaml
image: /home/ceci/GO2_Project/maps/go2_xt16_2d_map_latest.pgm
mode: trinary
resolution: 0.05
origin: [-7.61, -11.4, 0]
negate: 0
occupied_thresh: 0.65
free_thresh: 0.25
```

---

## 15. 推荐测试记录命令

每次完整建图后建议保存一次状态记录。

```bash
source ~/GO2_Project/go2_ros_env_lidar_wired.sh

mkdir -p ~/GO2_Project/logs/slam_test_$(date +%Y%m%d_%H%M%S)
TEST_DIR=$(ls -td ~/GO2_Project/logs/slam_test_* | head -1)

ros2 topic list > $TEST_DIR/topic_list.txt
ros2 topic info -v /scan_slam > $TEST_DIR/scan_slam_info.txt
ros2 topic info -v /map > $TEST_DIR/map_info.txt
ros2 topic info -v /utlidar/robot_odom > $TEST_DIR/robot_odom_info.txt

timeout 5s ros2 run tf2_ros tf2_echo odom base_link > $TEST_DIR/tf_odom_base_link.txt
timeout 5s ros2 run tf2_ros tf2_echo base_link hesai_lidar > $TEST_DIR/tf_base_link_hesai_lidar.txt
timeout 5s ros2 run tf2_ros tf2_echo map odom > $TEST_DIR/tf_map_odom.txt

cp ~/GO2_Project/go2_bridge_ws/config/slam_2d/mapper_params_online_async.yaml $TEST_DIR/ 2>/dev/null || true

echo "Saved test logs to: $TEST_DIR"
```

---

## 16. 推荐录制 rosbag

如果某次地图效果好，或者出现问题需要复现，建议录包。

```bash
source ~/GO2_Project/go2_ros_env_lidar_wired.sh

mkdir -p ~/GO2_Project/rosbags
cd ~/GO2_Project/rosbags

ros2 bag record \
  /lidar_points \
  /scan \
  /scan_slam \
  /utlidar/robot_odom \
  /tf \
  /tf_static \
  /map \
  -o go2_xt16_2d_slam_$(date +%Y%m%d_%H%M%S)
```

录完按 `Ctrl + C`。

查看：

```bash
ros2 bag info go2_xt16_2d_slam_*
```

---

## 17. 完整复测命令清单

### 17.1 启动基础系统

```bash
cd ~/GO2_Project/go2_bridge_ws
bash scripts/start_all_go2_system.sh
```

### 17.2 启动 SLAM

```bash
cd ~/GO2_Project/go2_bridge_ws
bash scripts/start_2d_slam_laptop.sh
```

### 17.3 看日志

```bash
tail -f ~/GO2_Project/go2_bridge_ws/logs/slam2d/slam_toolbox.log
```

### 17.4 检查频率和 TF

```bash
source ~/GO2_Project/go2_ros_env_lidar_wired.sh

timeout 10s ros2 topic hz /scan_slam
timeout 10s ros2 run tf2_ros tf2_echo map odom
```

### 17.5 打开实时建图 RViz

```bash
source ~/GO2_Project/go2_ros_env_lidar_wired.sh
rviz2
```

RViz：

```text
Fixed Frame = map
Add -> TF
Add -> Map, Topic = /map
Add -> LaserScan, Topic = /scan_slam
```

### 17.6 保存地图

```bash
source ~/GO2_Project/go2_ros_env_lidar_wired.sh

mkdir -p ~/GO2_Project/maps

ros2 run nav2_map_server map_saver_cli \
  -f ~/GO2_Project/maps/go2_xt16_2d_map_$(date +%Y%m%d_%H%M%S)
```

### 17.7 停止 SLAM

```bash
cd ~/GO2_Project/go2_bridge_ws
bash scripts/stop_2d_slam_laptop.sh
```

### 17.8 加载 latest 地图

```bash
cd ~/GO2_Project/go2_bridge_ws
bash scripts/start_map_view_local.sh
```

---

## 18. 当前阶段完成标准

本阶段目标不是马上导航，而是验证：

```text
1. XT-16 可以稳定发布 /lidar_points
2. /lidar_points 可以转 /scan
3. /scan 可以修正时间戳并降频为 /scan_slam
4. slam_toolbox 可以生成 /map
5. map_saver_cli 可以保存 .yaml + .pgm
6. map_server 可以重新加载地图
7. RViz2 可以显示重新加载后的静态地图
```

全部通过后，再进入下一阶段：

```text
AMCL 定位
Nav2 路径规划
任务点导航
巡检路线管理
```
