#include <chrono>
#include <cmath>
#include <cstdint>
#include <mutex>
#include <regex>
#include <string>
#include <thread>

#include "rclcpp/rclcpp.hpp"
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

    linear_speed_x_ = clampAbs(linear_speed_x_, max_linear_speed_x_);
    linear_speed_y_ = clampAbs(linear_speed_y_, max_linear_speed_y_);
    yaw_speed_ = clampAbs(yaw_speed_, max_yaw_speed_);
    move_duration_sec_ = clampRange(move_duration_sec_, 0.1, max_move_duration_sec_);
    control_period_sec_ = clampRange(control_period_sec_, 0.05, 1.0);

    command_sub_ = this->create_subscription<std_msgs::msg::String>(
      "/backend_command",
      10,
      std::bind(&BackendCommandHandlerNode::onCommand, this, std::placeholders::_1)
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
    } else if (command == "MOVE_BACKWARD") {
      startTimedMove(-linear_speed_x_, 0.0, 0.0, "MOVE_BACKWARD");
    } else if (command == "MOVE_LEFT") {
      startTimedMove(0.0, +linear_speed_y_, 0.0, "MOVE_LEFT");
    } else if (command == "MOVE_RIGHT") {
      startTimedMove(0.0, -linear_speed_y_, 0.0, "MOVE_RIGHT");
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
    } else {
      RCLCPP_WARN(this->get_logger(), "Unknown command: %s. Raw payload: %s",
                  command.c_str(), msg->data.c_str());
    }
  }

  void startTimedMove(double vx, double vy, double vyaw, const std::string & command_name)
  {
    std::lock_guard<std::mutex> lock(motion_mutex_);

    vx = clampAbs(vx, max_linear_speed_x_);
    vy = clampAbs(vy, max_linear_speed_y_);
    vyaw = clampAbs(vyaw, max_yaw_speed_);

    current_vx_ = vx;
    current_vy_ = vy;
    current_vyaw_ = vyaw;
    active_motion_ = true;
    motion_end_time_ = this->now() + secondsToDuration(move_duration_sec_);

    RCLCPP_INFO(
      this->get_logger(),
      "Start timed move: %s, vx=%.3f, vy=%.3f, vyaw=%.3f, duration=%.3f sec",
      command_name.c_str(), current_vx_, current_vy_, current_vyaw_, move_duration_sec_
    );

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

    if (!active_motion_) {
      return;
    }

    if (this->now() >= motion_end_time_) {
      clearMotionStateUnsafe();
      sendStopUnsafe();
      RCLCPP_INFO(this->get_logger(), "Timed move finished. Auto StopMove sent.");
      return;
    }

    sendMoveUnsafe(current_vx_, current_vy_, current_vyaw_);
  }

  void clearMotionStateUnsafe()
  {
    active_motion_ = false;
    current_vx_ = 0.0;
    current_vy_ = 0.0;
    current_vyaw_ = 0.0;
    motion_end_time_ = this->now();
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
  rclcpp::TimerBase::SharedPtr control_timer_;

  std::mutex motion_mutex_;

  bool active_motion_{false};
  double current_vx_{0.0};
  double current_vy_{0.0};
  double current_vyaw_{0.0};
  rclcpp::Time motion_end_time_{0, 0, RCL_ROS_TIME};

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
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);

  auto node = std::make_shared<BackendCommandHandlerNode>();
  rclcpp::spin(node);

  rclcpp::shutdown();
  return 0;
}
