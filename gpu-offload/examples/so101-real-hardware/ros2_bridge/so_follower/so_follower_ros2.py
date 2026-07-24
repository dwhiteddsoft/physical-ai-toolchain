# SPDX-License-Identifier: MIT
# Adapted from Microsoft Research "xavier-tutorial" (GPU-offloading reference architecture).
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
ROS2 implementation of SO-100/101 Follower robots.

This module provides ROS2-based implementations of the SO Follower robots that
communicate via ROS2 topics instead of direct serial bus connections.

Example usage:
    ```python
    from lerobot.robots.so_follower import SO101FollowerROS2, SO101FollowerConfigROS

    config = SO101FollowerConfigROS(
        port="/dev/ttyUSB0",  # Ignored by ROS2
        id="my_follower",
        ros_state_topic="/joint_states",    # Custom topic names
        ros_action_topic="/joint_command"
    )

    robot = SO101FollowerROS2(config)
    robot.connect()

    # Get observations
    obs = robot.get_observation()

    # Send actions
    action = {
        "shoulder_pan.pos": 0.0,
        "shoulder_lift.pos": 0.0,
        "elbow_flex.pos": 0.0,
        "wrist_flex.pos": 0.0,
        "wrist_roll.pos": 0.0,
        "gripper.pos": 0.0
    }
    robot.send_action(action)
    ```
"""

from __future__ import annotations

import logging
from functools import cached_property
from typing import TypeAlias

from lerobot.cameras.utils import make_cameras_from_configs
from lerobot.processor import RobotObservation

from ..robot_ros2 import ROS2MotorRobot
from .config_so_follower_ros import SOFollowerRobotConfigROS

logger = logging.getLogger(__name__)

# Conditional ROS2 imports
try:
    from sensor_msgs.msg import Image, JointState
    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    Image = None


class SOFollowerROS2(ROS2MotorRobot):
    """
    ROS2 implementation of SO Follower robots.

    This class communicates with a hardware bridge node instead of directly
    with the motor bus. It maintains the same interface as the standard
    SOFollower but uses ROS2 topics for communication.

    Topics:
        - /{namespace}/action (sensor_msgs/JointState): Commands to send to robot
        - /{namespace}/state (sensor_msgs/JointState): Current robot state
        - /{namespace}/camera/* (sensor_msgs/Image): Camera feeds (if configured)
    """

    config_class = SOFollowerRobotConfigROS
    name = "so_follower_ros2"

    # Motor names in order
    MOTOR_NAMES = [
        "shoulder_pan",
        "shoulder_lift",
        "elbow_flex",
        "wrist_flex",
        "wrist_roll",
        "gripper"
    ]

    def __init__(self, config: SOFollowerRobotConfigROS):
        super().__init__(config)
        self.config = config

        # Camera setup (cameras can still be local or ROS-based)
        self.cameras = make_cameras_from_configs(config.cameras) if config.cameras else {}
        self._camera_subscribers = {}
        self._latest_camera_images = {}

    def _get_motor_names(self) -> list[str]:
        """Return the list of motor names for SO Follower."""
        return self.MOTOR_NAMES

    @property
    def _motors_ft(self) -> dict[str, type]:
        return {f"{motor}.pos": float for motor in self.MOTOR_NAMES}

    @property
    def _cameras_ft(self) -> dict[str, tuple]:
        features = {}

        # Add local camera features
        if self.config.cameras:
            features.update({
                cam_name: (cam_config.height, cam_config.width, 3)
                for cam_name, cam_config in self.config.cameras.items()
            })

        # Add ROS2 camera features (default to 480x640x3 if not specified)
        if self.config.ros_camera_topics:
            for cam_name in self.config.ros_camera_topics:
                if cam_name not in features:  # Don't override local cameras
                    features[cam_name] = (480, 640, 3)  # Default camera resolution

        return features

    @cached_property
    def observation_features(self) -> dict[str, type | tuple]:
        """
        Observation features including motors and cameras.

        Returns:
            dict: Feature names mapped to types/shapes
        """
        return {**self._motors_ft, **self._cameras_ft}

    @cached_property
    def action_features(self) -> dict[str, type]:
        """
        Action features for SO Follower.

        Returns:
            dict: Motor action features
        """
        return self._motors_ft

    def connect(self, calibrate: bool = True) -> None:
        """
        Connect to the robot via ROS2.

        Args:
            calibrate (bool): Whether to send calibration data to hardware bridge
        """
        super().connect(calibrate=calibrate)

        # Setup camera subscribers for ROS2 camera topics
        if ROS2_AVAILABLE and self.config.ros_camera_topics:
            from functools import partial
            logger.info(f"Setting up {len(self.config.ros_camera_topics)} ROS2 camera subscribers...")
            for cam_name, topic in self.config.ros_camera_topics.items():
                # Use partial to properly capture cam_name (avoid lambda late binding issue)
                callback = partial(self._camera_callback, camera_name=cam_name)
                sub = self.node.create_subscription(
                    Image,
                    topic,
                    callback,
                    self._qos_profile
                )
                self._camera_subscribers[cam_name] = sub
                self._latest_camera_images[cam_name] = None  # Initialize
                logger.info(f"✓ Subscribed to camera '{cam_name}' on topic '{topic}'")
            logger.info("All camera subscriptions created. Waiting for messages...")
        else:
            if not ROS2_AVAILABLE:
                logger.warning("ROS2 not available - skipping camera setup")
            elif not self.config.ros_camera_topics:
                logger.info("No ros_camera_topics configured - skipping camera setup")

        # Connect local cameras if any
        for camera in self.cameras.values():
            if not camera.is_connected:
                camera.connect()

    def _camera_callback(self, msg: Image, camera_name: str) -> None:
        """
        Callback for camera image topics.

        Args:
            msg (Image): ROS Image message
            camera_name (str): Name of the camera
        """
        logger.info(f"🎥 Camera callback triggered for '{camera_name}': {msg.width}x{msg.height}, encoding={msg.encoding}")
        if ROS2_AVAILABLE:
            try:
                # Import cv_bridge when needed (not required for basic ROS2)
                from cv_bridge import CvBridge
                cv_bridge = CvBridge()
                # Convert ROS image to numpy array
                image = cv_bridge.imgmsg_to_cv2(msg, desired_encoding='rgb8')
                self._latest_camera_images[camera_name] = image
                logger.info(f"✓ Converted {camera_name} image to numpy: {image.shape}, dtype={image.dtype}")
            except Exception as e:
                logger.error(f"❌ Error processing {camera_name} image: {e}")

    def get_observation(self) -> RobotObservation:
        """
        Get observation including motor states and camera images.

        Returns:
            RobotObservation: Dictionary with all observation data
        """
        # Get motor observations from parent class
        # NOTE: Parent class already converts radians to degrees if use_degrees=True
        obs = super().get_observation()

        # Add local camera observations
        for cam_name, camera in self.cameras.items():
            if camera.is_connected:
                obs[cam_name] = camera.read()

        # Add ROS camera observations (include even if None to show in observation features)
        if self.config.ros_camera_topics:
            for cam_name in self.config.ros_camera_topics:
                obs[cam_name] = self._latest_camera_images.get(cam_name, None)

        return obs

    def setup_motors(self) -> None:
        """
        Setup motors by triggering the setup process on the hardware bridge.

        This method sends a service request to the hardware bridge node to run
        the motor setup procedure. The interactive prompts will appear on the
        hardware bridge terminal.

        Note: The hardware bridge must be running for this to work.
        """
        if not ROS2_AVAILABLE:
            raise RuntimeError("ROS2 is not available")

        if not self.is_connected:
            raise RuntimeError(f"{self} must be connected before calling setup_motors()")

        try:
            import rclpy
            from std_srvs.srv import Trigger

            # Create service client
            service_name = f"{self.namespace}/setup_motors"
            client = self.node.create_client(Trigger, service_name)

            # Wait for service
            logger.info(f"Waiting for setup_motors service at {service_name}...")
            if not client.wait_for_service(timeout_sec=5.0):
                raise RuntimeError(
                    f"Setup motors service not available at {service_name}. "
                    f"Make sure the hardware bridge is running."
                )

            # Call service
            logger.info("Triggering motor setup on hardware bridge...")
            logger.info("Follow the prompts on the hardware bridge terminal.")

            request = Trigger.Request()
            future = client.call_async(request)

            # Wait for completion
            rclpy.spin_until_future_complete(self.node, future, timeout_sec=300.0)  # 5 min timeout

            if future.result() is not None:
                response = future.result()
                if response.success:
                    logger.info("Motor setup completed successfully")
                else:
                    logger.error(f"Motor setup failed: {response.message}")
                    raise RuntimeError(f"Motor setup failed: {response.message}")
            else:
                raise RuntimeError("Service call failed or timed out")

        except ImportError:
            raise RuntimeError("std_srvs not available. Install: pip install std-srvs")

    def disconnect(self) -> None:
        """Disconnect from ROS2 and clean up resources."""
        # Disconnect local cameras
        for camera in self.cameras.values():
            if camera.is_connected:
                camera.disconnect()

        # Clean up ROS subscriptions
        self._camera_subscribers.clear()
        self._latest_camera_images.clear()

        # Call parent disconnect
        super().disconnect()


# Type aliases for different SO models
SO100FollowerROS2: TypeAlias = SOFollowerROS2
SO101FollowerROS2: TypeAlias = SOFollowerROS2
