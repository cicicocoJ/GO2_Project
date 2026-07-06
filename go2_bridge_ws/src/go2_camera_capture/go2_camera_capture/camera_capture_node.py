#!/usr/bin/env python3
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import cv2
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class CameraCaptureNode(Node):
    """
    D435i RGB camera capture node for GO2 inspection system.

    Subscribes:
      /camera_capture_command  std_msgs/String(JSON)
      /backend_command         std_msgs/String(JSON), optional

    Publishes:
      /camera_capture_result   std_msgs/String(JSON)
    """

    def __init__(self):
        super().__init__('camera_capture_node')

        self.declare_parameter('robot_id', 'GO2_001')
        self.declare_parameter('camera_index', 4)
        self.declare_parameter('image_dir', '/home/unitree/go2_captures')
        self.declare_parameter('image_width', 640)
        self.declare_parameter('image_height', 480)
        self.declare_parameter('jpeg_quality', 90)
        self.declare_parameter('warmup_frames', 10)
        self.declare_parameter('enable_backend_command', True)

        self.robot_id = self.get_parameter('robot_id').value
        self.camera_index = int(self.get_parameter('camera_index').value)
        self.image_dir = Path(str(self.get_parameter('image_dir').value))
        self.image_width = int(self.get_parameter('image_width').value)
        self.image_height = int(self.get_parameter('image_height').value)
        self.jpeg_quality = int(self.get_parameter('jpeg_quality').value)
        self.warmup_frames = int(self.get_parameter('warmup_frames').value)
        self.enable_backend_command = bool(self.get_parameter('enable_backend_command').value)

        self.image_dir.mkdir(parents=True, exist_ok=True)

        self.result_pub = self.create_publisher(
            String,
            '/camera_capture_result',
            10
        )

        self.capture_cmd_sub = self.create_subscription(
            String,
            '/camera_capture_command',
            self.capture_command_callback,
            10
        )

        self.backend_cmd_sub = None
        if self.enable_backend_command:
            self.backend_cmd_sub = self.create_subscription(
                String,
                '/backend_command',
                self.backend_command_callback,
                10
            )

        self.get_logger().info('camera_capture_node initialized')
        self.get_logger().info(f'robot_id: {self.robot_id}')
        self.get_logger().info(f'camera_index: {self.camera_index}')
        self.get_logger().info(f'image_dir: {self.image_dir}')
        self.get_logger().info(f'image_size: {self.image_width}x{self.image_height}')
        self.get_logger().info(f'jpeg_quality: {self.jpeg_quality}')
        self.get_logger().info(f'enable_backend_command: {self.enable_backend_command}')

    def parse_json(self, text: str) -> Dict[str, Any]:
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
            return {}
        except Exception as exc:
            self.get_logger().warn(f'Failed to parse JSON: {exc}; raw={text}')
            return {}

    def capture_command_callback(self, msg: String):
        data = self.parse_json(msg.data)
        command = data.get('command', 'CAPTURE_IMAGE')

        if command not in ['CAPTURE_IMAGE', 'TAKE_PHOTO', 'CAPTURE']:
            self.get_logger().warn(f'Unsupported camera command: {command}')
            return

        self.handle_capture_request(data, source_topic='/camera_capture_command')

    def backend_command_callback(self, msg: String):
        """
        Allow temporary testing through existing /backend_command.
        Later Dashboard can send CAPTURE_IMAGE directly using the current backend command API.
        """
        data = self.parse_json(msg.data)
        command = data.get('command', '')

        if command not in ['CAPTURE_IMAGE', 'TAKE_PHOTO', 'CAPTURE']:
            return

        self.handle_capture_request(data, source_topic='/backend_command')

    def safe_name(self, value: Any, default: str) -> str:
        text = str(value) if value is not None and str(value).strip() else default

        chars = []
        for ch in text:
            if ch.isalnum() or ch in ['_', '-', '.']:
                chars.append(ch)
            else:
                chars.append('_')

        return ''.join(chars)

    def build_image_path(self, request: Dict[str, Any]) -> Path:
        task_id = self.safe_name(request.get('task_id'), 'manual_task')
        checkpoint_id = self.safe_name(request.get('checkpoint_id'), 'manual_point')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]

        filename = f'{self.robot_id}_{task_id}_{checkpoint_id}_{timestamp}.jpg'
        return self.image_dir / filename

    def publish_result(self, result: Dict[str, Any]):
        msg = String()
        msg.data = json.dumps(result, ensure_ascii=False)
        self.result_pub.publish(msg)

    def open_camera(self):
        """
        Use V4L2 backend to avoid unstable GStreamer warnings on Jetson.
        """
        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_V4L2)

        if not cap.isOpened():
            # Fallback to default backend.
            cap.release()
            cap = cv2.VideoCapture(self.camera_index)

        return cap

    def handle_capture_request(self, request: Dict[str, Any], source_topic: str):
        command_id = request.get('command_id')
        task_id = request.get('task_id')
        checkpoint_id = request.get('checkpoint_id')

        self.get_logger().info(
            f'Received capture request from {source_topic}: '
            f'command_id={command_id}, task_id={task_id}, checkpoint_id={checkpoint_id}'
        )

        image_path = self.build_image_path(request)

        result = {
            'type': 'camera_capture_result',
            'robot_id': self.robot_id,
            'command_id': command_id,
            'task_id': task_id,
            'checkpoint_id': checkpoint_id,
            'success': False,
            'image_path': str(image_path),
            'timestamp': datetime.now().isoformat(),
            'error': None,
        }

        cap = None

        try:
            cap = self.open_camera()

            if not cap.isOpened():
                raise RuntimeError(f'Failed to open camera index {self.camera_index}')

            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.image_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.image_height)
            cap.set(cv2.CAP_PROP_FPS, 30)

            frame = None
            ok = False

            for _ in range(max(1, self.warmup_frames)):
                ok, frame = cap.read()
                time.sleep(0.03)

            ok, frame = cap.read()

            if not ok or frame is None:
                raise RuntimeError('Failed to read frame from camera')

            encode_params = [
                int(cv2.IMWRITE_JPEG_QUALITY),
                int(self.jpeg_quality),
            ]

            ok = cv2.imwrite(str(image_path), frame, encode_params)

            if not ok:
                raise RuntimeError(f'Failed to save image: {image_path}')

            file_size = os.path.getsize(image_path)

            result['success'] = True
            result['image_path'] = str(image_path)
            result['file_size_bytes'] = file_size
            result['width'] = int(frame.shape[1])
            result['height'] = int(frame.shape[0])

            self.get_logger().info(
                f'Image captured successfully: {image_path}, size={file_size} bytes'
            )

        except Exception as exc:
            result['success'] = False
            result['error'] = str(exc)
            self.get_logger().error(f'Capture failed: {exc}')

        finally:
            if cap is not None:
                cap.release()

        self.publish_result(result)


def main(args=None):
    rclpy.init(args=args)
    node = CameraCaptureNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
