# SPDX-License-Identifier: MIT
# Adapted from an upstream GPU-offloading reference implementation.

"""Run a SmolVLA policy for real SO-101 hardware control via ROS2.

This script runs a trained SmolVLA policy to control a physical SO-101 arm over
ROS2 topics. It is topic-source-agnostic: it reads joint-state and camera
observations from ROS2 topics and publishes joint commands back, without knowing
what produces those topics. On real hardware the operator runs the
``hardware_bridge`` node (see ROS2_README.md) against the physical arm; the bridge
owns the motor bus and enforces its own safety limits.

The policy's action-selection call is the GPU **offload boundary**: it is the
class/method that ``remote.yaml`` maps to a GPU server stage, so the call can be
transparently redirected to a remote GPU without changing this loop. See the
offload contract:
``../../../../../specifications/gpu-offload.specification.md``.

> [!WARNING]
> Offloading the policy call across machines injects network latency and jitter
> into the control loop. SmolVLA inference already caps this loop near 2.5 Hz, and
> a closed-loop arm is sensitive to added delay. Prefer **same-node** offload
> (policy GPU co-located with the control host) for closed-loop control. Only use
> cross-machine offload with an operator-supervised, latency-bounded setup and a
> watchdog that halts the arm if actions arrive late.

Coordinate space conversion (motor-normalized vs physical degrees)
------------------------------------------------------------------
The VLA was trained in *motor-normalized* degree space. For example, wrist_roll
is normalized to ±100° even though the physical joint travels ±160°. The ROS2
robot abstraction returns/consumes *physical* degrees (converted from the radians
on the wire when use_degrees=True). Feeding physical degrees straight to the VLA
would present out-of-distribution values, and the wrist_roll command would only
cover 62% of the real range (100/160), so the gripper would never rotate far
enough to be square to the target. Fix: convert physical → motor-normalized before
the VLA, then convert the VLA's motor-normalized output → physical before sending
to the robot. See physical_to_motor() / motor_to_physical() in utils.py.

Usage:
    # Run with defaults
    python run_vla.py

    # Custom model and control rate
    python run_vla.py --model-id /path/to/model --fps 30

    # See all options
    python run_vla.py --help
"""

from __future__ import annotations

import argparse
import os
import time

import torch
from lerobot.datasets.utils import hw_to_dataset_features
from lerobot.policies.factory import make_pre_post_processors
from lerobot.policies.smolvla.modeling_smolvla import SmolVLAPolicy
from lerobot.policies.utils import build_inference_frame, make_robot_action
from lerobot.robots.so_follower import SO101FollowerConfigROS, SO101FollowerROS2

# Import utility functions
from utils import (
    GRIPPER_CLOSE_OFFSET_DEG,
    apply_robot_heuristics,
    clip_action,
    clip_actions,
    load_action_clip_bounds,
    motor_to_physical,
    physical_to_motor,
    wait_for_cameras,
)

# Default values
# The default checkpoint path uses a "<run-id>" placeholder. Provide the real checkpoint
# via the MODEL_ID environment variable or --model-id.
DEFAULT_MODEL_ID = os.environ.get(
    "MODEL_ID",
    "/data/smolvla_lift_cube_abs_joint/<run-id>/checkpoints/010000/pretrained_model"
)
DEFAULT_DATASET_REPO_ID = os.environ.get("DATASET_REPO_ID", "local/lift_cube_abs_joint")
DEFAULT_STEPS = 5000000000   # run forever
DEFAULT_FPS = 10  # VLA model inference takes ~0.4s, so realistic max is ~2.5 Hz
DEFAULT_CAMERA_TIMEOUT = 150


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run SmolVLA model for SO-101 robot control via ROS2",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Model and dataset
    parser.add_argument(
        "--model-id",
        type=str,
        default=DEFAULT_MODEL_ID,
        help="Path to the trained model checkpoint"
    )
    parser.add_argument(
        "--dataset-repo-id",
        type=str,
        default=DEFAULT_DATASET_REPO_ID,
        help="LeRobot dataset repo ID for loading action clip bounds"
    )

    # Control parameters
    parser.add_argument(
        "--steps",
        type=int,
        default=DEFAULT_STEPS,
        help="Maximum steps per episode"
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=DEFAULT_FPS,
        help="Control loop frequency (Hz)"
    )

    # Robot behavior
    parser.add_argument(
        "--no-joint-limit-clipping",
        action="store_true",
        help="Disable clipping actions to joint limits from URDF"
    )
    parser.add_argument(
        "--no-action-clipping",
        action="store_true",
        help="Disable clipping action deltas to dataset bounds"
    )
    parser.add_argument(
        "--gripper-offset",
        type=float,
        default=GRIPPER_CLOSE_OFFSET_DEG,
        help="Motor-space degrees subtracted from the gripper command to overshoot "
             "the contact point the VLA learned on (0 to disable)"
    )

    # Camera and timeouts
    parser.add_argument(
        "--camera-timeout",
        type=int,
        default=DEFAULT_CAMERA_TIMEOUT,
        help="Maximum seconds to wait for camera data"
    )

    # Device
    parser.add_argument(
        "--device",
        type=str,
        default="cuda",
        choices=["cuda", "cpu", "mps"],
        help="Torch device to use"
    )

    return parser.parse_args()


def main():
    try:

        args = parse_args()

        device = torch.device(args.device)

        # Path to your local trained model checkpoint
        model_id = args.model_id

        model = SmolVLAPolicy.from_pretrained(model_id)

        # Load action clip bounds
        dataset_repo_id = args.dataset_repo_id
        action_clip_min, action_clip_max = load_action_clip_bounds(
            dataset_repo_id, cache_root=os.getenv("HF_LEROBOT_HOME")
        )

        print("✅ Model and action clip bounds loaded successfully")
        print("   Model ID:", model_id)
        print("   Dataset Repo ID:", dataset_repo_id)

        preprocess, postprocess = make_pre_post_processors(
            model.config,
            model_id,
            preprocessor_overrides={"device_processor": {"device": str(device)}},
        )

        # Robot configuration.
        # This loop is topic-source-agnostic. For real hardware, point these topic
        # names at the hardware_bridge node (ROS2_README.md), which publishes robot
        # state and subscribes to action commands under its ROS2 namespace.
        # use_degrees=True tells SO101FollowerROS2 to:
        #   • convert incoming radians (robot state) to degrees before returning them
        #   • convert outgoing degrees back to radians before publishing commands
        # This keeps all in-Python arithmetic in degrees, matching the dataset.
        robot_cfg = SO101FollowerConfigROS(
            port="/dev/ttyUSB0",  # Ignored by the ROS2 path; the bridge owns the bus
            id="so_follower_ros2",
            use_degrees=True,
            max_relative_target=10.0,  # Safety clamp: limits each action step to ±10° max
            disable_torque_on_disconnect=True,

            # Match the topics published/subscribed by the hardware_bridge node.
            # Default bridge topics are /{namespace}/state and /{namespace}/action;
            # the quick-start namespace in ROS2_README.md is /so101_follower.
            ros_state_topic="/so101_follower/state",   # bridge publishes joint state here
            ros_action_topic="/so101_follower/action",  # bridge subscribes to commands here

            # > [!NOTE]
            # Integrator: the hardware_bridge base node does not publish camera
            # feeds. Supply your own ROS2 camera driver topics (e.g. usb_cam,
            # realsense2_camera) below; the names here are placeholders.
            ros_camera_topics={
                "front": "/camera/front/image_raw",
                "wrist": "/camera/wrist/image_raw"
            }
        )

        robot_type = "so101_follower"
        robot = SO101FollowerROS2(robot_cfg)
        robot.connect()

        task = "Pick up the red cube"

        # This is used to match the raw observation keys to the keys expected by the policy
        action_features = hw_to_dataset_features(robot.action_features, "action")
        obs_features = hw_to_dataset_features(robot.observation_features, "observation")
        dataset_features = {**action_features, **obs_features}

        # Wait for camera data to be available (ROS2 subscribers need time to receive first messages)
        camera_keys = list(robot_cfg.ros_camera_topics.keys())
        if not wait_for_cameras(robot, camera_keys, max_wait_seconds=args.camera_timeout):
            return  # Timeout - exit gracefully

        print("\n" + "="*60)
        print("Starting inference loop...")
        print("="*60 + "\n")

        # Control loop frequency (Hz) - matches typical robot control rates
        control_fps = args.fps
        dt = 1.0 / control_fps

        for step in range(args.steps):
            step_start = time.time()

            # raw_obs contains physical degrees (converted from radians by SO101FollowerROS2)
            raw_obs = robot.get_observation()

            # Remap joint positions from physical degrees to motor-normalized degrees.
            # The VLA was trained in motor-normalized degree space, so we must
            # present observations in that same space.  Camera images are unchanged.
            # Example: wrist_roll physical=80° → motor=50° (÷1.6 scale)
            vla_obs = physical_to_motor(raw_obs)

            # Verify we still have camera data
            if any(raw_obs.get(key) is None for key in camera_keys):
                print(f"⚠️  Warning: Lost camera data at step {step + 1}")
                continue

            # Build the tensor observation dict expected by the policy
            obs_frame = build_inference_frame(
                observation=vla_obs, ds_features=dataset_features, device=device, task=task, robot_type=robot_type
            )

            obs = preprocess(obs_frame)

            # ── GPU OFFLOAD BOUNDARY ──────────────────────────────────────────
            # model.select_action is the policy inference call. Under the offload
            # contract this is the class/method that remote.yaml maps to a GPU
            # server stage (a remoteclass / remotefunc), so the call can be
            # transparently redirected to a remote GPU without changing this loop.
            # Contract: ../../../../../specifications/gpu-offload.specification.md
            # See the module-level WARNING: prefer same-node offload for this
            # closed-loop path.
            # Model outputs absolute joint positions in motor-normalized degrees.
            action_motor = model.select_action(obs)
            action_motor = postprocess(action_motor)

            # Clip to the min/max seen during training (from dataset stats.json).
            # This prevents the model from commanding values it was never trained on,
            # which can cause jerky or unsafe movements, especially during early steps
            # when the model is uncertain.
            if not args.no_action_clipping:
                action_motor = clip_actions(
                    action_motor, action_clip_min, action_clip_max, device, step=step
                )

            # Reformat the flat action tensor into a {joint_name: value} dict
            action_motor = make_robot_action(action_motor, dataset_features)

            # Apply SO-101-specific heuristics (e.g. gripper closing offset)
            action_motor = apply_robot_heuristics(action_motor, gripper_offset=args.gripper_offset)

            # Convert motor-normalized degrees → physical degrees for the robot
            # Example: wrist_roll motor=50° -> physical=80° (1.6x scale)
            action_phys = motor_to_physical(action_motor)

            # Clip to URDF physical joint limits (degrees)
            action = clip_action(
                action_phys,
                clip_to_limits=(not args.no_joint_limit_clipping),
            )

            if step % 10 == 0:
                joint_str = "  ".join(
                    f"{j}={raw_obs.get(f'{j}.pos', 0.0):6.1f}°" for j in [
                        "shoulder_pan", "shoulder_lift", "elbow_flex",
                        "wrist_flex", "wrist_roll", "gripper"
                    ]
                )
                print(f"  Step {step + 1}/{args.steps}  |  {joint_str}")

            # Maintain consistent control frequency
            elapsed = time.time() - step_start
            sleep_time = dt - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

            robot.send_action(action)

    finally:
        print("\n" + "="*60)
        print("Shutting down gracefully...")
        print("="*60)
        try:
            robot.disconnect()
        except Exception as e:
            print(f"Warning during disconnect: {e}")
        print("✅ Shutdown complete")


if __name__ == "__main__":
    main()
