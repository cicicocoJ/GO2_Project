cmake_minimum_required(VERSION 3.5)
project(go2_command_control)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)
find_package(unitree_api REQUIRED)

# Unitree 官方 ROS2 示例源码路径。
# 注意：这个路径需要在 Jetson 上存在。
set(UNITREE_EXAMPLE_SRC_DIR "/home/unitree/unitree_ros2/example/src")

include_directories(
  ${UNITREE_EXAMPLE_SRC_DIR}/include
  ${UNITREE_EXAMPLE_SRC_DIR}/include/common
)

add_executable(backend_command_handler_node
  src/backend_command_handler_node.cpp
  ${UNITREE_EXAMPLE_SRC_DIR}/src/common/ros2_sport_client.cpp
)

ament_target_dependencies(
  backend_command_handler_node
  rclcpp
  std_msgs
  unitree_api
)

install(
  TARGETS backend_command_handler_node
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
