#include <chrono>
#include <cmath>
#include <regex>
#include <string>

#include "rclcpp/rclcpp.hpp"
#include "std_msgs/msg/string.hpp"
#include "unitree_api/msg/request.hpp"
#include "unitree_api/msg/response.hpp"

#include "common/ros2_sport_client.h"

using namespace std::chrono_literals;

class BackendCommandHandlerNode : public rclcpp::Node
{
public:
  BackendCommandHandlerNode()
  : Node("backend_command_handler_node"),
    sport_client_(this)
  {
    // ============================================================
    // 1. 参数
    // ============================================================

    this->declare_parameter<std::string>("backend_command_topic", "/backend_command");
    this->declare_parameter<std::string>("sport_request_topic", "/api/sport/request");
    this->declare_parameter<std::string>("sport_response_topic", "/api/sport/response");

    // 默认前进速度。第一版必须低速。
    this->declare_parameter<double>("forward_speed", 0.15);

    // START_TASK / RESUME_TASK 默认持续时间，单位秒。
    this->declare_parameter<double>("forward_duration_sec", 1.0);

    // 控制请求重复发布周期。
    this->declare_parameter<double>("control_period_sec", 0.1);

    backend_command_topic_ = this->get_parameter("backend_command_topic").as_string();
    sport_request_topic_ = this->get_parameter("sport_request_topic").as_string();
    sport_response_topic_ = this->get_parameter("sport_response_topic").as_string();

    forward_speed_ = this->get_parameter("forward_speed").as_double();
    forward_duration_sec_ = this->get_parameter("forward_duration_sec").as_double();
    control_period_sec_ = this->get_parameter("control_period_sec").as_double();

    // ============================================================
    // 2. ROS2 发布与订阅
    // ============================================================

    command_sub_ = this->create_subscription<std_msgs::msg::String>(
      backend_command_topic_,
      10,
      std::bind(&BackendCommandHandlerNode::backendCommandCallback, this, std::placeholders::_1)
    );

    sport_request_pub_ = this->create_publisher<unitree_api::msg::Request>(
      sport_request_topic_,
      10
    );

    sport_response_sub_ = this->create_subscription<unitree_api::msg::Response>(
      sport_response_topic_,
      10,
      std::bind(&BackendCommandHandlerNode::sportResponseCallback, this, std::placeholders::_1)
    );

    timer_ = this->create_wall_timer(
      std::chrono::duration<double>(control_period_sec_),
      std::bind(&BackendCommandHandlerNode::controlTimerCallback, this)
    );

    RCLCPP_INFO(this->get_logger(), "backend_command_handler_node initialized");
    RCLCPP_INFO(this->get_logger(), "backend_command_topic: %s", backend_command_topic_.c_str());
    RCLCPP_INFO(this->get_logger(), "sport_request_topic: %s", sport_request_topic_.c_str());
    RCLCPP_INFO(this->get_logger(), "sport_response_topic: %s", sport_response_topic_.c_str());
    RCLCPP_INFO(this->get_logger(), "forward_speed: %.3f m/s", forward_speed_);
    RCLCPP_INFO(this->get_logger(), "forward_duration_sec: %.3f s", forward_duration_sec_);
  }

private:
  // ============================================================
  // JSON 简单解析
  // ============================================================

  std::string extractStringField(const std::string & json_text, const std::string & key)
  {
    // 简单提取形如：
    //   "command": "PAUSE_TASK"
    // 的字符串字段。
    //
    // 第一版只解析 backend_client_node 发来的固定 JSON 格式。
    const std::string pattern =
      "\"" + key + "\"\\s*:\\s*\"([^\"]*)\"";

    std::regex re(pattern);
    std::smatch match;

    if (std::regex_search(json_text, match, re) && match.size() >= 2) {
      return match[1].str();
    }

    return "";
  }

  // ============================================================
  // Backend command 回调
  // ============================================================

  void backendCommandCallback(const std_msgs::msg::String::SharedPtr msg)
  {
    const std::string raw = msg->data;

    const std::string command = extractStringField(raw, "command");
    const std::string command_id = extractStringField(raw, "command_id");

    if (command.empty()) {
      RCLCPP_WARN(this->get_logger(), "Received /backend_command without command field: %s", raw.c_str());
      return;
    }

    RCLCPP_INFO(
      this->get_logger(),
      "Received backend command: command=%s, command_id=%s",
      command.c_str(),
      command_id.c_str()
    );

    if (command == "PING") {
      RCLCPP_INFO(this->get_logger(), "PING received. No GO2 motion command will be sent.");
      return;
    }

    if (command == "PAUSE_TASK") {
      active_forward_ = false;
      publishStopMove("PAUSE_TASK");
      return;
    }

    if (command == "STOP_TASK") {
      active_forward_ = false;
      publishStopMove("STOP_TASK");
      return;
    }

    if (command == "EMERGENCY_STOP") {
      active_forward_ = false;

      // 急停命令连续发送 3 次，增加可靠性。
      publishStopMove("EMERGENCY_STOP");
      publishStopMove("EMERGENCY_STOP");
      publishStopMove("EMERGENCY_STOP");
      return;
    }

    if (command == "START_TASK" || command == "RESUME_TASK") {
      startForwardMotion(command);
      return;
    }

    RCLCPP_WARN(
      this->get_logger(),
      "Unsupported command: %s. StopMove will be sent for safety.",
      command.c_str()
    );

    active_forward_ = false;
    publishStopMove("UNSUPPORTED_COMMAND");
  }

  // ============================================================
  // Unitree Sport API 请求发布
  // ============================================================

  void publishStopMove(const std::string & reason)
  {
    unitree_api::msg::Request req;
    sport_client_.StopMove(req);
    sport_request_pub_->publish(req);

    RCLCPP_WARN(
      this->get_logger(),
      "Published StopMove. reason=%s",
      reason.c_str()
    );
  }

  void publishMoveForward()
  {
    unitree_api::msg::Request req;

    // vx > 0 表示前进。
    // vy = 0 不侧移。
    // vyaw = 0 不旋转。
    sport_client_.Move(
      req,
      static_cast<float>(forward_speed_),
      0.0f,
      0.0f
    );

    sport_request_pub_->publish(req);

    RCLCPP_INFO(
      this->get_logger(),
      "Published Move forward: vx=%.3f, vy=0.000, vyaw=0.000",
      forward_speed_
    );
  }

  void startForwardMotion(const std::string & reason)
  {
    active_forward_ = true;
    forward_end_time_ = this->now() + rclcpp::Duration::from_seconds(forward_duration_sec_);

    RCLCPP_WARN(
      this->get_logger(),
      "Start low-speed forward motion. reason=%s, speed=%.3f m/s, duration=%.3f s",
      reason.c_str(),
      forward_speed_,
      forward_duration_sec_
    );

    publishMoveForward();
  }

  // ============================================================
  // 定时器：持续发送低速前进命令，到时间后自动停止
  // ============================================================

  void controlTimerCallback()
  {
    if (!active_forward_) {
      return;
    }

    const rclcpp::Time now = this->now();

    if (now < forward_end_time_) {
      publishMoveForward();
      return;
    }

    active_forward_ = false;
    publishStopMove("AUTO_STOP_AFTER_DURATION");
  }

  // ============================================================
  // sport response 回调
  // ============================================================

  void sportResponseCallback(const unitree_api::msg::Response::SharedPtr msg)
  {
    (void)msg;

    // 第一版不解析 Response 具体字段，只确认收到了响应。
    // 如果后续需要更详细的执行反馈，再根据 unitree_api/msg/Response 字段补充。
    RCLCPP_DEBUG(this->get_logger(), "Received sport response.");
  }

private:
  SportClient sport_client_;

  std::string backend_command_topic_;
  std::string sport_request_topic_;
  std::string sport_response_topic_;

  double forward_speed_{0.15};
  double forward_duration_sec_{1.0};
  double control_period_sec_{0.1};

  bool active_forward_{false};
  rclcpp::Time forward_end_time_;

  rclcpp::Subscription<std_msgs::msg::String>::SharedPtr command_sub_;
  rclcpp::Publisher<unitree_api::msg::Request>::SharedPtr sport_request_pub_;
  rclcpp::Subscription<unitree_api::msg::Response>::SharedPtr sport_response_sub_;
  rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);

  auto node = std::make_shared<BackendCommandHandlerNode>();

  rclcpp::spin(node);

  rclcpp::shutdown();

  return 0;
}
