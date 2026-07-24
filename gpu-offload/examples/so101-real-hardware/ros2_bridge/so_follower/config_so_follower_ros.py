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

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from ..config import RobotConfig
from .config_so_follower import SOFollowerConfig


@dataclass
class SOFollowerConfigROS(SOFollowerConfig):
    """Configuration class for SO Follower robots with ROS2 support.

    Extends SOFollowerConfig with ROS2-specific parameters for custom topic names.
    This allows the robot to connect to different ROS2 topic structures (e.g., a
    simulator, hardware bridge, etc.) without code changes.

    Example:
        # Connect to a simulator's standard topics
        config = SOFollowerConfigROS(
            port="/dev/ttyUSB0",  # Ignored by ROS2
            id="my_robot",
            ros_state_topic="/joint_states",
            ros_action_topic="/joint_command"
        )

        # Connect to hardware bridge's namespaced topics
        config = SOFollowerConfigROS(
            port="/dev/ttyUSB0",
            id="my_robot",
            ros_state_topic="/my_robot/state",
            ros_action_topic="/my_robot/action"
        )
    """

    # ROS2-specific configuration
    # Topic name for robot state observations (default: /{id}/state)
    ros_state_topic: str | None = None

    # Topic name for robot action commands (default: /{id}/action)
    ros_action_topic: str | None = None

    # Topic name for calibration data (default: /{id}/calibration)
    ros_calibration_topic: str | None = None

    # ROS2 camera topic names (key=camera_name, value=topic_name)
    # Example: {"front": "/camera/front/image_raw", "left": "/camera/left/image_raw"}
    ros_camera_topics: dict[str, str] | None = None


@RobotConfig.register_subclass("so101_follower_ros2")
@RobotConfig.register_subclass("so100_follower_ros2")
@dataclass
class SOFollowerRobotConfigROS(RobotConfig, SOFollowerConfigROS):
    """ROS2-enabled SO Follower robot configuration for RobotConfig registry."""
    pass


# Type aliases for convenience
SO100FollowerConfigROS: TypeAlias = SOFollowerRobotConfigROS
SO101FollowerConfigROS: TypeAlias = SOFollowerRobotConfigROS
