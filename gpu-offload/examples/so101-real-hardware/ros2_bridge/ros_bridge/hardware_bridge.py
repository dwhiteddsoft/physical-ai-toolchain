# SPDX-License-Identifier: MIT
# Adapted from an upstream GPU-offloading reference implementation.
#!/usr/bin/env python3

# Copyright 2026 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Base ROS2 hardware bridge node for LeRobot robots.

This module provides a base class for creating hardware bridge nodes that connect
ROS2 topics/actions to physical robot hardware via motor buses.

The bridge node:
1. Subscribes to action commands from ROS2 clients
2. Forwards commands to physical hardware (motor bus)
3. Publishes hardware state back to ROS2 clients
4. Handles calibration and configuration

Architecture:
    ROS2Robot (client) → ROS2 Topics → HardwareBridge → Motor Bus → Physical Robot

Example:
    ```python
    from lerobot.robots.ros_bridge import RobotHardwareBridge
    from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

    class SO101Bridge(RobotHardwareBridge):
        def create_robot(self):
            config = SO101FollowerConfig(
                port=self.declare_parameter('port', '/dev/ttyUSB0').value,
                id=self.declare_parameter('robot_id', 'follower').value
            )
            return SO101Follower(config)

    rclpy.init()
    bridge = SO101Bridge()
    rclpy.spin(bridge)
    ```
"""

from __future__ import annotations

import abc
import logging
import traceback
from typing import Any

import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64MultiArray, String
from std_srvs.srv import Trigger

logger = logging.getLogger(__name__)


class RobotHardwareBridge(Node, abc.ABC):
    """
    Base class for hardware bridge nodes.

    This node acts as a bridge between ROS2 and physical robot hardware.
    It receives action commands via ROS2 topics and forwards them to the
    hardware, while publishing hardware state back to ROS2.

    Subclasses must implement:
        - create_robot(): Factory method to create the robot instance

    Attributes:
        robot: The physical robot instance
        namespace: ROS2 namespace for topics
        publish_rate: Rate (Hz) at which to publish state
    """

    def __init__(self, node_name: str = 'robot_hardware_bridge'):
        """
        Initialize the hardware bridge node.

        Args:
            node_name (str): Name of the ROS2 node
        """
        super().__init__(node_name)

        # Declare parameters
        self.declare_parameter('namespace', '/robot')
        self.declare_parameter('publish_rate', 50.0)  # Hz
        self.declare_parameter('port', '/dev/ttyUSB0')
        self.declare_parameter('robot_id', 'robot')
        self.declare_parameter('calibrate_on_start', True)

        # Get parameters
        self.namespace = self.get_parameter('namespace').value
        publish_rate = self.get_parameter('publish_rate').value
        calibrate_on_start = self.get_parameter('calibrate_on_start').value

        # QoS profile — depth=1: only the latest state/command matters
        self.qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )

        # Create robot instance
        try:
            self.robot = self.create_robot()
            self.get_logger().info(f"Created robot: {self.robot}")
        except Exception as e:
            self.get_logger().error(f"Failed to create robot: {e}")
            self.get_logger().error(traceback.format_exc())
            raise

        # Connect to robot
        try:
            self.robot.connect(calibrate=calibrate_on_start)
            self.get_logger().info(f"Connected to robot on {self.namespace}")
        except Exception as e:
            self.get_logger().error(f"Failed to connect to robot: {e}")
            self.get_logger().error(traceback.format_exc())
            raise

        # Create publishers
        self.state_publisher = self.create_publisher(
            JointState,
            f"{self.namespace}/state",
            self.qos_profile
        )

        self.status_publisher = self.create_publisher(
            String,
            f"{self.namespace}/status",
            self.qos_profile
        )

        # Create subscribers
        self.action_subscriber = self.create_subscription(
            JointState,
            f"{self.namespace}/action",
            self.action_callback,
            self.qos_profile
        )

        self.calibration_subscriber = self.create_subscription(
            Float64MultiArray,
            f"{self.namespace}/calibration",
            self.calibration_callback,
            self.qos_profile
        )

        # Create service for motor setup
        self.setup_motors_service = self.create_service(
            Trigger,
            f"{self.namespace}/setup_motors",
            self.setup_motors_callback
        )

        # Create service for calibration
        self.calibrate_service = self.create_service(
            Trigger,
            f"{self.namespace}/calibrate",
            self.calibrate_callback_service
        )

        # Create timer for publishing state
        timer_period = 1.0 / publish_rate
        self.timer = self.create_timer(timer_period, self.publish_state)

        # State tracking
        self.last_action = None
        self.error_count = 0
        self.max_errors = 10

        self.get_logger().info(f"Hardware bridge initialized for {self.namespace}")
        self.get_logger().info(f"Publishing state at {publish_rate} Hz")

        # Publish initial status
        self._publish_status("connected")

    @abc.abstractmethod
    def create_robot(self):
        """
        Factory method to create the robot instance.

        This method must be implemented by subclasses to create and configure
        the specific robot hardware instance.

        Returns:
            Robot: An instance of a Robot subclass
        """
        pass

    def action_callback(self, msg: JointState) -> None:
        """
        Callback for action commands from ROS2 clients.

        Args:
            msg (JointState): Action command message
        """
        try:
            # Convert JointState to action dict
            action = self._joint_state_to_action(msg)

            # Send action to robot
            self.robot.send_action(action)
            self.last_action = action

            # Reset error count on success
            if self.error_count > 0:
                self.error_count = 0
                self._publish_status("connected")

        except Exception as e:
            self.error_count += 1
            self.get_logger().error(f"Error sending action: {e}")

            if self.error_count >= self.max_errors:
                self.get_logger().error(f"Too many errors ({self.error_count}), shutting down")
                self._publish_status("error")
                rclpy.shutdown()

    def publish_state(self) -> None:
        """Timer callback to publish robot state."""
        try:
            # Get observation from robot
            obs = self.robot.get_observation()

            # Convert to JointState message
            msg = self._observation_to_joint_state(obs)

            # Publish
            self.state_publisher.publish(msg)

        except Exception as e:
            self.error_count += 1
            self.get_logger().error(f"Error getting/publishing state: {e}")

            if self.error_count >= self.max_errors:
                self.get_logger().error(f"Too many errors ({self.error_count}), shutting down")
                self._publish_status("error")
                rclpy.shutdown()

    def calibration_callback(self, msg: Float64MultiArray) -> None:
        """
        Callback for calibration data from ROS2 clients.

        Args:
            msg (Float64MultiArray): Calibration data
        """
        self.get_logger().info("Received calibration request")
        # Subclasses can implement specific calibration handling
        # For now, we assume calibration is done offline

    def setup_motors_callback(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        """
        Service callback for motor setup requests.

        This runs the interactive motor setup procedure on the hardware bridge side.

        Args:
            request: Empty trigger request
            response: Response indicating success/failure

        Returns:
            Trigger.Response with success status and message
        """
        self.get_logger().info("Received setup_motors request")
        self.get_logger().info("Starting interactive motor setup procedure...")

        try:
            # Check if robot has setup_motors method
            if not hasattr(self.robot, 'setup_motors'):
                response.success = False
                response.message = "Robot does not support setup_motors()"
                return response

            # Run the setup procedure
            # This will prompt the user on this terminal
            self.robot.setup_motors()

            response.success = True
            response.message = "Motor setup completed successfully"
            self.get_logger().info("Motor setup completed")

        except Exception as e:
            response.success = False
            response.message = f"Motor setup failed: {e!s}"
            self.get_logger().error(f"Motor setup failed: {e}")
            self.get_logger().error(traceback.format_exc())

        return response

    def calibrate_callback_service(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        """
        Service callback for calibration requests.

        This runs the interactive calibration procedure on the hardware bridge side.

        Args:
            request: Empty trigger request
            response: Response indicating success/failure

        Returns:
            Trigger.Response with success status and message
        """
        self.get_logger().info("Received calibration request")
        self.get_logger().info("Starting interactive calibration procedure...")

        try:
            # Run the calibration procedure
            # This will prompt the user on this terminal
            self.robot.calibrate()

            response.success = True
            response.message = "Calibration completed successfully"
            self.get_logger().info("Calibration completed")

        except Exception as e:
            response.success = False
            response.message = f"Calibration failed: {e!s}"
            self.get_logger().error(f"Calibration failed: {e}")
            self.get_logger().error(traceback.format_exc())

        return response

    def _joint_state_to_action(self, msg: JointState) -> dict[str, float]:
        """
        Convert JointState message to action dictionary.

        Args:
            msg (JointState): ROS JointState message

        Returns:
            dict: Action dictionary
        """
        action = {}
        for i, name in enumerate(msg.name):
            if i < len(msg.position):
                action[f"{name}.pos"] = msg.position[i]
        return action

    def _observation_to_joint_state(self, obs: dict[str, Any]) -> JointState:
        """
        Convert observation dictionary to JointState message.

        Args:
            obs (dict): Observation dictionary

        Returns:
            JointState: ROS message
        """
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()

        # Extract motor positions from observation
        for key, value in obs.items():
            if key.endswith('.pos') and isinstance(value, (int, float)):
                motor_name = key.replace('.pos', '')
                msg.name.append(motor_name)
                msg.position.append(float(value))

        return msg

    def _publish_status(self, status: str) -> None:
        """
        Publish status message.

        Args:
            status (str): Status string
        """
        msg = String()
        msg.data = status
        self.status_publisher.publish(msg)

    def destroy_node(self) -> None:
        """Clean up resources when node is destroyed."""
        self.get_logger().info("Shutting down hardware bridge")

        try:
            if self.robot and self.robot.is_connected:
                self.robot.disconnect()
        except Exception as e:
            self.get_logger().error(f"Error disconnecting robot: {e}")

        super().destroy_node()


def main(bridge_class: type[RobotHardwareBridge], args=None):
    """
    Main entry point for hardware bridge nodes.

    Args:
        bridge_class: The hardware bridge class to instantiate
        args: Command-line arguments
    """
    rclpy.init(args=args)

    try:
        bridge = bridge_class()
        rclpy.spin(bridge)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Error in hardware bridge: {e}")
        logger.error(traceback.format_exc())
    finally:
        try:
            bridge.destroy_node()
        except:  # noqa: E722
            pass

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    # This is a base class and shouldn't be run directly
    logger.error("RobotHardwareBridge is a base class. Use a specific implementation.")
