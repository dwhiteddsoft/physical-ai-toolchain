# SPDX-License-Identifier: MIT
# Adapted from an upstream GPU-offloading reference implementation.

"""Utility functions for SO-101 robot control with LeRobot.

This module provides utilities for:
- Coordinate space conversion (physical degrees <-> motor-normalized degrees)
- Action clipping (safety constraints from dataset statistics)
- Camera initialization (waiting for ROS2 camera topics)
- Robot control helpers (reset to zero position)
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np
import torch

# ============================================================================
# Coordinate space conversion: physical degrees  <->  motor-normalized degrees
#
# WHY THIS IS NEEDED
# ------------------
# The VLA is trained in *motor-normalized* degree space. The ROS2 wire carries
# *physical* radians (SO101FollowerROS2 converts to degrees). Without conversion
# the VLA sees out-of-distribution observations, and the wrist_roll command only
# covers 62% of the real range (100/160).
#
# HOW IT IS APPLIED
# -----------------
# Before VLA:  raw_obs → physical_to_motor() → vla_obs
# After VLA:   action_motor → motor_to_physical() → physical action
# ============================================================================

# Physical joint limits (degrees) — from so101_follower.usd / URDF
PHYS_DEG = {
    'shoulder_pan.pos':  (-110.0, 110.0),
    'shoulder_lift.pos': (-100.0, 100.0),
    'elbow_flex.pos':    (-100.0,  90.0),
    'wrist_flex.pos':     (-95.0,  95.0),
    'wrist_roll.pos':   (-160.0, 160.0),
    'gripper.pos':        (-10.0, 100.0),
}

# Motor-normalized limits (degrees) — the space the VLA was trained in.
# Source: the SO101 follower motor-limit table from the training environment.
MOTOR_DEG = {
    'shoulder_pan.pos':  (-100.0, 100.0),
    'shoulder_lift.pos': (-100.0, 100.0),
    'elbow_flex.pos':    (-100.0, 100.0),
    'wrist_flex.pos':    (-100.0, 100.0),
    'wrist_roll.pos':    (-100.0, 100.0),
    'gripper.pos':          (0.0, 100.0),
}

# Gripper closing heuristic
# During training the gripper was blocked by the cube at ~8-9° motor — never
# fully closed.  The VLA targets ~8-9° motor at inference → physical ≈ -0.005 rad.
# Subtracting GRIPPER_CLOSE_OFFSET_DEG (motor space) before motor_to_physical()
# overshoots past the contact point so the gripper actually grips.
#   VLA=8.8° → offset=9° → motor=-0.2° → physical≈-10.2° → ≈-0.178 rad
GRIPPER_CLOSE_OFFSET_DEG: float = 9.0


def physical_to_motor(obs: dict) -> dict:
    """Convert physical degrees → motor-normalized degrees for VLA input.

    Only joint position keys (ending in '.pos') are remapped.  Camera images
    and any other values are passed through unchanged.
    """
    out = {}
    for key, value in obs.items():
        if key in PHYS_DEG and isinstance(value, (int, float)):
            p_min, p_max = PHYS_DEG[key]
            m_min, m_max = MOTOR_DEG[key]
            out[key] = (value - p_min) / (p_max - p_min) * (m_max - m_min) + m_min
        else:
            out[key] = value
    return out


def motor_to_physical(action: dict) -> dict:
    """Convert motor-normalized degrees → physical degrees for robot command.

    Inverse of physical_to_motor().
    """
    out = {}
    for key, value in action.items():
        if key in PHYS_DEG and isinstance(value, (int, float)):
            p_min, p_max = PHYS_DEG[key]
            m_min, m_max = MOTOR_DEG[key]
            out[key] = (value - m_min) / (m_max - m_min) * (p_max - p_min) + p_min
        else:
            out[key] = value
    return out


def apply_robot_heuristics(action: dict, gripper_offset: float = GRIPPER_CLOSE_OFFSET_DEG) -> dict:
    """Apply SO-101-specific heuristics to a motor-space action dict.

    Currently applies the gripper closing heuristic: subtract ``gripper_offset``
    (motor-normalized degrees) from the gripper command so the VLA's learned
    "almost closed" target actually closes past the contact point.

    Call this *after* clip_actions and *before* motor_to_physical.

    Args:
        action: Dict of joint_name → motor-normalized degree value.
        gripper_offset: Degrees to subtract from gripper.pos (default:
            GRIPPER_CLOSE_OFFSET_DEG = 9.0).

    Returns:
        A new dict with heuristics applied.
    """
    out = dict(action)
    if gripper_offset != 0.0 and 'gripper.pos' in out:
        out['gripper.pos'] -= gripper_offset
    return out


# ============================================================================
# Robot Control Helpers
# ============================================================================


def return_to_zero_position(robot, robot_cfg, sleep_after=None):
    """Send a command to return all joints to zero position (home position).

    Uses the canonical zero position for SO-101 from the training home state.
    These values match what the robot reports when it is at rest.

    Zero position (in radians):
    - elbow_flex: 0.0108 rad (≈0.62°)
    - wrist_flex: 0.0016 rad (≈0.09°)
    - shoulder_lift: 0.0 rad
    - wrist_roll: 0.0 rad
    - shoulder_pan: 0.0 rad
    - gripper: -0.0004 rad (≈-0.02°)

    Args:
        robot: Robot interface with send_action() method
        robot_cfg: Robot configuration containing joint information
        sleep_after: Optional seconds to sleep after sending command
    """
    import math

    # Zero position values in radians (from the training home state)
    zero_positions_rad = {
        'elbow_flex': 0.0108,
        'wrist_flex': 0.0016,
        'shoulder_lift': 0.0,
        'wrist_roll': 0.0,
        'shoulder_pan': 0.0,
        'gripper': -0.0004,
    }

    # Check if we need to convert to degrees
    use_degrees = getattr(robot_cfg, 'use_degrees', False)

    # Construct zero action dict
    zero_action = {}
    for joint, rad_value in zero_positions_rad.items():
        key = f'{joint}.pos'
        if use_degrees:
            # Convert radians to degrees for the robot interface
            zero_action[key] = math.degrees(rad_value)
        else:
            zero_action[key] = rad_value

    robot.send_action(zero_action)
    print(f"   🏠 Sent return to zero position command ({'degrees' if use_degrees else 'radians'})")

    if sleep_after is not None:
        print(f"   ⏳ Sleeping for {sleep_after} seconds to allow robot to reach position...")
        time.sleep(sleep_after)


def clip_action(
    action: dict,
    clip_to_limits: bool = True,
) -> dict:
    """Optionally clip absolute joint position commands to physical joint limits.

    Args:
        action:          {'{joint}.pos': float}  in physical degrees
        clip_to_limits:  whether to clip values to URDF joint limits

    Returns:
        Action dict in physical degrees, clipped if requested.
    """
    if not clip_to_limits:
        return action

    # SO-101 joint limits in degrees (from URDF / so101_follower.usd)
    JOINT_LIMITS_DEG = {
        'shoulder_pan.pos':  (-110.0, 110.0),
        'shoulder_lift.pos': (-100.0, 100.0),
        'elbow_flex.pos':     (-96.8,  96.8),
        'wrist_flex.pos':     (-95.0,  95.0),
        'wrist_roll.pos':   (-157.2, 162.8),
        'gripper.pos':        (-10.0, 100.0),
    }

    out = {}
    for key, val in action.items():
        if key in JOINT_LIMITS_DEG:
            lo, hi = JOINT_LIMITS_DEG[key]
            out[key] = max(lo, min(hi, val))
        else:
            out[key] = val
    return out


# ============================================================================
# Action Clipping Utilities
# ============================================================================

def load_action_clip_bounds(
    dataset_repo_id: str,
    cache_root: str | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Load action min/max from a LeRobot dataset's stats.json.

    Returns (clip_min, clip_max) as float32 numpy arrays.
    Falls back to +/-inf (no clipping) if stats.json is missing or malformed.
    """
    if cache_root is None:
        cache_root = os.path.join(
            os.path.expanduser("~"), ".cache", "huggingface", "lerobot"
        )

    stats_path = Path(cache_root) / dataset_repo_id / "meta" / "stats.json"
    if not stats_path.exists():
        print(
            f"[WARN] stats.json not found at {stats_path} — action clipping disabled."
        )
        return None, None

    with open(stats_path) as f:
        stats = json.load(f)

    action_stats = stats.get("action")
    if action_stats is None or "min" not in action_stats or "max" not in action_stats:
        print(f"[WARN] No action min/max in {stats_path} — action clipping disabled.")
        return None, None

    clip_min = np.array(action_stats["min"], dtype=np.float32)
    clip_max = np.array(action_stats["max"], dtype=np.float32)
    print(
        f"[INFO] Loaded action clip bounds from {stats_path}\n"
        f"       dims={len(clip_min)}, min={clip_min.tolist()}, max={clip_max.tolist()}"
    )
    return clip_min, clip_max


def clip_actions(
    action_deltas,
    action_clip_min: np.ndarray,
    action_clip_max: np.ndarray,
    device: torch.device,
    step: int = 0,
    verbose: bool = True,
):
    """Clip action deltas to training data range.

    This ensures the array order matches stats.json order by clipping before
    converting to a dict via make_robot_action().

    Args:
        action_deltas: Output from policy (tensor or dict with "action" key)
        action_clip_min: Minimum action values from dataset stats
        action_clip_max: Maximum action values from dataset stats
        device: Torch device for tensors
        step: Current step number (for logging)
        verbose: Whether to print clipping details

    Returns:
        Clipped action_deltas in the same format as input
    """
    if action_clip_min is None:
        return action_deltas

    # Extract the action tensor/array
    if isinstance(action_deltas, dict):
        action_array = action_deltas["action"]
    else:
        action_array = action_deltas

    # Convert to numpy if needed
    if isinstance(action_array, torch.Tensor):
        action_array = action_array.cpu().numpy()
    else:
        action_array = np.array(action_array)

    # Remove batch dim if present: [1, 8] -> [8]
    if action_array.ndim == 2 and action_array.shape[0] == 1:
        action_array = action_array.squeeze(0)

    # Store original values for logging
    action_before_clip = action_array.copy()

    # Clip to dataset bounds
    action_array = np.clip(action_array, action_clip_min, action_clip_max)

    # Convert back to tensor with batch dimension and put back in the same format
    action_tensor = torch.from_numpy(action_array).float().unsqueeze(0).to(device)
    if isinstance(action_deltas, dict):
        action_deltas["action"] = action_tensor
    else:
        action_deltas = action_tensor

    return action_deltas


# ============================================================================
# Camera Initialization Utilities
# ============================================================================

def wait_for_cameras(
    robot,
    camera_keys: list[str],
    max_wait_seconds: float = 150,
    check_interval: float = 1.0,
) -> bool:
    """Wait for all camera topics to publish data.

    ROS2 subscribers need time to receive first messages after connecting.
    This function polls the robot's observation until all expected cameras
    have published at least one frame.

    Args:
        robot: Robot interface with get_observation() method
        camera_keys: List of camera names to wait for (e.g., ['front', 'wrist'])
        max_wait_seconds: Maximum time to wait before timing out
        check_interval: How often to check for camera data (seconds)

    Returns:
        True if all cameras are ready, False if timeout occurred
    """
    print("\n" + "="*60)
    print("Waiting for camera data from ROS2 topics...")
    print("="*60)

    start_time = time.time()

    while True:
        obs = robot.get_observation()
        available_cameras = [k for k in camera_keys if obs.get(k) is not None]
        missing_cameras = [k for k in camera_keys if obs.get(k) is None]

        if all(obs.get(key) is not None for key in camera_keys):
            print(f"✅ All cameras ready! ({', '.join(camera_keys)})")
            return True

        elapsed = time.time() - start_time
        if elapsed > max_wait_seconds:
            print(f"\n❌ Timeout waiting for cameras after {max_wait_seconds}s")
            print(f"   Available: {available_cameras}")
            print(f"   Missing: {missing_cameras}")
            return False

        print(f"⏳ Waiting... ({len(available_cameras)}/{len(camera_keys)} cameras) - {missing_cameras}")
        time.sleep(check_interval)
