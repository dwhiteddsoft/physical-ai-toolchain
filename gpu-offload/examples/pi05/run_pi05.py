# SPDX-License-Identifier: MIT
#
# Control-loop entrypoint for the Pi0.5 UR10e offload example.
#
# Runs in the lightweight control container next to the robot. `autoremote.start`
# installs the decorators declared in remote.yaml, so `Pi05Policy.load` and
# `Pi05Policy.select_action` execute in the GPU server-stage pod while this process
# keeps only the robot I/O.
from __future__ import annotations

import json
import os
import time

from remoter import autoremote


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def main() -> None:
    autoremote.start(False)

    from pi05_policy import Pi05Policy
    from ur10e_bridge import RobotBridge

    # The checkpoint is mounted into the GPU stage, not into this container, so this
    # path is only ever resolved on the far side of the offload boundary.
    model_path = os.environ.get("PI05_MODEL_PATH", "/models/pi05")
    # pi05 was trained single-task on this verbatim string; a different prompt drifts
    # the text embedding off-distribution and pick quality collapses.
    task = os.environ.get("PI05_TASK", "Pick up the gear and place it in the box.")
    # Keep this at the training fps: the model emits a chunk of absolute joint targets
    # meant to be replayed at that rate.
    fps = _env_float("PI05_FPS", 15.0)

    bridge = RobotBridge.from_env()
    policy = Pi05Policy(pretrained_path=model_path, device="cuda", fps=int(fps), task=task)

    print(json.dumps({"event": "loading", "model_path": model_path}), flush=True)
    print(json.dumps({"event": "loaded", **policy.load()}), flush=True)

    policy.reset()
    period = 1.0 / fps
    while True:
        started = time.perf_counter()

        action = policy.select_action(bridge.read_state(), bridge.read_frames(), task)
        bridge.send_action(action)

        elapsed = time.perf_counter() - started
        print(
            json.dumps(
                {
                    "event": "action",
                    "client_host": os.environ.get("HOSTNAME", "unknown"),
                    "cycle_ms": round(elapsed * 1000.0, 3),
                    "action": [round(value, 6) for value in action],
                }
            ),
            flush=True,
        )

        remaining = period - elapsed
        if remaining > 0:
            time.sleep(remaining)


if __name__ == "__main__":
    main()
