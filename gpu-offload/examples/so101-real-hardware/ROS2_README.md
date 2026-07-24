# ROS2 Robot Implementation Guide

This directory contains ROS2-based implementations of LeRobot robots that communicate via ROS2 topics/actions instead of direct hardware bus connections.

> [!IMPORTANT]
> This example is **authored and lint-validated, NOT runtime-verified.** We have neither
> the prebuilt GPU-offload platform images nor a physical SO-101 arm, so no end-to-end run,
> screenshots, or captures exist. Treat every command below as a reference to adapt, not a
> validated recipe. The real-hardware control loop lives in
> `ros2_bridge/examples/so101_ros/run_vla.py`; it is topic-source-agnostic and drives the
> arm entirely through the `hardware_bridge` node — no simulator is involved.

<!-- -->

> [!WARNING]
> The policy inference call in `run_vla.py` is the GPU **offload boundary** (see
> `../../specifications/gpu-offload.specification.md`). Offloading it across machines injects
> network latency and jitter into a closed-loop control path. SmolVLA inference already caps
> the loop near 2.5 Hz, and an arm is sensitive to added delay. Prefer **same-node** offload
> (policy GPU co-located with the control host) for closed-loop control. Only use
> cross-machine offload with an operator-supervised, latency-bounded setup and a watchdog
> that halts the arm if actions arrive late.

## Architecture Overview

The ROS2 robot architecture consists of two main components:

```text
┌─────────────────┐         ROS2 Topics          ┌──────────────────┐
│                 │    ────────────────────►      │                  │
│  ROS2Robot      │                               │ Hardware Bridge  │
│  (Client Side)  │    ◄────────────────────      │  (Hardware Side) │
│                 │                               │                  │
└─────────────────┘                               └──────────────────┘
        │                                                  │
        │ Implements Robot API                            │ Uses Motor Bus
        │ (EXACT SAME INTERFACE)                          │
        ▼                                                  ▼
  Application Code                                  Physical Robot
```

### Components

1. **ROS2Robot** (`robot_ros2.py`): Base abstract class that implements the Robot interface but communicates via ROS2
2. **Concrete ROS2 Implementations** (e.g., `so_follower_ros2.py`): Specific robot implementations
3. **Hardware Bridge Node** (`ros_bridge/hardware_bridge.py`): Base class for bridge nodes
4. **Specific Bridge Nodes** (e.g., `ros_bridge/so_follower_bridge.py`): Hardware-specific bridges

## Key Feature: Identical Interface

**The ROS2 robots have the EXACT SAME interface as direct hardware robots!**

```python
# Direct hardware version
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
robot = SO101Follower(SO101FollowerConfig(port="/dev/ttyUSB0", id="robot"))
robot.connect()
robot.setup_motors()      # Interactive setup
robot.calibrate()         # Calibration
obs = robot.get_observation()
robot.send_action(action)

# ROS2 version - SAME INTERFACE!
from lerobot.robots.so_follower import SO101FollowerROS2, SO101FollowerConfig
robot = SO101FollowerROS2(SO101FollowerConfig(ros_namespace="/robot", id="robot"))
robot.connect()
robot.setup_motors()      # ✅ Same method! (triggers on bridge)
robot.calibrate()         # ✅ Same method! (handled by bridge)
obs = robot.get_observation()  # ✅ Same method!
robot.send_action(action)      # ✅ Same method!
```

## Benefits

- **Decoupling**: Separate application logic from hardware communication
- **Flexibility**: Run application and hardware on different machines
- **Safety**: Hardware bridge can enforce safety limits independently
- **Multi-client**: Multiple applications can observe robot state
- **Recording**: Easy to record/replay using ROS2 bag files
- **Visualization**: Use ROS2 tools (RViz, PlotJuggler) for debugging

## Quick Start

### 1. Install ROS2 Dependencies

```bash
pip install rclpy sensor-msgs std-msgs cv-bridge
```

### 2. Start Hardware Bridge

On the machine connected to the robot:

```bash
# For SO-101 Follower
python3 -m lerobot.robots.ros_bridge.so_follower_bridge \
    --ros-args \
    -p namespace:=/so101_follower \
    -p port:=/dev/ttyUSB0 \
    -p robot_id:=my_follower \
    -p publish_rate:=50.0
```

### 3. Use ROS2Robot in Your Application

```python
from lerobot.robots.so_follower import SO101FollowerROS2, SO101FollowerConfig

# Create configuration
config = SO101FollowerConfig(
    id="my_follower",
    ros_namespace="/so101_follower"
)

# Create robot instance
robot = SO101FollowerROS2(config)

# Connect (subscribes to ROS topics)
robot.connect()

# Use like any other robot
observation = robot.get_observation()
print(f"Current state: {observation}")

# Send actions
action = {
    "shoulder_pan.pos": 0.0,
    "shoulder_lift.pos": 10.0,
    "elbow_flex.pos": -20.0,
    "wrist_flex.pos": 0.0,
    "wrist_roll.pos": 0.0,
    "gripper.pos": 50.0
}
robot.send_action(action)

# Disconnect
robot.disconnect()
```

### 4. Run the VLA Control Loop on Real Hardware

`ros2_bridge/examples/so101_ros/run_vla.py` runs a trained SmolVLA policy in a closed
observation → policy → action loop. It reads joint-state and camera observations from ROS2
topics and publishes joint commands back — it is agnostic to what produces those topics, so
on real hardware the operator simply runs the `hardware_bridge` node against the physical arm
(step 2). No simulator is involved.

```bash
# Terminal 1 — hardware bridge against the physical arm (see step 2)
python3 -m lerobot.robots.ros_bridge.so_follower_bridge \
    --ros-args \
    -p namespace:=/so101_follower \
    -p port:=/dev/ttyUSB0 \
    -p robot_id:=my_follower \
    -p publish_rate:=50.0

# Terminal 2 — camera driver node(s) publishing the RGB topics the policy expects
#   (the hardware_bridge base node does NOT publish camera feeds)

# Terminal 3 — the policy control loop
export MODEL_ID=/path/to/pretrained_model      # real checkpoint (no default is shipped)
python3 ros2_bridge/examples/so101_ros/run_vla.py --fps 10 --device cuda
```

The loop's `run_vla.py` config targets the bridge topics `/so101_follower/state` and
`/so101_follower/action`. Change `ros_state_topic` / `ros_action_topic` / `ros_camera_topics`
in `run_vla.py` if your bridge uses a different namespace or your camera drivers publish
different topic names.

> [!NOTE]
> Integrator: camera wiring is environment-specific. The `hardware_bridge` base node
> publishes only joint state and status, so you must run separate ROS2 camera driver nodes
> (for example `usb_cam` or `realsense2_camera`) and set `ros_camera_topics` in `run_vla.py`
> to their topic names. The topic names in the shipped config are placeholders.

## Creating ROS2 Implementations for Other Robots

### Step 1: Create ROS2 Robot Implementation

Create a file like `your_robot_ros2.py`:

```python
from lerobot.robots.robot_ros2 import ROS2MotorRobot
from .config_your_robot import YourRobotConfig

class YourRobotROS2(ROS2MotorRobot):
    config_class = YourRobotConfig
    name = "your_robot_ros2"

    MOTOR_NAMES = [
        "joint1",
        "joint2",
        "gripper"
    ]

    def _get_motor_names(self) -> list[str]:
        return self.MOTOR_NAMES
```

### Step 2: Create Hardware Bridge

Create a file in `ros_bridge/your_robot_bridge.py`:

```python
from lerobot.robots.ros_bridge.hardware_bridge import RobotHardwareBridge, main
from lerobot.robots.your_robot import YourRobot, YourRobotConfig

class YourRobotBridge(RobotHardwareBridge):
    def __init__(self):
        super().__init__(node_name='your_robot_bridge')

    def create_robot(self):
        port = self.get_parameter('port').value
        robot_id = self.get_parameter('robot_id').value

        config = YourRobotConfig(port=port, id=robot_id)
        return YourRobot(config)

def main_your_robot(args=None):
    main(YourRobotBridge, args)

if __name__ == '__main__':
    main_your_robot()
```

### Step 3: Use Your ROS2 Robot

```python
from lerobot.robots.your_robot import YourRobotROS2, YourRobotConfig

config = YourRobotConfig(
    id="my_robot",
    ros_namespace="/your_robot"
)

robot = YourRobotROS2(config)
robot.connect()

# Use the robot...
```

## Advanced Topics

### Custom Message Types

If you need custom message types beyond `sensor_msgs/JointState`, override these methods:

```python
class CustomROS2Robot(ROS2Robot):
    def _create_observation_from_msg(self, msg):
        # Custom conversion logic
        pass

    def _create_action_msg(self, action):
        # Custom conversion logic
        pass
```

### Multi-Robot Setup

Run multiple bridges on different namespaces:

```bash
# Robot 1
python3 -m lerobot.robots.ros_bridge.so_follower_bridge \
    --ros-args -p namespace:=/robot1 -p port:=/dev/ttyUSB0

# Robot 2
python3 -m lerobot.robots.ros_bridge.so_follower_bridge \
    --ros-args -p namespace:=/robot2 -p port:=/dev/ttyUSB1
```

Then connect clients to different namespaces:

```python
robot1 = SO101FollowerROS2(SO101FollowerConfig(
    id="robot1", ros_namespace="/robot1"
))

robot2 = SO101FollowerROS2(SO101FollowerConfig(
    id="robot2", ros_namespace="/robot2"
))
```

### Network Setup

Run bridge and client on different machines:

```bash
# On robot machine (192.168.1.100)
export ROS_DOMAIN_ID=42
python3 -m lerobot.robots.ros_bridge.so_follower_bridge

# On client machine
export ROS_DOMAIN_ID=42
export ROS_MASTER_URI=http://192.168.1.100:11311
python3 your_application.py
```

## ROS2 Topics Reference

### Published by Bridge

- `/{namespace}/state` (`sensor_msgs/JointState`): Current robot state
  - `name`: Motor names
  - `position`: Current positions

- `/{namespace}/status` (`std_msgs/String`): Bridge status
  - "connected": Normal operation
  - "error": Error state

### Subscribed by Bridge

- `/{namespace}/action` (`sensor_msgs/JointState`): Action commands
  - `name`: Motor names
  - `position`: Desired positions

- `/{namespace}/calibration` (`std_msgs/Float64MultiArray`): Calibration data

## Troubleshooting

### No messages received

Check that bridge is running:

```bash
ros2 node list
ros2 topic list
ros2 topic echo /{namespace}/state
```

### Motors not responding

1. Check hardware bridge logs
2. Verify port permissions: `sudo chmod 666 /dev/ttyUSB0`
3. Verify calibration is loaded
4. Check motor power supply

### High latency

1. Adjust QoS settings
2. Increase publish rate
3. Check network configuration
4. Use wired connection instead of WiFi

## Examples

See `examples/` directory for complete examples:

- `basic_ros2_control.py`: Simple position control
- `teleoperation_ros2.py`: Teleoperation with ROS2 robots
- `data_collection_ros2.py`: Collecting datasets via ROS2

## License

Apache 2.0 - See LICENSE file for details

## Attribution

> This reference architecture originates with the Microsoft Research Xavier team, whose
> `xavier-tutorial` project defined the transparent GPU-offloading contract and
> deployment topology adapted here. This repository carries the consumer-facing contract
> and deployment scaffolding only; the offloading engine ships as prebuilt external
> images.
