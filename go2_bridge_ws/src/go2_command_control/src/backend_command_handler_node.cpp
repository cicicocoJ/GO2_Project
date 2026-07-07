#include <chrono>
#include <cmath>
#include <cstdint>
#include <cctype>
#include <mutex>
#include <regex>
#include <string>
#include <thread>

#include "rclcpp/rclcpp.hpp"
#include "nav_msgs/msg/odometry.hpp"
#include "std_msgs/msg/string.hpp"

#include "unitree_api/msg/request.hpp"
#include "common/ros2_sport_client.h"

using namespace std::chrono_literals;

class BackendCommandHandlerNode : public rclcpp::Node
{
public:
  BackendCommandHandlerNode()
  : Node("backend_command_handler_node"),
    sport_client_(this)
  {
    this->declare_parameter<double>("linear_speed_x", 0.30);
    this->declare_parameter<double>("linear_speed_y", 0.25);
    this->declare_parameter<double>("yaw_speed", 0.70);
    this->declare_parameter<double>("move_duration_sec", 1.5);
    this->declare_parameter<double>("control_period_sec", 0.1);

    // Safety limits.
    this->declare_parameter<double>("max_linear_speed_x", 0.40);
    this->declare_parameter<double>("max_linear_speed_y", 0.30);
    this->declare_parameter<double>("max_yaw_speed", 0.80);
    this->declare_parameter<double>("max_move_duration_sec", 2.0);
    this->declare_parameter<int>("emergency_stop_repeat", 3);

    // Before posture actions, optionally send StopMove once.
    this->declare_parameter<bool>("stop_before_posture", true);

    // Manual mapping motion profile and yaw lock.
    this->declare_parameter<bool>("enable_yaw_lock", true);
    this->declare_parameter<double>("yaw_lock_kp", 0.6);
    this->declare_parameter<double>("yaw_lock_max_correction", 0.10);
    this->declare_parameter<double>("mapping_forward_speed", 0.24);
    this->declare_parameter<double>("mapping_backward_speed", -0.22);
    this->declare_parameter<double>("mapping_turn_speed", 0.45);
    this->declare_parameter<double>("mapping_strafe_speed", 0.16);
    this->declare_parameter<double>("yaw_lock_log_interval_sec", 1.0);
    this->declare_parameter<bool>("enable_start_boost", true);
    this->declare_parameter<double>("forward_start_boost_speed", 0.28);
    this->declare_parameter<double>("backward_start_boost_speed", -0.26);
    this->declare_parameter<double>("start_boost_duration_sec", 0.5);

    // Dedicated mapping commands use short, effective high-level pulses.
    this->declare_parameter<double>("mapping_cmd_vx", 0.22);
    this->declare_parameter<double>("mapping_cmd_vy", 0.0);
    this->declare_parameter<double>("mapping_yaw_deadband_deg", 1.5);
    this->declare_parameter<double>("mapping_yaw_trigger_deg", 2.0);
    this->declare_parameter<double>("mapping_yaw_correction_rate", 0.50);
    this->declare_parameter<double>("mapping_yaw_correction_max", 0.70);
    this->declare_parameter<double>("mapping_control_period_sec", 0.10);
    this->declare_parameter<int>("mapping_yaw_pulse_cycles", 1);
    this->declare_parameter<double>("mapping_forward_step_duration_sec", 1.2);
    this->declare_parameter<double>("mapping_small_turn_rate", 0.70);
    this->declare_parameter<double>("mapping_small_turn_duration_sec", 0.20);
    this->declare_parameter<double>("mapping_log_interval_sec", 1.0);

    linear_speed_x_ = this->get_parameter("linear_speed_x").as_double();
    linear_speed_y_ = this->get_parameter("linear_speed_y").as_double();
    yaw_speed_ = this->get_parameter("yaw_speed").as_double();
    move_duration_sec_ = this->get_parameter("move_duration_sec").as_double();
    control_period_sec_ = this->get_parameter("control_period_sec").as_double();

    max_linear_speed_x_ = this->get_parameter("max_linear_speed_x").as_double();
    max_linear_speed_y_ = this->get_parameter("max_linear_speed_y").as_double();
    max_yaw_speed_ = this->get_parameter("max_yaw_speed").as_double();
    max_move_duration_sec_ = this->get_parameter("max_move_duration_sec").as_double();
    emergency_stop_repeat_ = this->get_parameter("emergency_stop_repeat").as_int();
    stop_before_posture_ = this->get_parameter("stop_before_posture").as_bool();

    enable_yaw_lock_ = this->get_parameter("enable_yaw_lock").as_bool();
    yaw_lock_kp_ = this->get_parameter("yaw_lock_kp").as_double();
    yaw_lock_max_correction_ = this->get_parameter("yaw_lock_max_correction").as_double();
    mapping_forward_speed_ = this->get_parameter("mapping_forward_speed").as_double();
    mapping_backward_speed_ = this->get_parameter("mapping_backward_speed").as_double();
    mapping_turn_speed_ = this->get_parameter("mapping_turn_speed").as_double();
    mapping_strafe_speed_ = this->get_parameter("mapping_strafe_speed").as_double();
    yaw_lock_log_interval_sec_ = this->get_parameter("yaw_lock_log_interval_sec").as_double();
    enable_start_boost_ = this->get_parameter("enable_start_boost").as_bool();
    forward_start_boost_speed_ = this->get_parameter("forward_start_boost_speed").as_double();
    backward_start_boost_speed_ = this->get_parameter("backward_start_boost_speed").as_double();
    start_boost_duration_sec_ = this->get_parameter("start_boost_duration_sec").as_double();
    mapping_cmd_vx_ = this->get_parameter("mapping_cmd_vx").as_double();
    mapping_cmd_vy_ = this->get_parameter("mapping_cmd_vy").as_double();
    mapping_yaw_deadband_deg_ = this->get_parameter("mapping_yaw_deadband_deg").as_double();
    mapping_yaw_trigger_deg_ = this->get_parameter("mapping_yaw_trigger_deg").as_double();
    mapping_yaw_correction_rate_ = this->get_parameter("mapping_yaw_correction_rate").as_double();
    mapping_yaw_correction_max_ = this->get_parameter("mapping_yaw_correction_max").as_double();
    mapping_control_period_sec_ = this->get_parameter("mapping_control_period_sec").as_double();
    mapping_yaw_pulse_cycles_ = this->get_parameter("mapping_yaw_pulse_cycles").as_int();
    mapping_forward_step_duration_sec_ = this->get_parameter("mapping_forward_step_duration_sec").as_double();
    mapping_small_turn_rate_ = this->get_parameter("mapping_small_turn_rate").as_double();
    mapping_small_turn_duration_sec_ = this->get_parameter("mapping_small_turn_duration_sec").as_double();
    mapping_log_interval_sec_ = this->get_parameter("mapping_log_interval_sec").as_double();

    linear_speed_x_ = clampAbs(linear_speed_x_, max_linear_speed_x_);
    linear_speed_y_ = clampAbs(linear_speed_y_, max_linear_speed_y_);
    yaw_speed_ = clampAbs(yaw_speed_, max_yaw_speed_);
    move_duration_sec_ = clampRange(move_duration_sec_, 0.1, max_move_duration_sec_);
    control_period_sec_ = clampRange(control_period_sec_, 0.05, 1.0);
    yaw_lock_kp_ = clampRange(yaw_lock_kp_, 0.0, 10.0);
    yaw_lock_max_correction_ = clampRange(std::fabs(yaw_lock_max_correction_), 0.0, max_yaw_speed_);
    mapping_forward_speed_ = clampRange(mapping_forward_speed_, 0.0, max_linear_speed_x_);
    mapping_backward_speed_ = clampRange(mapping_backward_speed_, -max_linear_speed_x_, 0.0);
    mapping_turn_speed_ = clampRange(mapping_turn_speed_, 0.0, max_yaw_speed_);
    mapping_strafe_speed_ = clampRange(mapping_strafe_speed_, 0.0, max_linear_speed_y_);
    yaw_lock_log_interval_sec_ = clampRange(yaw_lock_log_interval_sec_, 0.1, 60.0);
    forward_start_boost_speed_ = clampRange(forward_start_boost_speed_, 0.0, max_linear_speed_x_);
    backward_start_boost_speed_ = clampRange(backward_start_boost_speed_, -max_linear_speed_x_, 0.0);
    start_boost_duration_sec_ = clampRange(start_boost_duration_sec_, 0.0, 5.0);
    mapping_cmd_vx_ = clampRange(mapping_cmd_vx_, 0.0, max_linear_speed_x_);
    mapping_cmd_vy_ = clampAbs(mapping_cmd_vy_, max_linear_speed_y_);
    mapping_yaw_deadband_deg_ = clampRange(mapping_yaw_deadband_deg_, 0.0, 30.0);
    mapping_yaw_trigger_deg_ = clampRange(mapping_yaw_trigger_deg_, mapping_yaw_deadband_deg_, 45.0);
    mapping_yaw_correction_rate_ = clampRange(std::fabs(mapping_yaw_correction_rate_), 0.0, max_yaw_speed_);
    mapping_yaw_correction_max_ = clampRange(std::fabs(mapping_yaw_correction_max_), 0.0, max_yaw_speed_);
    mapping_control_period_sec_ = clampRange(mapping_control_period_sec_, 0.05, 1.0);
    if (mapping_yaw_pulse_cycles_ < 1) {
      mapping_yaw_pulse_cycles_ = 1;
    }
    if (mapping_yaw_pulse_cycles_ > 2) {
      mapping_yaw_pulse_cycles_ = 2;
    }
    mapping_forward_step_duration_sec_ = clampRange(mapping_forward_step_duration_sec_, 0.1, max_move_duration_sec_);
    mapping_small_turn_rate_ = clampRange(std::fabs(mapping_small_turn_rate_), 0.0, max_yaw_speed_);
    mapping_small_turn_duration_sec_ = clampRange(mapping_small_turn_duration_sec_, 0.05, 1.0);
    mapping_log_interval_sec_ = clampRange(mapping_log_interval_sec_, 0.1, 60.0);

    command_sub_ = this->create_subscription<std_msgs::msg::String>(
      "/backend_command",
      10,
      std::bind(&BackendCommandHandlerNode::onCommand, this, std::placeholders::_1)
    );

    odom_sub_ = this->create_subscription<nav_msgs::msg::Odometry>(
      "/utlidar/robot_odom",
      10,
      std::bind(&BackendCommandHandlerNode::onOdom, this, std::placeholders::_1)
    );

    auto timer_period = std::chrono::duration<double>(control_period_sec_);
    control_timer_ = this->create_wall_timer(
      std::chrono::duration_cast<std::chrono::milliseconds>(timer_period),
      std::bind(&BackendCommandHandlerNode::onControlTimer, this)
    );

    {
      std::lock_guard<std::mutex> lock(motion_mutex_);
      clearMotionStateUnsafe();
      sendStopUnsafe();
    }

    RCLCPP_INFO(this->get_logger(), "backend_command_handler_node started.");

    RCLCPP_INFO(this->get_logger(), "Safe motion commands:");
    RCLCPP_INFO(this->get_logger(), "  MOVE_FORWARD, MOVE_BACKWARD, MOVE_LEFT, MOVE_RIGHT");
    RCLCPP_INFO(this->get_logger(), "  TURN_LEFT, TURN_RIGHT, STOP_MOVE, EMERGENCY_STOP");
    RCLCPP_INFO(this->get_logger(), "Mapping commands:");
    RCLCPP_INFO(this->get_logger(), "  MAPPING_FORWARD_YAW_LOCK, MAPPING_FORWARD_STEP, MAPPING_TURN_LEFT_SMALL");
    RCLCPP_INFO(this->get_logger(), "  MAPPING_TURN_RIGHT_SMALL, MAPPING_STOP");

    RCLCPP_INFO(this->get_logger(), "Posture commands:");
    RCLCPP_INFO(this->get_logger(), "  STAND_DOWN, STAND_UP, BALANCE_STAND, RECOVERY_STAND");
    RCLCPP_INFO(this->get_logger(), "  SIT, RISE_SIT, DAMP");

    RCLCPP_INFO(this->get_logger(), "Compatible commands:");
    RCLCPP_INFO(this->get_logger(), "  START_TASK -> MOVE_FORWARD");
    RCLCPP_INFO(this->get_logger(), "  STOP_TASK / PAUSE_TASK -> STOP_MOVE");

    RCLCPP_INFO(
      this->get_logger(),
      "Params: linear_speed_x=%.3f, linear_speed_y=%.3f, yaw_speed=%.3f, move_duration_sec=%.3f, control_period_sec=%.3f, stop_before_posture=%s",
      linear_speed_x_,
      linear_speed_y_,
      yaw_speed_,
      move_duration_sec_,
      control_period_sec_,
      stop_before_posture_ ? "true" : "false"
    );

    RCLCPP_INFO(
      this->get_logger(),
      "Yaw lock params: enable_yaw_lock=%s, yaw_lock_kp=%.3f, yaw_lock_max_correction=%.3f, mapping_forward_speed=%.3f, mapping_backward_speed=%.3f, mapping_turn_speed=%.3f, mapping_strafe_speed=%.3f, yaw_lock_log_interval_sec=%.3f, enable_start_boost=%s, forward_start_boost_speed=%.3f, backward_start_boost_speed=%.3f, start_boost_duration_sec=%.3f",
      enable_yaw_lock_ ? "true" : "false",
      yaw_lock_kp_,
      yaw_lock_max_correction_,
      mapping_forward_speed_,
      mapping_backward_speed_,
      mapping_turn_speed_,
      mapping_strafe_speed_,
      yaw_lock_log_interval_sec_,
      enable_start_boost_ ? "true" : "false",
      forward_start_boost_speed_,
      backward_start_boost_speed_,
      start_boost_duration_sec_
    );

    RCLCPP_INFO(
      this->get_logger(),
      "Dedicated mapping params: vx=%.3f, vy=%.3f, yaw_deadband_deg=%.3f, yaw_trigger_deg=%.3f, yaw_correction_rate=%.3f, yaw_correction_max=%.3f, control_period_sec=%.3f, yaw_pulse_cycles=%d, step_duration=%.3f, small_turn_rate=%.3f, small_turn_duration=%.3f",
      mapping_cmd_vx_,
      mapping_cmd_vy_,
      mapping_yaw_deadband_deg_,
      mapping_yaw_trigger_deg_,
      mapping_yaw_correction_rate_,
      mapping_yaw_correction_max_,
      mapping_control_period_sec_,
      mapping_yaw_pulse_cycles_,
      mapping_forward_step_duration_sec_,
      mapping_small_turn_rate_,
      mapping_small_turn_duration_sec_
    );
  }

  ~BackendCommandHandlerNode()
  {
    std::lock_guard<std::mutex> lock(motion_mutex_);
    clearMotionStateUnsafe();
    sendStopUnsafe();
  }

private:
  static double clampAbs(double value, double max_abs)
  {
    if (max_abs <= 0.0) {
      return 0.0;
    }

    if (value > max_abs) {
      return max_abs;
    }

    if (value < -max_abs) {
      return -max_abs;
    }

    return value;
  }

  static double clampRange(double value, double min_value, double max_value)
  {
    if (value < min_value) {
      return min_value;
    }

    if (value > max_value) {
      return max_value;
    }

    return value;
  }

  static double normalizeAngle(double angle)
  {
    constexpr double kPi = 3.14159265358979323846;
    constexpr double kTwoPi = 2.0 * kPi;

    while (angle > kPi) {
      angle -= kTwoPi;
    }

    while (angle < -kPi) {
      angle += kTwoPi;
    }

    return angle;
  }

  template<typename QuaternionT>
  static double yawFromQuaternion(const QuaternionT & q)
  {
    const double siny_cosp = 2.0 * (q.w * q.z + q.x * q.y);
    const double cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z);
    return std::atan2(siny_cosp, cosy_cosp);
  }

  static rclcpp::Duration secondsToDuration(double seconds)
  {
    if (seconds < 0.0) {
      seconds = 0.0;
    }

    const int32_t sec = static_cast<int32_t>(std::floor(seconds));
    const uint32_t nanosec = static_cast<uint32_t>((seconds - static_cast<double>(sec)) * 1e9);
    return rclcpp::Duration(sec, nanosec);
  }

  static std::string trim(const std::string & input)
  {
    const auto begin = input.find_first_not_of(" \t\r\n\"");
    if (begin == std::string::npos) {
      return "";
    }

    const auto end = input.find_last_not_of(" \t\r\n\"");
    return input.substr(begin, end - begin + 1);
  }

  static std::string toUpperAscii(std::string value)
  {
    for (char & ch : value) {
      ch = static_cast<char>(std::toupper(static_cast<unsigned char>(ch)));
    }

    return value;
  }

  std::string extractCommand(const std::string & payload)
  {
    // Expected bridge format:
    // {"command":"MOVE_FORWARD","command_id":"xxx"}
    std::regex command_regex("\"command\"\\s*:\\s*\"([^\"]+)\"");
    std::smatch match;

    if (std::regex_search(payload, match, command_regex) && match.size() >= 2) {
      return trim(match[1].str());
    }

    // Also support directly publishing a plain string:
    // MOVE_FORWARD
    return trim(payload);
  }

  std::string normalizeCommand(const std::string & command)
  {
    const std::string upper_command = toUpperAscii(command);

    if (upper_command == "MAPPING_FORWARD_YAW_LOCK" ||
      upper_command == "MAPPING_FORWARD_STEP" ||
      upper_command == "MAPPING_TURN_LEFT_SMALL" ||
      upper_command == "MAPPING_TURN_RIGHT_SMALL" ||
      upper_command == "MAPPING_STOP")
    {
      return upper_command;
    }

    if (command == "START_TASK") {
      return "MOVE_FORWARD";
    }

    if (command == "STOP_TASK" || command == "PAUSE_TASK") {
      return "STOP_MOVE";
    }

    // Chinese aliases. These are optional, useful for manual debugging.
    if (command == "卧倒") {
      return "STAND_DOWN";
    }

    if (command == "站立") {
      return "STAND_UP";
    }

    if (command == "平衡站立") {
      return "BALANCE_STAND";
    }

    if (command == "恢复站立") {
      return "RECOVERY_STAND";
    }

    if (command == "坐下") {
      return "SIT";
    }

    if (command == "起坐" || command == "坐姿起来") {
      return "RISE_SIT";
    }

    return command;
  }

  void onOdom(const nav_msgs::msg::Odometry::SharedPtr msg)
  {
    const double yaw = yawFromQuaternion(msg->pose.pose.orientation);

    std::lock_guard<std::mutex> lock(motion_mutex_);
    latest_yaw_ = yaw;
    latest_yaw_valid_ = true;
  }

  void onCommand(const std_msgs::msg::String::SharedPtr msg)
  {
    const std::string raw_command = extractCommand(msg->data);
    const std::string command = normalizeCommand(raw_command);

    if (command.empty()) {
      RCLCPP_WARN(this->get_logger(), "Received empty backend command. Raw payload: %s", msg->data.c_str());
      return;
    }

    RCLCPP_INFO(this->get_logger(), "Received backend command: raw='%s', normalized='%s'",
                raw_command.c_str(), command.c_str());

    // First-batch safe motion commands.
    if (command == "MOVE_FORWARD") {
      startTimedMove(+linear_speed_x_, 0.0, 0.0, "MOVE_FORWARD");
    } else if (command == "MOVE_FORWARD_CONTINUOUS") {
      startContinuousMove(+linear_speed_x_, 0.0, 0.0, "MOVE_FORWARD_CONTINUOUS");
    } else if (command == "MOVE_BACKWARD") {
      startTimedMove(-linear_speed_x_, 0.0, 0.0, "MOVE_BACKWARD");
    } else if (command == "MOVE_BACKWARD_CONTINUOUS") {
      startContinuousMove(-linear_speed_x_, 0.0, 0.0, "MOVE_BACKWARD_CONTINUOUS");
    } else if (command == "MOVE_LEFT") {
      startTimedMove(0.0, +linear_speed_y_, 0.0, "MOVE_LEFT");
    } else if (command == "MOVE_LEFT_CONTINUOUS") {
      startContinuousMove(0.0, +linear_speed_y_, 0.0, "MOVE_LEFT_CONTINUOUS");
    } else if (command == "MOVE_RIGHT") {
      startTimedMove(0.0, -linear_speed_y_, 0.0, "MOVE_RIGHT");
    } else if (command == "MOVE_RIGHT_CONTINUOUS") {
      startContinuousMove(0.0, -linear_speed_y_, 0.0, "MOVE_RIGHT_CONTINUOUS");
    } else if (command == "TURN_LEFT") {
      startTimedMove(0.0, 0.0, +yaw_speed_, "TURN_LEFT");
    } else if (command == "TURN_RIGHT") {
      startTimedMove(0.0, 0.0, -yaw_speed_, "TURN_RIGHT");
    } else if (command == "STOP_MOVE") {
      stopMove("STOP_MOVE");
    } else if (command == "EMERGENCY_STOP") {
      emergencyStop();

    // Second-batch posture commands.
    } else if (command == "STAND_DOWN") {
      runPostureCommand("STAND_DOWN");
    } else if (command == "STAND_UP") {
      runPostureCommand("STAND_UP");
    } else if (command == "BALANCE_STAND") {
      runPostureCommand("BALANCE_STAND");
    } else if (command == "RECOVERY_STAND") {
      runPostureCommand("RECOVERY_STAND");
    } else if (command == "SIT") {
      runPostureCommand("SIT");
    } else if (command == "RISE_SIT") {
      runPostureCommand("RISE_SIT");
    } else if (command == "DAMP") {
      runPostureCommand("DAMP");
    } else if (command == "MAPPING_FORWARD_YAW_LOCK") {
      startMappingForwardYawLock();
    } else if (command == "MAPPING_FORWARD_STEP") {
      startMappingForwardStep();
    } else if (command == "MAPPING_TURN_LEFT_SMALL") {
      startMappingSmallTurn(+mapping_small_turn_rate_, "MAPPING_TURN_LEFT_SMALL");
    } else if (command == "MAPPING_TURN_RIGHT_SMALL") {
      startMappingSmallTurn(-mapping_small_turn_rate_, "MAPPING_TURN_RIGHT_SMALL");
    } else if (command == "MAPPING_STOP") {
      mappingStop();
    } else {
      RCLCPP_WARN(this->get_logger(), "Unknown command: %s. Raw payload: %s",
                  command.c_str(), msg->data.c_str());
    }
  }

  void startTimedMove(double vx, double vy, double vyaw, const std::string & command_name)
  {
    std::lock_guard<std::mutex> lock(motion_mutex_);

    clearMappingStateUnsafe();

    vx = clampAbs(vx, max_linear_speed_x_);
    vy = clampAbs(vy, max_linear_speed_y_);
    vyaw = clampAbs(vyaw, max_yaw_speed_);

    clearYawLockUnsafe();

    target_vx_ = vx;
    target_vy_ = vy;
    target_yaw_ = vyaw;
    current_vx_ = target_vx_;
    current_vy_ = target_vy_;
    current_vyaw_ = target_yaw_;
    active_motion_ = true;
    continuous_motion_ = false;
    active_motion_command_ = command_name;
    motion_end_time_ = this->now() + secondsToDuration(move_duration_sec_);

    RCLCPP_INFO(
      this->get_logger(),
      "Start timed move: %s, vx=%.3f, vy=%.3f, vyaw=%.3f, duration=%.3f sec",
      command_name.c_str(), current_vx_, current_vy_, current_vyaw_, move_duration_sec_
    );

    sendMoveUnsafe(current_vx_, current_vy_, current_vyaw_);
  }

  void startContinuousMove(double vx, double vy, double vyaw, const std::string & command_name)
  {
    std::lock_guard<std::mutex> lock(motion_mutex_);

    clearMappingStateUnsafe();

    vx = clampAbs(vx, max_linear_speed_x_);
    vy = clampAbs(vy, max_linear_speed_y_);
    vyaw = clampAbs(vyaw, max_yaw_speed_);

    clearYawLockUnsafe();

    target_vx_ = vx;
    target_vy_ = vy;
    target_yaw_ = vyaw;
    current_vx_ = target_vx_;
    current_vy_ = target_vy_;
    current_vyaw_ = target_yaw_;
    active_motion_ = true;
    continuous_motion_ = true;
    active_motion_command_ = command_name;

    // This timestamp is not used for continuous motion, but keeps state valid.
    motion_end_time_ = this->now();

    RCLCPP_WARN(
      this->get_logger(),
      "Start CONTINUOUS move: %s, vx=%.3f, vy=%.3f, vyaw=%.3f. It will keep moving until STOP_MOVE or EMERGENCY_STOP.",
      command_name.c_str(), current_vx_, current_vy_, current_vyaw_
    );

    sendMoveUnsafe(current_vx_, current_vy_, current_vyaw_);
  }

  void startYawLockedMove(double vx, const std::string & command_name, bool continuous)
  {
    std::lock_guard<std::mutex> lock(motion_mutex_);

    clearMappingStateUnsafe();

    vx = clampRange(vx, -max_linear_speed_x_, max_linear_speed_x_);

    const bool entering_new_yaw_lock_move =
      !active_motion_ ||
      !yaw_lock_active_ ||
      !(active_motion_command_ == "MOVE_FORWARD" ||
        active_motion_command_ == "MOVE_FORWARD_CONTINUOUS" ||
        active_motion_command_ == "MOVE_BACKWARD" ||
        active_motion_command_ == "MOVE_BACKWARD_CONTINUOUS") ||
      ((vx >= 0.0) != (target_vx_ >= 0.0));

    if (entering_new_yaw_lock_move) {
      if (latest_yaw_valid_) {
        yaw_ref_ = latest_yaw_;
        yaw_ref_valid_ = true;
        RCLCPP_INFO(
          this->get_logger(),
          "Yaw lock reference recorded for %s: yaw_ref=%.4f",
          command_name.c_str(),
          yaw_ref_
        );
      } else {
        yaw_ref_valid_ = false;
        RCLCPP_WARN(
          this->get_logger(),
          "Yaw lock requested for %s, but /utlidar/robot_odom yaw is not valid yet.",
          command_name.c_str()
        );
      }

      last_yaw_lock_log_time_ = this->now();
      motion_start_time_ = this->now();
    }

    yaw_lock_active_ = true;
    target_vx_ = vx;
    target_vy_ = 0.0;
    target_yaw_ = 0.0;
    active_motion_ = true;
    continuous_motion_ = continuous;
    active_motion_command_ = command_name;
    current_vx_ = computeYawLockedVxUnsafe();
    current_vy_ = target_vy_;
    current_vyaw_ = 0.0;

    if (continuous_motion_) {
      motion_end_time_ = this->now();
      RCLCPP_WARN(
        this->get_logger(),
        "Start yaw-locked CONTINUOUS move: %s, target_vx=%.3f, sent_vx=%.3f, start_boost=%s. It will keep moving until STOP_MOVE or EMERGENCY_STOP.",
        command_name.c_str(),
        target_vx_,
        current_vx_,
        isStartBoostActiveUnsafe() ? "true" : "false"
      );
    } else {
      motion_end_time_ = this->now() + secondsToDuration(move_duration_sec_);
      RCLCPP_INFO(
        this->get_logger(),
        "Start yaw-locked timed move: %s, target_vx=%.3f, sent_vx=%.3f, start_boost=%s, duration=%.3f sec",
        command_name.c_str(),
        target_vx_,
        current_vx_,
        isStartBoostActiveUnsafe() ? "true" : "false",
        move_duration_sec_
      );
    }

    sendMoveUnsafe(current_vx_, current_vy_, current_vyaw_);
  }

  void stopMove(const std::string & reason)
  {
    std::lock_guard<std::mutex> lock(motion_mutex_);

    clearMotionStateUnsafe();
    sendStopUnsafe();

    RCLCPP_WARN(this->get_logger(), "StopMove called. reason=%s", reason.c_str());
  }

  void emergencyStop()
  {
    std::lock_guard<std::mutex> lock(motion_mutex_);

    clearMotionStateUnsafe();

    RCLCPP_ERROR(this->get_logger(), "EMERGENCY_STOP received. Sending StopMove repeatedly.");

    int repeat = emergency_stop_repeat_;
    if (repeat < 1) {
      repeat = 1;
    }
    if (repeat > 10) {
      repeat = 10;
    }

    for (int i = 0; i < repeat; ++i) {
      sendStopUnsafe();
      std::this_thread::sleep_for(60ms);
    }

    RCLCPP_ERROR(this->get_logger(), "Emergency stop finished. Motion state cleared.");
  }

  void runPostureCommand(const std::string & command)
  {
    std::lock_guard<std::mutex> lock(motion_mutex_);

    clearMotionStateUnsafe();

    if (stop_before_posture_) {
      sendStopUnsafe();
      std::this_thread::sleep_for(100ms);
    }

    RCLCPP_WARN(this->get_logger(), "Run posture command: %s", command.c_str());

    if (command == "STAND_DOWN") {
      sport_client_.StandDown(req_);
      RCLCPP_WARN(this->get_logger(), "Posture command sent: StandDown");
    } else if (command == "STAND_UP") {
      sport_client_.StandUp(req_);
      RCLCPP_WARN(this->get_logger(), "Posture command sent: StandUp");
    } else if (command == "BALANCE_STAND") {
      sport_client_.BalanceStand(req_);
      RCLCPP_WARN(this->get_logger(), "Posture command sent: BalanceStand");
    } else if (command == "RECOVERY_STAND") {
      sport_client_.RecoveryStand(req_);
      RCLCPP_WARN(this->get_logger(), "Posture command sent: RecoveryStand");
    } else if (command == "SIT") {
      sport_client_.Sit(req_);
      RCLCPP_WARN(this->get_logger(), "Posture command sent: Sit");
    } else if (command == "RISE_SIT") {
      sport_client_.RiseSit(req_);
      RCLCPP_WARN(this->get_logger(), "Posture command sent: RiseSit");
    } else if (command == "DAMP") {
      sport_client_.Damp(req_);
      RCLCPP_ERROR(this->get_logger(), "Posture command sent: Damp. Use RECOVERY_STAND or remote controller if needed.");
    } else {
      RCLCPP_WARN(this->get_logger(), "Unsupported posture command: %s", command.c_str());
    }
  }

  void onControlTimer()
  {
    std::lock_guard<std::mutex> lock(motion_mutex_);

    if (mapping_mode_active_) {
      handleMappingTimerUnsafe();
      return;
    }

    if (!active_motion_) {
      return;
    }

    if (!continuous_motion_ && this->now() >= motion_end_time_) {
      clearMotionStateUnsafe();
      sendStopUnsafe();
      RCLCPP_INFO(this->get_logger(), "Timed move finished. Auto StopMove sent.");
      return;
    }

    if (yaw_lock_active_ &&
      (isForwardCommand(active_motion_command_) ||
      isBackwardCommand(active_motion_command_)))
    {
      const double yaw_correction = computeYawLockCorrection();
      current_vx_ = computeYawLockedVxUnsafe();
      current_vy_ = 0.0;
      current_vyaw_ = yaw_correction;
      maybeLogYawLockUnsafe(yaw_correction);
      sendMoveUnsafe(current_vx_, current_vy_, current_vyaw_);
      return;
    }

    current_vx_ = target_vx_;
    current_vy_ = target_vy_;
    current_vyaw_ = target_yaw_;
    sendMoveUnsafe(current_vx_, current_vy_, current_vyaw_);
  }

  void clearMotionStateUnsafe()
  {
    active_motion_ = false;
    continuous_motion_ = false;
    yaw_lock_active_ = false;
    yaw_ref_valid_ = false;
    active_motion_command_ = "STOP";
    target_vx_ = 0.0;
    target_vy_ = 0.0;
    target_yaw_ = 0.0;
    current_vx_ = 0.0;
    current_vy_ = 0.0;
    current_vyaw_ = 0.0;
    motion_end_time_ = this->now();
    motion_start_time_ = this->now();
    clearMappingStateUnsafe();
  }

  void clearYawLockUnsafe()
  {
    yaw_lock_active_ = false;
    yaw_ref_valid_ = false;
  }

  static double radToDeg(double value)
  {
    constexpr double kRadToDeg = 180.0 / 3.14159265358979323846;
    return value * kRadToDeg;
  }

  bool setMappingTargetYawUnsafe(const std::string & command_name)
  {
    if (!latest_yaw_valid_) {
      RCLCPP_WARN(
        this->get_logger(),
        "%s requested, but /utlidar/robot_odom yaw is not valid yet. Mapping command ignored.",
        command_name.c_str()
      );
      return false;
    }

    mapping_target_yaw_ = latest_yaw_;
    mapping_target_yaw_valid_ = true;
    return true;
  }

  void startMappingForwardYawLock()
  {
    std::lock_guard<std::mutex> lock(motion_mutex_);

    clearMotionStateUnsafe();

    if (!setMappingTargetYawUnsafe("MAPPING_FORWARD_YAW_LOCK")) {
      return;
    }

    mapping_mode_active_ = true;
    mapping_mode_ = "MAPPING_FORWARD_YAW_LOCK";
    active_motion_command_ = mapping_mode_;
    mapping_mode_start_time_ = this->now();
    mapping_last_control_time_ = rclcpp::Time(0, 0, RCL_ROS_TIME);
    mapping_last_log_time_ = this->now();
    mapping_yaw_pulse_cycles_remaining_ = 0;

    RCLCPP_INFO(
      this->get_logger(),
      "MAPPING_FORWARD_YAW_LOCK started: target_yaw=%.4f, vx=%.3f, control_period=%.3f",
      mapping_target_yaw_,
      mapping_cmd_vx_,
      mapping_control_period_sec_
    );
  }

  void startMappingForwardStep()
  {
    std::lock_guard<std::mutex> lock(motion_mutex_);

    clearMotionStateUnsafe();

    if (!setMappingTargetYawUnsafe("MAPPING_FORWARD_STEP")) {
      return;
    }

    mapping_mode_active_ = true;
    mapping_mode_ = "MAPPING_FORWARD_STEP";
    active_motion_command_ = mapping_mode_;
    mapping_mode_start_time_ = this->now();
    mapping_last_control_time_ = rclcpp::Time(0, 0, RCL_ROS_TIME);
    mapping_last_log_time_ = this->now();
    mapping_yaw_pulse_cycles_remaining_ = 0;

    RCLCPP_INFO(
      this->get_logger(),
      "MAPPING_FORWARD_STEP started: step_duration=%.3f, target_yaw=%.4f, vx=%.3f",
      mapping_forward_step_duration_sec_,
      mapping_target_yaw_,
      mapping_cmd_vx_
    );
  }

  void startMappingSmallTurn(double yaw_rate, const std::string & command_name)
  {
    std::lock_guard<std::mutex> lock(motion_mutex_);

    clearMotionStateUnsafe();

    mapping_mode_active_ = true;
    mapping_mode_ = command_name;
    active_motion_command_ = mapping_mode_;
    mapping_target_yaw_valid_ = false;
    mapping_turn_yaw_rate_ = clampAbs(yaw_rate, mapping_yaw_correction_max_);
    mapping_mode_start_time_ = this->now();
    mapping_last_control_time_ = rclcpp::Time(0, 0, RCL_ROS_TIME);
    mapping_last_log_time_ = this->now();
    mapping_yaw_pulse_cycles_remaining_ = 0;

    RCLCPP_INFO(
      this->get_logger(),
      "%s started: yaw_rate=%.3f, duration=%.3f",
      command_name.c_str(),
      mapping_turn_yaw_rate_,
      mapping_small_turn_duration_sec_
    );
  }

  void mappingStop()
  {
    std::lock_guard<std::mutex> lock(motion_mutex_);

    RCLCPP_WARN(this->get_logger(), "MAPPING_STOP received. Exit mapping control mode.");
    clearMotionStateUnsafe();
    sendMoveUnsafe(0.0, 0.0, 0.0);
    sendStopUnsafe();
  }

  double computeMappingYawRateUnsafe()
  {
    if (!mapping_target_yaw_valid_ || !latest_yaw_valid_) {
      return 0.0;
    }

    const double yaw_error = normalizeAngle(mapping_target_yaw_ - latest_yaw_);
    const double yaw_error_abs_deg = std::fabs(radToDeg(yaw_error));

    if (mapping_yaw_pulse_cycles_remaining_ > 0) {
      --mapping_yaw_pulse_cycles_remaining_;
      return clampAbs(mapping_yaw_pulse_rate_, mapping_yaw_correction_max_);
    }

    if (yaw_error_abs_deg < mapping_yaw_deadband_deg_) {
      mapping_yaw_pulse_rate_ = 0.0;
      return 0.0;
    }

    if (yaw_error_abs_deg >= mapping_yaw_trigger_deg_) {
      mapping_yaw_pulse_rate_ = (yaw_error >= 0.0) ?
        mapping_yaw_correction_rate_ : -mapping_yaw_correction_rate_;
      mapping_yaw_pulse_rate_ = clampAbs(mapping_yaw_pulse_rate_, mapping_yaw_correction_max_);
      mapping_yaw_pulse_cycles_remaining_ = mapping_yaw_pulse_cycles_ - 1;
      return mapping_yaw_pulse_rate_;
    }

    return 0.0;
  }

  void maybeLogMappingUnsafe(double yaw_rate, bool pulse_active)
  {
    const rclcpp::Time now = this->now();
    const double elapsed_sec = (now - mapping_last_log_time_).seconds();

    if (elapsed_sec < mapping_log_interval_sec_) {
      return;
    }

    double yaw_error_deg = 0.0;
    if (mapping_target_yaw_valid_ && latest_yaw_valid_) {
      yaw_error_deg = radToDeg(normalizeAngle(mapping_target_yaw_ - latest_yaw_));
    }

    RCLCPP_INFO(
      this->get_logger(),
      "Mapping control: mode=%s, current_yaw=%.4f, target_yaw=%.4f, yaw_error_deg=%.2f, yaw_rate=%.3f, pulse=%s",
      mapping_mode_.c_str(),
      latest_yaw_,
      mapping_target_yaw_,
      yaw_error_deg,
      yaw_rate,
      pulse_active ? "true" : "false"
    );

    mapping_last_log_time_ = now;
  }

  void handleMappingTimerUnsafe()
  {
    const rclcpp::Time now = this->now();

    if (mapping_last_control_time_.nanoseconds() != 0 &&
      (now - mapping_last_control_time_).seconds() < mapping_control_period_sec_)
    {
      return;
    }

    mapping_last_control_time_ = now;

    if (mapping_mode_ == "MAPPING_FORWARD_YAW_LOCK" || mapping_mode_ == "MAPPING_FORWARD_STEP") {
      if (mapping_mode_ == "MAPPING_FORWARD_STEP" &&
        (now - mapping_mode_start_time_).seconds() >= mapping_forward_step_duration_sec_)
      {
        RCLCPP_INFO(this->get_logger(), "MAPPING_FORWARD_STEP finished. StopMove sent.");
        clearMotionStateUnsafe();
        sendMoveUnsafe(0.0, 0.0, 0.0);
        sendStopUnsafe();
        return;
      }

      const int pulse_cycles_before = mapping_yaw_pulse_cycles_remaining_;
      const double yaw_rate = computeMappingYawRateUnsafe();
      const bool pulse_active = std::fabs(yaw_rate) > 1e-6 || pulse_cycles_before > 0;
      maybeLogMappingUnsafe(yaw_rate, pulse_active);
      sendMoveUnsafe(mapping_cmd_vx_, mapping_cmd_vy_, yaw_rate);
      return;
    }

    if (mapping_mode_ == "MAPPING_TURN_LEFT_SMALL" || mapping_mode_ == "MAPPING_TURN_RIGHT_SMALL") {
      if ((now - mapping_mode_start_time_).seconds() >= mapping_small_turn_duration_sec_) {
        RCLCPP_INFO(this->get_logger(), "%s finished. StopMove sent.", mapping_mode_.c_str());
        clearMotionStateUnsafe();
        sendMoveUnsafe(0.0, 0.0, 0.0);
        sendStopUnsafe();
        return;
      }

      sendMoveUnsafe(0.0, 0.0, mapping_turn_yaw_rate_);
      return;
    }

    RCLCPP_WARN(this->get_logger(), "Unknown mapping mode '%s'. StopMove sent.", mapping_mode_.c_str());
    clearMotionStateUnsafe();
    sendStopUnsafe();
  }

  void clearMappingStateUnsafe()
  {
    mapping_mode_active_ = false;
    mapping_mode_ = "NONE";
    mapping_target_yaw_valid_ = false;
    mapping_turn_yaw_rate_ = 0.0;
    mapping_yaw_pulse_rate_ = 0.0;
    mapping_yaw_pulse_cycles_remaining_ = 0;
  }

  double computeYawLockCorrection()
  {
    if (!enable_yaw_lock_) {
      return 0.0;
    }

    if (!latest_yaw_valid_ || !yaw_ref_valid_) {
      return 0.0;
    }

    const double error = normalizeAngle(yaw_ref_ - latest_yaw_);
    const double correction = yaw_lock_kp_ * error;
    return clampAbs(correction, yaw_lock_max_correction_);
  }

  bool isForwardCommand(const std::string & command) const
  {
    return command == "MOVE_FORWARD" || command == "MOVE_FORWARD_CONTINUOUS";
  }

  bool isBackwardCommand(const std::string & command) const
  {
    return command == "MOVE_BACKWARD" || command == "MOVE_BACKWARD_CONTINUOUS";
  }

  bool isStartBoostActiveUnsafe()
  {
    if (!enable_start_boost_) {
      return false;
    }

    if (!isForwardCommand(active_motion_command_) && !isBackwardCommand(active_motion_command_)) {
      return false;
    }

    const double elapsed_sec = (this->now() - motion_start_time_).seconds();
    return elapsed_sec >= 0.0 && elapsed_sec < start_boost_duration_sec_;
  }

  double computeYawLockedVxUnsafe()
  {
    if (isForwardCommand(active_motion_command_)) {
      if (isStartBoostActiveUnsafe()) {
        return forward_start_boost_speed_;
      }
      return mapping_forward_speed_;
    }

    if (isBackwardCommand(active_motion_command_)) {
      if (isStartBoostActiveUnsafe()) {
        return backward_start_boost_speed_;
      }
      return mapping_backward_speed_;
    }

    return target_vx_;
  }

  void maybeLogYawLockUnsafe(double yaw_correction)
  {
    if (!enable_yaw_lock_ || !latest_yaw_valid_ || !yaw_ref_valid_) {
      return;
    }

    const rclcpp::Time now = this->now();
    const double elapsed_sec = (now - last_yaw_lock_log_time_).seconds();

    if (elapsed_sec < yaw_lock_log_interval_sec_) {
      return;
    }

    const double yaw_error = normalizeAngle(yaw_ref_ - latest_yaw_);
    const bool start_boost_active = isStartBoostActiveUnsafe();

    RCLCPP_INFO(
      this->get_logger(),
      "Yaw lock: command=%s, start_boost=%s, sent_vx=%.3f, yaw_ref=%.4f, latest_yaw=%.4f, yaw_error=%.4f, yaw_correction=%.4f",
      active_motion_command_.c_str(),
      start_boost_active ? "true" : "false",
      current_vx_,
      yaw_ref_,
      latest_yaw_,
      yaw_error,
      yaw_correction
    );

    last_yaw_lock_log_time_ = now;
  }

  void sendMoveUnsafe(double vx, double vy, double vyaw)
  {
    sport_client_.Move(req_, vx, vy, vyaw);
  }

  void sendStopUnsafe()
  {
    sport_client_.StopMove(req_);
  }

private:
  SportClient sport_client_;
  unitree_api::msg::Request req_;

  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr command_sub_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_sub_;
  rclcpp::TimerBase::SharedPtr control_timer_;

  std::mutex motion_mutex_;

  bool active_motion_{false};
  bool continuous_motion_{false};
  double current_vx_{0.0};
  double current_vy_{0.0};
  double current_vyaw_{0.0};
  std::string active_motion_command_{"STOP"};
  double target_vx_{0.0};
  double target_vy_{0.0};
  double target_yaw_{0.0};
  rclcpp::Time motion_end_time_{0, 0, RCL_ROS_TIME};
  rclcpp::Time motion_start_time_{0, 0, RCL_ROS_TIME};

  double linear_speed_x_{0.30};
  double linear_speed_y_{0.25};
  double yaw_speed_{0.70};
  double move_duration_sec_{1.5};
  double control_period_sec_{0.1};

  double max_linear_speed_x_{0.40};
  double max_linear_speed_y_{0.30};
  double max_yaw_speed_{0.80};
  double max_move_duration_sec_{2.0};
  int emergency_stop_repeat_{3};

  bool stop_before_posture_{true};

  bool enable_yaw_lock_{true};
  bool yaw_lock_active_{false};
  bool yaw_ref_valid_{false};
  bool latest_yaw_valid_{false};
  double yaw_ref_{0.0};
  double latest_yaw_{0.0};
  double yaw_lock_kp_{0.6};
  double yaw_lock_max_correction_{0.10};
  double mapping_forward_speed_{0.24};
  double mapping_backward_speed_{-0.22};
  double mapping_turn_speed_{0.45};
  double mapping_strafe_speed_{0.16};
  double yaw_lock_log_interval_sec_{1.0};
  bool enable_start_boost_{true};
  double forward_start_boost_speed_{0.28};
  double backward_start_boost_speed_{-0.26};
  double start_boost_duration_sec_{0.5};
  rclcpp::Time last_yaw_lock_log_time_{0, 0, RCL_ROS_TIME};

  bool mapping_mode_active_{false};
  std::string mapping_mode_{"NONE"};
  bool mapping_target_yaw_valid_{false};
  double mapping_target_yaw_{0.0};
  double mapping_turn_yaw_rate_{0.0};
  double mapping_yaw_pulse_rate_{0.0};
  int mapping_yaw_pulse_cycles_remaining_{0};
  rclcpp::Time mapping_mode_start_time_{0, 0, RCL_ROS_TIME};
  rclcpp::Time mapping_last_control_time_{0, 0, RCL_ROS_TIME};
  rclcpp::Time mapping_last_log_time_{0, 0, RCL_ROS_TIME};

  double mapping_cmd_vx_{0.22};
  double mapping_cmd_vy_{0.0};
  double mapping_yaw_deadband_deg_{1.5};
  double mapping_yaw_trigger_deg_{2.0};
  double mapping_yaw_correction_rate_{0.50};
  double mapping_yaw_correction_max_{0.70};
  double mapping_control_period_sec_{0.10};
  int mapping_yaw_pulse_cycles_{1};
  double mapping_forward_step_duration_sec_{1.2};
  double mapping_small_turn_rate_{0.70};
  double mapping_small_turn_duration_sec_{0.20};
  double mapping_log_interval_sec_{1.0};
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);

  auto node = std::make_shared<BackendCommandHandlerNode>();
  rclcpp::spin(node);

  rclcpp::shutdown();
  return 0;
}
