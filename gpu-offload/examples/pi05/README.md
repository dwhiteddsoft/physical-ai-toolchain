# Pi0.5 UR10e control loop with offloaded policy inference

<!-- cspell:ignore paligemma Containerfile -->

## 🧭 Overview

This example drives a UR10e with the trained `pi05-ur10-v5-joints-mixed-40k` checkpoint
while the policy runs in a GPU server-stage pod. The control container next to the robot
holds only the robot I/O and calls the policy as if it were local; the platform routes
the call to the GPU stage.

The offload boundary is [pi05_policy.py](./pi05_policy.py), a thin wrapper over the
lerobot 0.4.3 pi05 runtime:

| Call                                                     | Runs where        | Why                                                                       |
|----------------------------------------------------------|-------------------|---------------------------------------------------------------------------|
| `Pi05Policy.load`                                        | GPU stage         | Loads ~7 GB of weights plus the saved processor pipelines once per stage  |
| `Pi05Policy.select_action`                               | GPU stage         | Normalization, tokenization, the flow-matching pass, and un-normalization |
| `RobotBridge.read_state` / `read_frames` / `send_action` | Control container | Robot and camera I/O at the robot site                                    |

The wrapper exists rather than remoting `PI05Policy` directly because lerobot resolves the
concrete policy through `get_policy_class(cfg.type)`, and because lerobot's own
`select_action` exchanges torch tensors that the MessagePack codec rejects. Every value
crossing the wire is a plain `str`, `float`, `bytes`, `list`, or `dict`: joint state as
floats, camera frames as JPEG bytes, and the action as floats.

> [!IMPORTANT]
> [ur10e_bridge.py](./ur10e_bridge.py) is the hardware seam and is reference material.
> `read_state`, `read_frames`, and `send_action` raise `NotImplementedError` until they are
> connected to your ROS 2, RTDE, or Physical-AI-Operator follower stack. Dry-run mode
> substitutes zeroed state and blank frames so the offload path can be verified without a
> robot.

## 📋 Prerequisites

| Requirement         | Detail                                                                                                                                                |
|---------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------|
| GPU node            | 16 GB VRAM or more, with the NVIDIA device plugin advertising `nvidia.com/gpu`                                                                        |
| Cluster runtime     | `k3s` on the GPU host: the checkpoint is exposed through a hostPath `PersistentVolume`, which a `kind` node container cannot see without extra mounts |
| `gpu-offload` chart | Installed cluster-wide (`mise run d-offload-43-install-controller`)                                                                                     |
| Trained checkpoint  | A pi05 checkpoint directory on the node holding `config.json`, `model.safetensors`, and the saved processor pipelines                                 |
| HuggingFace cache   | The gated `google/paligemma-3b-pt-224` tokenizer cached on the node; the pods run with `HF_HUB_OFFLINE=1`                                             |
| UR10e               | Only for real motion; dry-run mode needs no robot                                                                                                     |

The upstream checkpoint ships `model.safetensors` split across parts. Join it once before
deploying:

```bash
cd <checkpoint>/pretrained_model
cat model.safetensors.part.* > model.safetensors
```

> [!NOTE]
> The server stage requests a whole GPU. On a single-GPU node it cannot start while another
> offload example holds the device, and scaling that example down is not enough — the
> controller recreates a server stage for as long as its client deployment exists. Uninstall
> the other example first (for example `mise run f-30-teardown` for the first-run demo).

## 🚀 Run

1. Point the tasks at the checkpoint and the tokenizer cache:

   ```bash
   cd gpu-offload
   mise run a-env-init
   ```

   Then set `PI05_MODEL_HOST_PATH` and `PI05_HF_CACHE_HOST_PATH` in `.env`. Both default
   to `$HOME/Physical-AI-Operator/data/pi05-ur10-v5-joints-mixed-40k/pretrained_model` and
   `$HOME/.cache/huggingface`.

2. Build, load, deploy, and verify:

   ```bash
   mise run e-pi05-40-build-image
   mise run e-pi05-41-load-image
   mise run e-pi05-50-deploy
   mise run e-pi05-51-check-inference
   ```

   `pi05-50-deploy` installs with `policy.dryRun=true` unless `PI05_DRY_RUN=false`.
   `pi05-51-check-inference` asserts that the load happened on the server-stage pod, that
   CUDA was available there, and that the control pod received an action.

3. Remove the workloads when finished. The checkpoint on the node is untouched:

   ```bash
   mise run e-pi05-90-teardown
   ```

## ⚙️ Configuration

| Value                       | Default                                     | Purpose                                                                               |
|-----------------------------|---------------------------------------------|---------------------------------------------------------------------------------------|
| `policy.task`               | `Pick up the gear and place it in the box.` | Language instruction; pi05 was trained single-task on this verbatim string            |
| `policy.fps`                | `15`                                        | Training fps; the action chunk is absolute joint targets meant to replay at this rate |
| `policy.cameras`            | `scene,wrist`                               | Camera names the processor pipeline renames to the training image keys                |
| `policy.dryRun`             | `false`                                     | Zeroed state and blank frames instead of robot I/O                                    |
| `policy.enableMotion`       | `false`                                     | Guard: the bridge refuses to command the arm until this is `true`                     |
| `model.hostPath`            | none                                        | Checkpoint directory on the node; required                                            |
| `huggingFaceCache.hostPath` | none                                        | Tokenizer cache on the node; required                                                 |

> [!WARNING]
> Running the loop at the wrong rate replays the action chunk too fast and causes
> overshoot and missed grasps. Changing `policy.task` drifts the text embedding
> off-distribution. Keep both aligned with training.

## 🧩 Volume Propagation

The controller copies `configMap`, `downwardAPI`, `emptyDir`, `ephemeral`,
`persistentVolumeClaim`, `projected`, and `secret` volumes from the client container into
the generated server pod, and rejects raw `hostPath` volumes. The checkpoint is therefore
published as a hostPath `PersistentVolume` with a matching claim, and the control
container declares both mounts even though it never reads them. Environment variables on
the control container are merged into the server container the same way, so
`PI05_MODEL_PATH` and `HF_HOME` resolve identically on both sides.

## 🐍 Local Python

The dependency set is isolated because pi05 needs lerobot's transformers fork (patched
SigLIP), which conflicts with the stock `transformers` every other Python subproject uses:

```bash
cd gpu-offload/examples/pi05
uv venv --seed
uv sync
```

## 📦 Files

| Path                           | Content                                                          |
|--------------------------------|------------------------------------------------------------------|
| `pi05_policy.py`               | Policy wrapper; the offloaded class                              |
| `ur10e_bridge.py`              | Robot and camera seam; never offloaded                           |
| `run_pi05.py`                  | Control-loop entrypoint                                          |
| `remote.yaml`                  | Offload spec, mirrored into the ConfigMap the chart renders      |
| `Containerfile`                | Image for both the control container and the server stage        |
| `pyproject.toml`, `uv.lock`    | Isolated pi05 dependency set                                     |
| `templates/manifests.yaml.tpl` | ServiceAccount, RBAC, volumes, ConfigMap, and control Deployment |
