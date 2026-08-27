# SPDX-License-Identifier: MIT
#
# UR10e observation and command seam for the pi05 offload example.
#
# This file is the hardware boundary and is reference material: replace `RobotBridge`
# with the integration you already run at the robot site (ROS 2 topics, RTDE, or the
# Physical-AI-Operator follower node). Nothing here is offloaded — it executes in the
# control container next to the robot.
from __future__ import annotations

import os

# cspell:ignore imencode

JOINT_COUNT = 6

# The checkpoint was trained on 6 joint positions plus one gripper value, and emits an
# action of the same width. lerobot pads the vector to the model's 32-wide state slot.
STATE_DIM = JOINT_COUNT + 1


class RobotBridge:
    """Read observations from and write commands to a UR10e.

    The control loop needs three things per cycle: joint positions in the training
    order, one JPEG frame per training camera, and a way to apply the predicted
    action. Implement those three methods against your own robot stack.
    """

    def __init__(self, cameras: list[str], *, dry_run: bool = False, enable_motion: bool = False) -> None:
        self.cameras = cameras
        self.dry_run = dry_run
        self.enable_motion = enable_motion

    @classmethod
    def from_env(cls) -> RobotBridge:
        cameras = [name.strip() for name in os.environ.get("PI05_CAMERAS", "scene,wrist").split(",") if name.strip()]
        return cls(
            cameras,
            dry_run=os.environ.get("PI05_DRY_RUN", "false").lower() == "true",
            enable_motion=os.environ.get("PI05_ENABLE_MOTION", "false").lower() == "true",
        )

    def read_state(self) -> list[float]:
        """Current joint positions plus gripper, ordered exactly as in the training dataset."""
        if self.dry_run:
            return [0.0] * STATE_DIM
        raise NotImplementedError("connect read_state to the UR10e joint-state source")

    def read_frames(self) -> dict[str, bytes]:
        """One JPEG-encoded RGB frame per camera, keyed by the training camera name.

        JPEG keeps each cycle inside the 8 MiB codec message limit; raw 224x224x3
        buffers would also fit, but wrist and scene cameras deliver larger frames.
        """
        if self.dry_run:
            return {name: _blank_jpeg() for name in self.cameras}
        raise NotImplementedError("connect read_frames to the scene and wrist cameras")

    def send_action(self, action: list[float]) -> None:
        """Apply one action: absolute joint targets plus an optional gripper command."""
        if not self.enable_motion or self.dry_run:
            return
        raise NotImplementedError("connect send_action to the UR10e joint-target interface")


def _blank_jpeg(width: int = 224, height: int = 224) -> bytes:
    import cv2
    import numpy as np

    ok, encoded = cv2.imencode(".jpg", np.zeros((height, width, 3), dtype=np.uint8))
    if not ok:
        raise RuntimeError("failed to encode the placeholder frame")
    return encoded.tobytes()
