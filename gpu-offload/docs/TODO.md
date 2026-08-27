---
title: GPU Offload Work Items
description: Track pending GPU-offload implementation work
ms.date: 2026-08-19
ms.topic: reference
---

<!-- cspell:ignore simplelog Robotiq RealSense pyrealsense servoj movej pretrained -->

Track implementation work that has been identified but not completed. Remove each task after its code changes and validation are merged.

## Pi05 UR10e Real-Robot Motion

Target directory: [`examples/pi05`](../examples/pi05/)

The pi05 example offloads inference to a GPU server stage and is verified end to end in dry-run
mode. `RobotBridge` in [`ur10e_bridge.py`](../examples/pi05/ur10e_bridge.py) is still the only
unimplemented seam: `read_state`, `read_frames`, and `send_action` raise `NotImplementedError`
unless `PI05_DRY_RUN=true`. The arm therefore does not move yet.

### Pi05 Progress Log

| Date       | Entry                                                                                                                                                                           |
|------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 2026-08-19 | Example added: policy wrapper, control loop, chart, offload spec, isolated `uv.lock`, container image, and `pi05-*` tasks.                                                      |
| 2026-08-19 | Offload verified on the k3s GPU host. The GPU stage loaded the checkpoint on an RTX 5090 and returned actions to the client pod at roughly 2 to 8 ms per cycle in dry-run mode. |
| 2026-08-19 | Fixed the dry-run state width. The checkpoint consumes six joint values plus one gripper value; a six-value vector failed with a tensor size mismatch.                          |
| 2026-08-19 | Fixed a deploy race by parking the client at zero replicas until the generated server stage is ready.                                                                           |
| 2026-08-19 | Confirmed the controller is reachable: dashboard port 29999 on 192.168.2.102 accepts connections from the GPU host.                                                             |
| 2026-08-19 | Confirmed both cameras are attached to the GPU host: RealSense D405 and RealSense D435i, enumerated as `/dev/video*`.                                                           |

### Pi05 Robot Interfaces

| Port  | Interface        | Use                                                                                |
|-------|------------------|------------------------------------------------------------------------------------|
| 29999 | Dashboard        | Text protocol for robot mode, safety mode, power, and brake release                |
| 30002 | Secondary client | Accepts URScript; this is the interface that moves the arm                         |
| 30003 | Realtime client  | 125 Hz binary stream of joint angles, TCP pose, and modes                          |
| 30004 | RTDE             | Structured real-time protocol used by the `ur_rtde` control and receive interfaces |
| 63352 | Gripper          | Robotiq socket interface on the controller                                         |

### Pi05 Open Questions

* Camera source: capture the RealSense pair directly in the control container, or read the frames the ROS 2 operator stack already publishes.
* Contention: only one RTDE control script can own the arm, so the operator follower node and this control loop cannot drive it at the same time.
* Motion policy: the initial move sequence, the servo rate relative to the 15 Hz training rate, and which safety gates must pass before motion is enabled.

### Pi05 Motion Implementation

* [ ] Implement `read_state` as six joint positions plus the gripper value, ordered as in the training dataset.
* [ ] Implement `read_frames` for the `scene` and `wrist` cameras as JPEG-encoded RGB at the trained 224 by 224 resolution.
* [ ] Implement `send_action` against the joint-target interface, keeping `PI05_ENABLE_MOTION` as the gate that separates observation from motion.
* [ ] Apply per-joint clamps before every command and reject stale or non-finite actions.
* [ ] Move the arm to the home pose before the first predicted action, because the checkpoint expects to start inside its training distribution.
* [ ] Give the control container the network path and device access the robot and cameras require, and document both in the example README.
* [ ] Stop motion cleanly on shutdown, on connection loss, and when the policy stops returning actions.

### Pi05 Motion Acceptance Criteria

* The control loop reads live joint state and camera frames without dry-run substitutes.
* Predicted actions reach the arm only when motion is explicitly enabled.
* Inference still executes on the GPU stage, with the control container holding no model weights.
* Loss of the robot connection or the policy stage halts motion instead of replaying a stale action.
* The example README states the required robot address, ports, camera devices, and safety gates.

### Pi05 Motion Validation

* [ ] Run the control loop with motion disabled and confirm live state and frames produce actions from the GPU stage.
* [ ] Confirm the loop sustains the 15 Hz training rate with live cameras.
* [ ] Enable motion and confirm the arm tracks predicted actions from the home pose.
* [ ] Confirm a forced disconnect of the robot or the policy stage stops motion.

## Mise Task Layout

Target files: [`mise.toml`](../mise.toml), [`scripts`](../scripts/), [`examples`](../examples/)

The current tasks predate
[`mise-tasks.instructions.md`](../../.github/instructions/mise-tasks.instructions.md) and violate it
in three ways: task bodies are embedded shell scripts inside the TOML, names use numeric segments
instead of colon-separated groups, and the resulting `mise tasks` listing does not read as the
order a new contributor should follow after cloning.

### Mise Task Implementation

* [ ] Move every embedded `run` body out of `mise.toml` into a script file, leaving each task as an invocation of that script.
* [ ] Place platform-wide scripts in `gpu-offload/scripts` and example-specific scripts in `gpu-offload/examples`, prefixed with the example name.
* [ ] Regroup task names with colon-separated prefixes so related tasks match a single pattern.
* [ ] Start every task name with a letter, never a digit or symbol.
* [ ] Order the groups so the alphanumeric sort matches the human path: setup, deploy, verify, develop, then teardown.
* [ ] Keep the pi05 tasks aligned with the same grouping rather than carrying a parallel naming scheme.
* [ ] Update the READMEs and walkthroughs that reference the old task names.

### Mise Task Acceptance Criteria

* `mise.toml` contains no multi-line shell bodies.
* `mise tasks` lists the groups in the order a contributor executes them.
* Each script is independently executable and passes `shellcheck`.
* Every documented command matches a task that exists.

### Mise Task Validation

* [ ] Run `shellcheck` over the extracted scripts.
* [ ] Run the full first-run path through the renamed tasks.
* [ ] Run the full pi05 path through the renamed tasks.

## Local Podman and kind Hardening

The CPU-only and WSL2 NVIDIA first-run paths completed successfully with rootless Podman 4.9.3, kind 0.30.0, Kubernetes 1.35.0, and an RTX 3060. The validated WSL2 path requires local runtime configuration that is not suitable for production clusters.

### Observed Issues

* kind can retain an older image behind a mutable `:local` tag. Loading a new archive does not reliably replace the existing containerd image without removing the tag first.
* Generated server Deployments are asynchronous. Calling `kubectl rollout status` immediately after Helm returns can fail with `NotFound`; the walkthrough waits for resource creation first.
* The one-shot client can invoke its remote function before the generated server becomes discoverable. Restarting the client after the server rollout succeeds avoids the race.
* Changing `remote.yaml` from a CPU stage to an NVIDIA stage can leave the obsolete generated CPU Deployment until reconciliation removes it or an operator deletes it.
* NVIDIA's standard device plugin fails WSL2 GPU-PV discovery through nested local Kubernetes because NVML initialization returns `Not Supported`.
* The validated WSL2 workaround uses a privileged generic device plugin to register `/dev/dxg` as `nvidia.com/gpu`.
* The validated kind runtime adds `/usr/lib/wsl` to the base OCI specification, making the read-only driver tree visible to every pod on that local node.
* The TCP messenger previously entered the global heartbeat list before initializing its socket. Depending on thread timing, the heartbeat could close the new connection and fail the remote call.
* The synchronized first-run chart briefly contained both `.yaml` and `.yaml.tpl` copies of the same template. Helm rendered duplicate resources, and whitespace trimming joined the YAML language-server directive to `apiVersion` in one copy.

### Local Runtime Implementation

* [ ] Add an automated Podman and kind smoke harness for CPU-only and WSL2 NVIDIA paths.
* [ ] Make the smoke harness wait for each generated Deployment to exist before checking rollout status.
* [ ] Use immutable image references or make the harness remove mutable tags before loading replacements.
* [ ] Gate the first client invocation on server-stage discovery instead of requiring a client restart.
* [ ] Reconcile generated Deployments immediately when server stages are removed or renamed.
* [ ] Replace the privileged generic WSL2 device plugin with a CDI-aware allocation path when kind and containerd support the WSL GPU device end to end.
* [ ] Scope WSL driver-library injection to GPU-allocated containers instead of the node-wide OCI base specification.
* [x] Initialize TCP transport state before registering the messenger for heartbeat transmission.
* [x] Keep one `.yaml.tpl` first-run template so Helm renders each resource once without raw YAML editor diagnostics.

### Local Runtime Acceptance Criteria

* A single command creates the Podman-backed kind cluster, loads fresh images, and runs the selected path.
* The first client pod returns a remote result without a manual restart.
* Stage changes remove obsolete generated Deployments.
* Only GPU-allocated pods receive `/dev/dxg` and WSL driver libraries.
* [x] Successful calls do not emit heartbeat attribute errors.

### Local Runtime Validation

* [x] CPU server returned `{"executed_by":"first-run-client-remote-server-cpu-...","predictions":[1,4,9,16]}`.
* [x] Kubernetes advertised `nvidia.com/gpu: 1` on the WSL2 kind node.
* [x] A disposable GPU pod reported NVIDIA GeForce RTX 3060 through `/dev/dxg`.
* [x] The generated NVIDIA server requested one GPU while the client requested none.
* [x] The generated NVIDIA server reported NVIDIA GeForce RTX 3060, driver 595.95, and 12288 MiB.
* [x] NVIDIA server returned `{"executed_by":"first-run-client-remote-server-nvidia-...","predictions":[1,4,9,16]}`.
* [x] Fresh CPU and NVIDIA client runs completed without heartbeat attribute, bad file descriptor, or missing-result errors.
* [x] Synchronized commit `fbb50d27` passed runtime tests and fresh CPU and NVIDIA cluster runs after rebuilding and replacing the kind image.
* [x] The first-run chart passed Helm lint, single-resource render checks, and Kubernetes server-side dry-run validation.

## Bound Log Rollover Failure Handling

Target file: [`runtime/remoter/simplelog.py`](../runtime/remoter/simplelog.py)

The logger invokes `lsof` during process startup to avoid rotating a log file that another process has open. A missing `lsof` executable now returns `False`, but other subprocess and filesystem failures can still block startup indefinitely.

### Failure Modes

* `subprocess.run()` has no timeout. A stalled `lsof` process stalls logger and application initialization.
* `rollover()` catches every exception and retries with a new filename in an unbounded loop.
* Persistent filesystem errors, including a read-only directory, insufficient permissions, exhausted storage, or rename failures, cause infinite retries.
* An execution error other than `FileNotFoundError`, such as `PermissionError`, enters the same unbounded retry loop.
* The current implementation provides no final error identifying why rollover could not complete.

### Implementation

* [ ] Add a short timeout to the `lsof` invocation.
* [ ] Treat `FileNotFoundError`, `subprocess.TimeoutExpired`, and other expected `OSError` failures as an unavailable `lsof` check.
* [ ] Preserve argument-list invocation and continue to avoid `shell=True`.
* [ ] Replace the unbounded rollover loop with a finite number of filename attempts.
* [ ] Raise a clear exception containing the original failure after all attempts are exhausted.
* [ ] Preserve the existing log retention behavior when rollover succeeds.
* [ ] Remove the duplicate `os` import while editing the module.

### Acceptance Criteria

* Application startup completes when `lsof` is not installed.
* Application startup does not wait indefinitely when `lsof` stalls.
* A persistent filesystem failure exits rollover after a bounded number of attempts.
* The final exception identifies the target log path and preserves the underlying error as its cause.
* Existing log files continue to rotate according to the `keep` value.
* Paths are passed as subprocess arguments without shell interpolation.

### Validation

* [ ] Add focused tests that replace `subprocess.run()` with missing-command, timeout, open-file, and closed-file outcomes.
* [ ] Add focused tests for successful rollover and persistent filesystem failure.
* [ ] Verify the persistent-failure test completes within a fixed test timeout.
* [ ] Run the GPU-offload runtime test suite.
* [ ] Start the first-run client in the slim container image, where `lsof` is absent, and verify remote execution reaches the server pod.
