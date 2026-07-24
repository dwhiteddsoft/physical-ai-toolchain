# Real-hardware SO101 with offloaded VLA inference

## 🧭 Overview

This example drives a physical SO-101 arm with a trained SmolVLA policy while the policy
inference runs on a remote GPU through the transparent GPU-offloading contract. A
lightweight control container runs the closed loop next to the robot and calls its policy
as if it ran locally; the platform intercepts the policy's action-selection call and
routes it to a GPU server-stage pod.

The offload boundary is `SmolVLAPolicy.select_action` in
[run_vla.py](./ros2_bridge/examples/so101_ros/run_vla.py). The control loop is
topic-source-agnostic: it reads observations and publishes commands over ROS2 topics, and
a separate `hardware_bridge` node owns the motor bus. See
[ROS2_README.md](./ROS2_README.md) for the ROS2 bridge details and
[bring-your-own-arm.md](./bring-your-own-arm.md) to adapt the pattern to a different arm.

## 📋 Prerequisites

| Requirement                | Detail                                                                                                                                      |
|----------------------------|---------------------------------------------------------------------------------------------------------------------------------------------|
| Offloading platform images | Prebuilt external `xavier-mutate` and `pyremote` images mirrored into a registry you control (see the [chart README](../../helm/README.md)) |
| `gpu-offload` chart        | Installed cluster-wide so opt-in workloads are mutated (see the [chart README](../../helm/README.md))                                       |
| Physical SO-101            | A calibrated SO-101 follower arm connected to the bridge host                                                                               |
| `hardware_bridge` node     | Running against the physical arm, publishing state and subscribing to commands over ROS2 topics                                             |
| ROS2 environment           | A ROS2 install with `rclpy`, `sensor_msgs`, `std_msgs`, and `cv_bridge`, plus your camera driver topics                                     |
| Control image              | An operator-built image containing `run_vla.py`, the bundled [ros2_bridge](./ros2_bridge/), and the LeRobot runtime                         |
| Trained checkpoint         | A SmolVLA checkpoint reachable by the control container (`MODEL_ID`)                                                                        |

> [!IMPORTANT]
> This example is a reference to adapt to your setup; it has not been validated
> end-to-end. The offloading platform images and a physical arm are prerequisites you
> supply.

## 🚀 Run

1. **Install the offload chart.** Deploy the mutating webhook and node agent so opt-in
   workloads are mutated. Point `image.registry` at the registry holding your mirrored
   `xavier-mutate` and `pyremote` images. Full instructions are in the
   [chart README](../../helm/README.md).

   ```bash
   helm install gpu-offload gpu-offload/helm/gpu-offload \
     --namespace gpu-offload --create-namespace \
     --set image.registry=<your-registry>.azurecr.io
   ```

2. **Apply the offload ConfigMap.** This carries `remote.yaml`, which maps
   `SmolVLAPolicy.select_action` to a GPU server stage.

   ```bash
   kubectl apply -f manifests/offload-configmap.yaml
   ```

3. **Apply the control workload.** Edit
   [manifests/control-workload.yaml](./manifests/control-workload.yaml) first: set the
   `image` to your operator-supplied control image and set `MODEL_ID` to your checkpoint
   path. The workload carries the `xavier: "true"` label, the `xavierconfig` annotation
   referencing the ConfigMap, and the `REMOTERPORT` env, so the platform injects the GPU
   server-stage pod on admission.

   ```bash
   kubectl apply -f manifests/control-workload.yaml
   ```

4. **Start the `hardware_bridge` node.** On the machine connected to the arm, launch the
   bridge so it owns the motor bus and exposes state/action topics. See
   [ROS2_README.md](./ROS2_README.md) for the exact command and topic names.

   ```bash
   python3 -m lerobot.robots.ros_bridge.so_follower_bridge \
     --ros-args \
     -p namespace:=/so101_follower \
     -p port:=/dev/ttyUSB0 \
     -p robot_id:=my_follower \
     -p publish_rate:=50.0
   ```

5. **Run the control loop.** The control container runs
   [run_vla.py](./ros2_bridge/examples/so101_ros/run_vla.py), which reads observations and
   publishes commands over the bridge topics; its `select_action` call executes on the
   remote GPU. Match the topic names and camera topics to your bridge and camera driver.

   ```bash
   python3 run_vla.py --model-id "$MODEL_ID" --fps 10
   ```

## ⚠️ Limitations

- This example has **not been validated end-to-end.** Treat every command as a reference
  to adapt to your hardware, not a turnkey recipe.
- The offloading platform images (`xavier-mutate`, `pyremote`) are an external
  prerequisite. The chart and this example consume them; they are not built here.
- Offloading `select_action` across machines injects network latency and jitter into the
  control loop. SmolVLA inference already caps the loop near 2.5 Hz, and a closed-loop arm
  is sensitive to added delay.
- Prefer **same-node** offload (the GPU server-stage pod co-located with the control host)
  for closed-loop control. Only use cross-machine offload with an operator-supervised,
  latency-bounded setup and a watchdog that halts the arm if actions arrive late.

## 🔗 See also

- [GPU offload contract](../../specifications/gpu-offload.specification.md) — the opt-in
  label, annotation, and ConfigMap wiring.
- [remote.yaml schema](../../specifications/remote-spec-schema.md) — the offload-spec
  fields this example's [remote.yaml](./remote.yaml) satisfies.
- [gpu-offload chart README](../../helm/README.md) — installing the platform components.
- [Bring your own arm](./bring-your-own-arm.md) — adapting the bridge to another arm.
- [ROS2 bridge guide](./ROS2_README.md) — the ROS2 robot/bridge details.
