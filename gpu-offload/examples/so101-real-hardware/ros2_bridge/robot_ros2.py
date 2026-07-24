# SPDX-License-Identifier: MIT
# Adapted from an upstream GPU-offloading reference implementation.
#!/usr/bin/env python

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
Base class for ROS2-based robot implementations.

This module provides an abstract base class for robots that communicate via ROS2
instead of direct hardware bus connections. The ROS2Robot class bridges the LeRobot
Robot interface with ROS2 topics and actions.

Architecture:
    Application Code → ROS2Robot → ROS Topics/Actions → Hardware Bridge Node → Hardware

Example:
    class MyMobileBaseROS2(ROS2Robot):
        name = "my_mobile_base_ros2"
        config_class = MyRobotConfig

        def _get_action_msg_type(self):
            return Twist  # Velocity commands

        def _get_state_msg_type(self):
            return Odometry  # Pose/velocity feedback

        def _create_observation_from_msg(self, msg):
            return {"x": msg.pose.pose.position.x, "y": msg.pose.pose.position.y}

        def _create_action_msg(self, action):
            msg = Twist()
            msg.linear.x = action["linear_velocity"]
            msg.angular.z = action["angular_velocity"]
            return msg

    # For motor-based robots, use ROS2MotorRobot instead
"""

from __future__ import annotations

import abc
import logging
import threading
import time
from typing import Any

from lerobot.processor import RobotAction, RobotObservation
from lerobot.utils.decorators import check_if_already_connected, check_if_not_connected

from .robot import Robot

logger = logging.getLogger(__name__)

# ROS2 imports will be conditional to avoid dependency issues
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy

    # Motor-specific imports (only used in ROS2MotorRobot subclass)
    from sensor_msgs.msg import JointState
    from std_msgs.msg import Float64MultiArray, MultiArrayDimension

    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    # Create placeholder types/classes for when ROS2 is not available
    Node = None
    JointState = None
    Float64MultiArray = None
    MultiArrayDimension = None

    # Mock QoS classes
    class QoSProfile:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    class ReliabilityPolicy:
        RELIABLE = 1
        BEST_EFFORT = 2

    class HistoryPolicy:
        KEEP_LAST = 1
        KEEP_ALL = 2

    logger.warning("ROS2 not available. ROS2Robot classes will not function.")


class ROS2Robot(Robot):
    """
    Abstract base class for robots that communicate via ROS2.

    This class handles ROS2 communication, providing a bridge between the LeRobot
    Robot interface and ROS2 topics/actions. Subclasses must implement message
    conversion and type specification for their specific hardware.

    This base class is generic and does not assume motor-based robots. For robots
    with motor joints, use ROS2MotorRobot instead.

    Attributes:
        node (Node): ROS2 node for communication
        namespace (str): ROS2 namespace for topics
        connected (bool): Connection state
        calibrated (bool): Calibration state
    """

    def __init__(self, config):
        if not ROS2_AVAILABLE:
            raise RuntimeError("ROS2 is not available. Please install ROS2 dependencies.")

        super().__init__(config)
        self.config = config
        self.namespace = getattr(config, 'ros_namespace', f'/{self.name}')

        # ROS2 node and communication setup
        self.node: Node | None = None
        self._connected = False
        self._calibrated = True  # Assume calibrated via hardware bridge
        self._observation_lock = threading.Lock()
        self._latest_observation: RobotObservation = {}

        # Publishers and subscribers
        self._action_publisher = None
        self._state_subscriber = None
        self._calibration_publisher = None

        # QoS profile for reliable communication
        # depth=1: only the latest joint state / camera frame / command matters;
        # stale buffered messages would cause the robot to act on outdated data.
        self._qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )

    @abc.abstractmethod
    def _create_observation_from_msg(self, msg: Any) -> RobotObservation:
        """
        Convert ROS message to RobotObservation format.

        Args:
            msg: ROS message containing observation data

        Returns:
            RobotObservation: Dictionary with observation data
        """
        pass

    @abc.abstractmethod
    def _create_action_msg(self, action: RobotAction) -> Any:
        """
        Convert RobotAction to ROS message format.

        Args:
            action (RobotAction): Action dictionary

        Returns:
            ROS message ready to publish
        """
        pass

    @abc.abstractmethod
    def _get_action_msg_type(self):
        """
        Return the ROS message type for actions.

        Returns:
            ROS message class (e.g., JointState, Float64MultiArray, etc.)
        """
        pass

    @abc.abstractmethod
    def _get_state_msg_type(self):
        """
        Return the ROS message type for state/observations.

        Returns:
            ROS message class (e.g., JointState, Float64MultiArray, etc.)
        """
        pass

    @abc.abstractmethod
    def _get_calibration_msg_type(self):
        """
        Return the ROS message type for calibration data.

        Returns:
            ROS message class (e.g., Float64MultiArray, JointState, etc.)
            Return None if robot doesn't support calibration.
        """
        pass

    @abc.abstractmethod
    def _create_calibration_msg(self):
        """
        Convert robot calibration data to ROS message format.

        Returns:
            ROS message ready to publish, or None if no calibration available
        """
        pass

    def _get_action_topic_name(self) -> str:
        """Get the topic name for publishing actions."""
        # Use config override if available, otherwise use namespace/action
        if hasattr(self.config, 'ros_action_topic') and self.config.ros_action_topic:
            return self.config.ros_action_topic
        return f"{self.namespace}/action"

    def _get_state_topic_name(self) -> str:
        """Get the topic name for subscribing to state."""
        # Use config override if available, otherwise use namespace/state
        if hasattr(self.config, 'ros_state_topic') and self.config.ros_state_topic:
            return self.config.ros_state_topic
        return f"{self.namespace}/state"

    def _get_calibration_topic_name(self) -> str:
        """Get the topic name for publishing calibration data."""
        # Use config override if available, otherwise use namespace/calibration
        if hasattr(self.config, 'ros_calibration_topic') and self.config.ros_calibration_topic:
            return self.config.ros_calibration_topic
        return f"{self.namespace}/calibration"

    def _state_callback(self, msg: Any) -> None:
        """
        Callback for state topic subscription.

        Args:
            msg: ROS message containing state data
        """
        with self._observation_lock:
            self._latest_observation = self._create_observation_from_msg(msg)

    @property
    def is_connected(self) -> bool:
        """Whether the ROS2 robot is currently connected."""
        return self._connected and self.node is not None

    @property
    def is_calibrated(self) -> bool:
        """
        Whether the robot is calibrated.

        For ROS2 robots, we assume calibration is handled by the hardware bridge.
        """
        return self._calibrated

    @check_if_already_connected
    def connect(self, calibrate: bool = True) -> None:
        """
        Connect to the ROS2 robot by initializing node and topics.

        Args:
            calibrate (bool): If True and calibration exists, send it to hardware bridge
        """
        # Initialize ROS2 if not already done
        if not rclpy.ok():
            rclpy.init()

        # Create node
        node_name = f"{self.name}_{self.id}_client"
        self.node = Node(node_name)
        logger.info(f"Created ROS2 node: {node_name}")

        # Create publisher for actions (message type from subclass)
        action_topic = self._get_action_topic_name()
        action_msg_type = self._get_action_msg_type()
        self._action_publisher = self.node.create_publisher(
            action_msg_type,
            action_topic,
            self._qos_profile
        )
        logger.info(f"Created action publisher: topic='{action_topic}', type={action_msg_type.__name__}")

        # Create subscriber for state (message type from subclass)
        state_topic = self._get_state_topic_name()
        state_msg_type = self._get_state_msg_type()
        self._state_subscriber = self.node.create_subscription(
            state_msg_type,
            state_topic,
            self._state_callback,
            self._qos_profile
        )
        logger.info(f"Created state subscriber: topic='{state_topic}', type={state_msg_type.__name__}")

        # Create publisher for calibration if robot supports it
        calibration_msg_type = self._get_calibration_msg_type()
        if calibration_msg_type is not None:
            calibration_topic = self._get_calibration_topic_name()
            self._calibration_publisher = self.node.create_publisher(
                calibration_msg_type,
                calibration_topic,
                self._qos_profile
            )
            logger.info(f"Created calibration publisher: topic='{calibration_topic}', type={calibration_msg_type.__name__}")

        # Set connected flag BEFORE starting spin thread (spin checks this flag!)
        self._connected = True

        # Start spinning in a separate thread
        self._spin_thread = threading.Thread(target=self._spin_node, daemon=True)
        self._spin_thread.start()
        logger.info("Started ROS2 spin thread")

        # Give DDS discovery time to register subscriptions/publishers
        logger.info("Waiting for DDS discovery...")
        time.sleep(0.5)
        logger.info("DDS discovery complete")

        # Send calibration if available
        if self.calibration and calibrate and self._calibration_publisher:
            msg = self._create_calibration_msg()
            if msg is not None:
                self._calibration_publisher.publish(msg)
                logger.info(f"Published calibration data for {self.id}")

        logger.info(f"{self} connected via ROS2 on namespace {self.namespace}")

    def _spin_node(self) -> None:
        """Spin the ROS2 node in a separate thread."""
        while rclpy.ok() and self._connected:
            rclpy.spin_once(self.node, timeout_sec=0.01)

    def calibrate(self) -> None:
        """
        Calibration for ROS2 robots.

        This triggers the calibration procedure on the hardware bridge.
        Interactive prompts will appear on the hardware bridge terminal.
        """
        if not self.is_connected:
            raise RuntimeError(f"{self} must be connected before calling calibrate()")

        try:
            import rclpy
            from std_srvs.srv import Trigger

            # Create service client
            service_name = f"{self.namespace}/calibrate"
            client = self.node.create_client(Trigger, service_name)

            # Wait for service
            logger.info("Triggering calibration on hardware bridge...")
            logger.info("Follow the prompts on the hardware bridge terminal.")
            if not client.wait_for_service(timeout_sec=5.0):
                raise RuntimeError(
                    f"Calibration service not available at {service_name}. "
                    f"Make sure the hardware bridge is running."
                )

            # Call service
            request = Trigger.Request()
            future = client.call_async(request)

            # Wait for completion (calibration can take time)
            rclpy.spin_until_future_complete(self.node, future, timeout_sec=300.0)

            if future.result() is not None:
                response = future.result()
                if response.success:
                    logger.info("Calibration completed successfully")
                    self._calibrated = True
                else:
                    logger.error(f"Calibration failed: {response.message}")
                    raise RuntimeError(f"Calibration failed: {response.message}")
            else:
                raise RuntimeError("Calibration service call failed or timed out")

        except ImportError:
            raise RuntimeError("std_srvs not available. Install: pip install std-srvs")

    def configure(self) -> None:
        """
        Configure the robot.

        For ROS2 robots, configuration is automatically handled by the hardware
        bridge when it connects to the robot. This is a no-op on the client side.
        """
        logger.debug(f"Configuration for {self} is handled by the hardware bridge during connection.")

    @check_if_not_connected
    def get_observation(self) -> RobotObservation:
        """
        Get the latest observation from the robot.

        Returns:
            RobotObservation: Latest observation received from ROS2 topics
        """
        with self._observation_lock:
            if not self._latest_observation:
                logger.warning(f"{self} has no observation data yet. Waiting for messages...")
                # Wait a bit for messages to arrive
                time.sleep(0.1)
            return self._latest_observation.copy()

    @check_if_not_connected
    def send_action(self, action: RobotAction) -> RobotAction:
        """
        Send an action to the robot via ROS2.

        Args:
            action (RobotAction): Action to send

        Returns:
            RobotAction: The action that was sent (potentially modified)
        """
        msg = self._create_action_msg(action)
        action_topic = self._get_action_topic_name()

        # Log the actual message being sent
        logger.info(f"Publishing to '{action_topic}':")
        logger.info(f"  names: {msg.name}")
        logger.info(f"  positions: {[f'{p:.4f}' for p in msg.position]}")

        self._action_publisher.publish(msg)
        logger.debug("Action published successfully")

        # Return the action as-is (hardware bridge handles safety/clipping)
        return action

    @check_if_not_connected
    def disconnect(self) -> None:
        """Disconnect from the ROS2 robot."""
        self._connected = False

        if self.node:
            self.node.destroy_node()
            self.node = None

        logger.info(f"{self} disconnected from ROS2.")


class ROS2MotorRobot(ROS2Robot):
    """
    Specialized ROS2 robot for motor-based robots using JointState messages.

    This class provides a concrete implementation for robots that primarily use
    motor joints and can be represented using standard ROS JointState messages.

    Subclasses must implement:
    - _get_motor_names(): Return list of motor/joint names
    - observation_features and action_features properties (from Robot base class)
    """

    @abc.abstractmethod
    def _get_motor_names(self) -> list[str]:
        """
        Return the list of motor names for this robot.

        Returns:
            list[str]: Ordered list of motor names (e.g., ["shoulder_pan", "gripper"])
        """
        pass

    def _get_action_msg_type(self):
        """Return JointState message type for motor-based robots."""
        return JointState

    def _get_state_msg_type(self):
        """Return JointState message type for motor-based robots."""
        return JointState

    def _get_calibration_msg_type(self):
        """Return Float64MultiArray message type for motor calibration."""
        return Float64MultiArray

    def _create_calibration_msg(self):
        """
        Convert motor calibration data to Float64MultiArray message.

        Returns:
            Float64MultiArray message with calibration data, or None if unavailable
        """
        if not self.calibration:
            return None

        # This is a simplified version - actual implementation depends on calibration format
        # Subclasses can override this for specific calibration message formats
        msg = Float64MultiArray()
        # TODO: Populate msg.data with calibration values
        return msg

    def _create_observation_from_msg(self, msg: JointState) -> RobotObservation:
        """
        Convert JointState message to observation.

        Args:
            msg (JointState): ROS JointState message (positions in radians)

        Returns:
            RobotObservation: Observation dictionary (converted to degrees if config.use_degrees)
        """
        import math

        obs = {}
        motor_names = self._get_motor_names()

        # Check if config uses degrees (need to convert from radians)
        use_degrees = getattr(self.config, 'use_degrees', False)

        for i, name in enumerate(msg.name):
            if name in motor_names and i < len(msg.position):
                value = msg.position[i]
                # ROS2 JointState always in radians, convert if needed
                if use_degrees:
                    value = math.degrees(value)
                obs[f"{name}.pos"] = value

        return obs

    def _create_action_msg(self, action: RobotAction) -> JointState:
        """
        Convert action to JointState message.

        Args:
            action (RobotAction): Action dictionary

        Returns:
            JointState: ROS message (positions always in radians)
        """
        import math

        msg = JointState()
        msg.header.stamp = self.node.get_clock().now().to_msg()

        motor_names = self._get_motor_names()
        msg.name = motor_names
        msg.position = []

        # Check if config uses degrees (need to convert to radians for ROS2)
        use_degrees = getattr(self.config, 'use_degrees', False)

        for motor in motor_names:
            key = f"{motor}.pos"
            if key in action:
                value = action[key]
                # ROS2 JointState always uses radians
                if use_degrees:
                    original_value = value
                    value = math.radians(value)
                    logger.info(f"🔄 {motor}: {original_value:.2f}° → {value:.4f} rad")
                msg.position.append(value)
            else:
                logger.warning(f"Motor {motor} not in action, using 0.0")
                msg.position.append(0.0)

        return msg
