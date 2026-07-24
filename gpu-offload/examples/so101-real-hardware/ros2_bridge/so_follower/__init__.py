# SPDX-License-Identifier: MIT
# Adapted from an upstream GPU-offloading reference implementation.

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

# This __init__ exposes only the ROS2 variants of the SO-follower config and robot.
# The base LeRobot exports (SO100Follower, SO101Follower, and their configs) are provided
# by the upstream lerobot package and are intentionally not re-exported here.

from __future__ import annotations

# ROS2 variants (optional - only available if ROS2 dependencies are installed)
try:
    from .config_so_follower_ros import (
        SO100FollowerConfigROS,
        SO101FollowerConfigROS,
        SOFollowerConfigROS,
        SOFollowerRobotConfigROS,
    )
    from .so_follower_ros2 import (
        SO100FollowerROS2,
        SO101FollowerROS2,
        SOFollowerROS2,
    )

    _ROS2_EXPORTS = [
        "SO100FollowerConfigROS",
        "SO101FollowerConfigROS",
        "SOFollowerConfigROS",
        "SOFollowerRobotConfigROS",
        "SO100FollowerROS2",
        "SO101FollowerROS2",
        "SOFollowerROS2",
    ]
except ImportError:
    # ROS2 not available - ROS2 variants will not be exported
    _ROS2_EXPORTS = []

__all__ = [*_ROS2_EXPORTS]
