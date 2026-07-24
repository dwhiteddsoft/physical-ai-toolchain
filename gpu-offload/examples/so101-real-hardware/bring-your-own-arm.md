# Bring your own arm to the ROS2 bridge

Adapt the ROS2 hardware-bridge pattern to any motor-driven arm. The SO101 follower is
the worked example throughout; the pattern itself is embodiment-agnostic.

## Overview

The ROS2 bridge splits a robot into two processes that meet only at a set of ROS2
topics. The client side implements the LeRobot `Robot` interface but publishes and
subscribes over topics instead of driving a motor bus directly. The bridge side owns
the physical hardware: it subscribes to action commands, forwards them to the motor
bus or driver, and republishes measured state.

Because the control loop reads and writes topics — never the hardware — the loop is
identical for every arm. Swapping arms means supplying a new bridge and a new config;
the control loop connects unchanged. A new arm is a new bridge plus a config, not a
new control loop.

```text
┌──────────────────┐      ROS2 topics       ┌──────────────────┐
│  ROS2MotorRobot  │  ───── action ──────►  │ RobotHardware    │
│  (control loop)  │  ◄──── state ───────   │ Bridge (hardware)│
└──────────────────┘                        └──────────────────┘
        │  same Robot interface                    │  your motor bus / driver
        ▼                                           ▼
  policy + action call                        physical arm
```

## Steps to add an arm

Perform these steps in order. Steps 1 and 2 define the two processes; steps 3 and 4
wire them together.

1. Subclass `ROS2MotorRobot`. Set `MOTOR_NAMES` to your arm's joints in the exact
   order the motor bus and policy expect, and return that list from
   `_get_motor_names()`. The base class maps each name to a `<name>.pos` observation
   and action key and handles the radian/degree conversion, so joint order is the one
   contract you own here.

   ```python
   from __future__ import annotations

   from lerobot.robots.robot_ros2 import ROS2MotorRobot

   from .config_your_arm_ros import YourArmConfigROS


   class YourArmROS2(ROS2MotorRobot):
       config_class = YourArmConfigROS
       name = "your_arm_ros2"

       # SO101 worked example uses this six-joint order:
       #   shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper
       MOTOR_NAMES = [
           "joint_1",
           "joint_2",
           "gripper",
       ]

       def _get_motor_names(self) -> list[str]:
           return self.MOTOR_NAMES
   ```

2. Subclass `RobotHardwareBridge`. Implement `create_robot()` to build and return a
   hardware-connected robot instance for your motor bus or driver. Set the publish
   rate to a value your hardware sustains — the SO101 bridge runs at 50 Hz via the
   `publish_rate` parameter. The base class owns the publishers, subscribers, and QoS;
   `create_robot()` is the only method you must supply.

   ```python
   from __future__ import annotations

   from lerobot.robots.ros_bridge.hardware_bridge import RobotHardwareBridge, main

   from lerobot.robots.your_arm import YourArm, YourArmConfig


   class YourArmBridge(RobotHardwareBridge):
       def __init__(self) -> None:
           super().__init__(node_name="your_arm_bridge")

       def create_robot(self) -> YourArm:
           port = self.get_parameter("port").value
           robot_id = self.get_parameter("robot_id").value
           return YourArm(YourArmConfig(port=port, id=robot_id))


   def main_your_arm(args=None) -> None:
       main(YourArmBridge, args)
   ```

3. Provide a config module analogous to `config_so_follower_ros.py`. Extend your arm's
   base config with the ROS2 topic overrides so the client can target either a
   namespaced bridge or a different topic layout without code changes.

   ```python
   from __future__ import annotations

   from dataclasses import dataclass

   from .config_your_arm import YourArmConfig


   @dataclass
   class YourArmConfigROS(YourArmConfig):
       ros_state_topic: str | None = None
       ros_action_topic: str | None = None
       ros_calibration_topic: str | None = None
       ros_camera_topics: dict[str, str] | None = None
   ```

4. Match the ROS2 topic names so the existing control loop connects unchanged. The
   bridge publishes and subscribes under a namespace; point the client config at the
   same namespace or the same explicit topic names. With the names aligned, the
   control loop from the SO101 worked example runs against your arm with no edits.

   | Direction            | Topic                      | Message type                 |
   |----------------------|----------------------------|------------------------------|
   | Published by bridge  | `/{namespace}/state`       | `sensor_msgs/JointState`     |
   | Published by bridge  | `/{namespace}/status`      | `std_msgs/String`            |
   | Subscribed by bridge | `/{namespace}/action`      | `sensor_msgs/JointState`     |
   | Subscribed by bridge | `/{namespace}/calibration` | `std_msgs/Float64MultiArray` |

## Checklist

Create the following for a new arm. The SO101 files named under "Worked example" are
the reference implementations to generalize from; see [README.md](./README.md).

| File to create                  | Base to subclass       | What to fill in                                  | Worked example              |
|---------------------------------|------------------------|--------------------------------------------------|-----------------------------|
| `your_arm_ros2.py`              | `ROS2MotorRobot`       | `MOTOR_NAMES`, joint order, `_get_motor_names()` | `so_follower_ros2.py`       |
| `ros_bridge/your_arm_bridge.py` | `RobotHardwareBridge`  | `create_robot()`, publish rate, motor bus/driver | `so_follower_bridge.py`     |
| `config_your_arm_ros.py`        | your arm's base config | ROS2 topic overrides                             | `config_so_follower_ros.py` |
| — (config only)                 | —                      | Matching namespace / topic names                 | —                           |

## Offload boundary

The offload boundary is the policy call, not the arm. Offloading transports the
`get_action` (checkpoint inference) call to a GPU server stage; the ROS2 topics, the
bridge, and the motor bus stay local to the control loop. Changing the arm changes the
bridge and config only — it does not change what is offloaded or how. The offload
contract is defined entirely by the policy call and is identical across arms.

See [gpu-offload.specification.md](../../specifications/gpu-offload.specification.md)
for the opt-in offload contract that the policy call participates in.

## Safety

> [!WARNING]
> The control-loop rate (commonly 15–50 Hz) sets a hard budget for every operation
> inside the loop. Offloading the policy call to another machine injects network
> latency and jitter into that budget and can destabilize closed-loop control. Keep
> the offload server stage on the same node for closed-loop control, validate any
> cross-machine offload against your rate budget, and always test on hardware with a
> reachable e-stop before running autonomously.

## Validation status

The examples in this directory are authored and lint-validated. They are not
runtime-verified by this repository: it carries neither the prebuilt offloading images
nor a physical arm. Treat every command and code snippet as a reference to adapt and
verify on your own hardware.

---

> This reference architecture originates with the Microsoft Research Xavier team, whose
> `xavier-tutorial` project defined the transparent GPU-offloading contract and
> deployment topology adapted here. This repository carries the consumer-facing contract
> and deployment scaffolding only; the offloading engine ships as prebuilt external
> images.
