# Carry Decision: LeRobot ROS2 Hardware Bridge

This document records how the LeRobot ROS2 real-hardware bridge from the Microsoft
Research `xavier-tutorial` reference architecture was carried into this repository, why
Option A (vendored modules) was chosen, and the per-file provenance of every extracted
artifact.

## Decision: Option A — Vendored modules

The ROS2 bridge is carried as **standalone vendored Python modules** under
`ros2_bridge/`, mirroring the upstream import-relative package layout (minus the
`src/lerobot/robots/` prefix). The modules are copied faithfully from the upstream patch
with only the minimal edits noted below.

### Options considered

- **Option A — Vendored modules (CHOSEN).** Copy the post-patch file contents into this
  repository as a self-contained reference example.
  - Pros: simplest to lint and read; standalone; requires no LeRobot checkout or pinned
    upstream commit to inspect; aligns with the Path D "consumer-facing scaffolding
    only" model.
  - Cons: drifts from upstream LeRobot over time; the vendored copies are not
    automatically updated when LeRobot changes.
- **Option B — Patch against a pinned LeRobot commit.** Ship the raw diff plus a pinned
  upstream SHA and apply it at build time.
  - Rejected: reintroduces a heavy LeRobot checkout as a hard dependency of the example,
    complicates linting and review, and couples this example to upstream refactors of
    `robots/utils.py` and `so_follower/__init__.py`.
- **Option C — Upstream a PR to LeRobot.** Contribute the ROS2 bridge back to LeRobot
  and depend on the released package.
  - Out of scope for this integration. Recorded as a follow-up (see task 10 /
    `gpu-offload/OPEN-ITEMS.md`).

## Edits applied to vendored files

Every vendored `.py` file received the following mandatory edits and nothing more:

1. A two-line SPDX + attribution header prepended above any shebang / Apache header:

   ```python
   # SPDX-License-Identifier: MIT
   # Adapted from Microsoft Research "xavier-tutorial" (GPU-offloading reference architecture).
   ```

2. `from __future__ import annotations` as the first statement after the module docstring
   (inserted where upstream lacked it).

Additional, individually documented edits:

- **`examples/so101_ros/run_vla.py` — GUID sanitization (required by denylist).** The
  upstream `DEFAULT_MODEL_ID` embedded a run GUID in the checkpoint path. The GUID was
  replaced with a `<run-id>` placeholder; the real checkpoint is supplied via the
  `MODEL_ID` environment variable or `--model-id`.
- **`examples/so101_ros/run_vla.py` — control-loop decoupling (task 05).** Task 04 left a
  single `# TODO(task-05): sim coupling` marker at the ROS2 topic-mapping config block. The
  script never imported a simulator; the only coupling was by ROS2 topic names. Task 05
  resolved the marker: the config now targets the real `hardware_bridge` namespaced topics
  (`/so101_follower/state`, `/so101_follower/action`), the module docstring documents the
  real-hardware path and the offload boundary, and a latency/safety warning was added. No
  simulator scene-reset or environment logic was present to remove.
- **`so_follower/__init__.py` — partial reconstruction.** Upstream modified an existing
  LeRobot package `__init__`. Only the added ROS2 export block is reproduced here (it
  references the vendored `config_so_follower_ros` and `so_follower_ros2` modules). The
  original upstream exports (`SO100Follower`, `SO101Follower`, and their non-ROS configs)
  are intentionally omitted because they belong to unmodified upstream LeRobot.
- **`ROS2_README.md`** received the attribution footer paragraph from
  `gpu-offload/PROVENANCE.md`. The upstream `## License Apache 2.0` line is preserved and
  headings were not otherwise restyled.

## File provenance

| Target (under `gpu-offload/examples/so101-real-hardware/`) | Source path in `lerobot.patch`                             |
|------------------------------------------------------------|------------------------------------------------------------|
| `ros2_bridge/robot_ros2.py`                                | `src/lerobot/robots/robot_ros2.py`                         |
| `ros2_bridge/ros_bridge/__init__.py`                       | `src/lerobot/robots/ros_bridge/__init__.py`                |
| `ros2_bridge/ros_bridge/hardware_bridge.py`                | `src/lerobot/robots/ros_bridge/hardware_bridge.py`         |
| `ros2_bridge/ros_bridge/so_follower_bridge.py`             | `src/lerobot/robots/ros_bridge/so_follower_bridge.py`      |
| `ros2_bridge/so_follower/__init__.py`                      | `src/lerobot/robots/so_follower/__init__.py` (partial)     |
| `ros2_bridge/so_follower/config_so_follower_ros.py`        | `src/lerobot/robots/so_follower/config_so_follower_ros.py` |
| `ros2_bridge/so_follower/so_follower_ros2.py`              | `src/lerobot/robots/so_follower/so_follower_ros2.py`       |
| `ros2_bridge/examples/so101_ros/run_vla.py`                | `examples/so101_ros/run_vla.py`                            |
| `ros2_bridge/examples/so101_ros/utils.py`                  | `examples/so101_ros/utils.py`                              |
| `ROS2_README.md`                                           | `src/lerobot/robots/ROS2_README.md`                        |

## Files not cleanly reconstructed

- **`src/lerobot/robots/so_follower/__init__.py`** — reproduced partially (ROS2 export
  block only). See the edit note above.
- **`src/lerobot/robots/utils.py`** — the patch *modifies* an existing upstream
  `robots/utils.py` rather than adding a new file. It cannot be cleanly reconstructed
  standalone without vendoring unmodified upstream LeRobot code, so it is intentionally
  not extracted. Consumers relying on those modifications should apply them against their
  own LeRobot checkout (Option B) or track the Option C upstream follow-up.

## Known unresolved imports

The vendored modules import from `lerobot.*` (e.g. `lerobot.processor`,
`lerobot.utils.decorators`, `lerobot.cameras.utils`, `lerobot.datasets.utils`,
`lerobot.policies.*`) and from ROS2 packages (`rclpy`, `sensor_msgs`, `std_msgs`,
`std_srvs`, `cv_bridge`). These are not vendored here; the example expects a LeRobot +
ROS2 runtime. Resulting lint findings (unresolved imports, relative imports to
non-vendored `.robot` / `.config` / `.config_so_follower` modules) are expected and are
tracked for tasks 05 and 08.

## Python lint policy (lint-only reference)

The vendored bridge modules are carried as **lint-only reference code**: ruff-checked, but
with no `uv.lock`, no build target, and no `pyproject.toml` subproject. This is the
recommended posture for Path D because the code is not runtime-verified here and depends
on external `ros2` and `lerobot` runtimes that this repository does not provision.

The authored control loop (`ros2_bridge/examples/so101_ros/run_vla.py`) is held to the
repository's full ruff rule set. The faithfully-vendored upstream modules
(`robot_ros2.py`, `ros_bridge/*.py`, `so_follower/*.py`, `examples/so101_ros/utils.py`)
carry a scoped, justified `per-file-ignores` entry in the root `pyproject.toml` for the
residual upstream style choices we do not refactor. Mechanical formatting issues
(whitespace, import ordering) are resolved rather than ignored, so the ignore surface
stays narrow and the global rule set is never weakened.
