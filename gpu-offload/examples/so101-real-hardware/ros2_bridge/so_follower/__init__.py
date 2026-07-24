# SPDX-License-Identifier: MIT
# Adapted from Microsoft Research "xavier-tutorial" (GPU-offloading reference architecture).

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

# NOTE (vendored, partial): This __init__ reproduces ONLY the ROS2 export block that
# the upstream xavier-tutorial patch added to lerobot's so_follower package __init__.
# The original upstream exports (SO100Follower, SO101Follower, and their configs) are
# NOT reproduced here because they belong to unmodified upstream LeRobot. See
# CARRY-DECISION.md for the full provenance and reconstruction notes.

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
