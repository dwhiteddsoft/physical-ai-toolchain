#!/usr/bin/env bash
# Verify the pi05 policy loaded on the GPU stage and produced an action
set -o errexit -o nounset

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GPU_OFFLOAD_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$GPU_OFFLOAD_DIR"
eval "$(scripts/detect-platform.sh --export)"
server="pi05-control-remote-server-gpu"

# Loading roughly 7 GB of weights and warming CUDA takes a while on first start.
loaded=""
i=0
while [ "$i" -lt 120 ]; do
  loaded="$(kubectl --context "$GPU_OFFLOAD_KUBE_CONTEXT" logs deployment/pi05-control \
    --namespace gpu-offload-pi05 2>/dev/null | grep '"event": "loaded"' | tail -n 1 || true)"
  [ -n "$loaded" ] && break
  sleep 10
  i=$((i + 1))
done
test -n "$loaded"

action="$(kubectl --context "$GPU_OFFLOAD_KUBE_CONTEXT" logs deployment/pi05-control \
  --namespace gpu-offload-pi05 2>/dev/null | grep '"event": "action"' | tail -n 1 || true)"
test -n "$action"

LOADED="$loaded" ACTION="$action" SERVER="$server" python3 - <<'PY'
import json
import os

loaded = json.loads(os.environ["LOADED"])
action = json.loads(os.environ["ACTION"])
server = os.environ["SERVER"]

print(json.dumps(loaded, indent=2, sort_keys=True))

assert loaded["executed_by"].startswith(server + "-"), loaded["executed_by"]
assert loaded["policy_type"] == "pi05", loaded["policy_type"]
assert loaded["cuda_available"] is True, "CUDA was not available on the server stage"
assert loaded["device"] == "cuda", loaded["device"]
assert action["action"], "the control loop received an empty action"
assert action["client_host"] != loaded["executed_by"], "client and server are the same pod"

print()
print("pi05 offload verified")
print("  loaded on   :", loaded["executed_by"], "/", loaded["cuda_device_name"])
print("  policy      :", loaded["policy_class"])
print("  client host :", action["client_host"])
print("  cycle       :", action["cycle_ms"], "ms")
print("  action      :", action["action"])
PY
