# SPDX-License-Identifier: MIT
# Adapted from Microsoft Research "xavier-tutorial" (GPU-offloading reference architecture).
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
ROS2 hardware bridge node for SO-100/101 Follower robots.

This node bridges ROS2 communication with the physical SO Follower robot hardware.

Usage:
    # Run with default parameters
    ros2 run lerobot so101_follower_bridge

    # Run with custom parameters
    ros2 run lerobot so101_follower_bridge \\
        --ros-args \\
        -p namespace:=/so101_follower \\
        -p port:=/dev/ttyUSB0 \\
        -p robot_id:=my_follower \\
        -p publish_rate:=50.0

    # Using launch file
    ros2 launch lerobot so101_follower_bridge.launch.py

Topics:
    Subscribed:
        - /{namespace}/action (sensor_msgs/JointState): Action commands
        - /{namespace}/calibration (std_msgs/Float64MultiArray): Calibration data

    Published:
        - /{namespace}/state (sensor_msgs/JointState): Current robot state
        - /{namespace}/status (std_msgs/String): Bridge status
"""

from __future__ import annotations

import logging

from lerobot.robots.ros_bridge.hardware_bridge import RobotHardwareBridge, main
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig

logger = logging.getLogger(__name__)


class SO101FollowerBridge(RobotHardwareBridge):
    """
    Hardware bridge for SO-101 Follower robot.

    This bridge connects ROS2 topics to the physical SO-101 Follower robot
    via the Feetech motor bus.
    """

    def __init__(self):
        super().__init__(node_name='so101_follower_bridge')

    def create_robot(self):
        """
        Create the SO-101 Follower robot instance.

        Returns:
            SO101Follower: Robot instance configured from ROS parameters
        """
        # Get parameters
        port = self.get_parameter('port').value
        robot_id = self.get_parameter('robot_id').value

        # Create config
        config = SO101FollowerConfig(
            port=port,
            id=robot_id,
        )

        self.get_logger().info(f"Creating SO101Follower with port={port}, id={robot_id}")

        # Create and return robot
        return SO101Follower(config)


class SO100FollowerBridge(SO101FollowerBridge):
    """Hardware bridge for SO-100 Follower robot (same as SO-101)."""

    def __init__(self):
        # Call grandparent __init__ with different node name
        RobotHardwareBridge.__init__(self, node_name='so100_follower_bridge')


def main_so101(args=None):
    """Entry point for SO-101 Follower bridge."""
    main(SO101FollowerBridge, args)


def main_so100(args=None):
    """Entry point for SO-100 Follower bridge."""
    main(SO100FollowerBridge, args)


if __name__ == '__main__':
    main_so101()
