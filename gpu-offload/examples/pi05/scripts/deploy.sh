#!/usr/bin/env bash
# Deploy the pi05 control loop and its GPU server stage
set -o errexit -o nounset

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GPU_OFFLOAD_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$GPU_OFFLOAD_DIR"
eval "$(scripts/detect-platform.sh --export)"
if [ "$GPU_OFFLOAD_GPU_ENABLED" != "true" ]; then
  echo "pi05 needs a GPU node; platform $GPU_OFFLOAD_PLATFORM has none" >&2
  exit 1
fi

# The checkpoint and the tokenizer cache stay on the node; both paths are machine
# local, so they come from .env or from these defaults.
model_path="${PI05_MODEL_HOST_PATH:-$HOME/Physical-AI-Operator/data/pi05-ur10-v5-joints-mixed-40k/pretrained_model}"
cache_path="${PI05_HF_CACHE_HOST_PATH:-$HOME/.cache/huggingface}"
test -f "$model_path/config.json" || {
  echo "No pi05 checkpoint at $model_path; set PI05_MODEL_HOST_PATH in .env" >&2
  exit 1
}
test -f "$model_path/model.safetensors" || {
  echo "Join the split weights first: cat $model_path/model.safetensors.part.* > $model_path/model.safetensors" >&2
  exit 1
}
test -d "$cache_path" || {
  echo "No HuggingFace cache at $cache_path; the gated PaliGemma tokenizer must be cached on the node" >&2
  exit 1
}

helm --kube-context "$GPU_OFFLOAD_KUBE_CONTEXT" upgrade --install pi05 examples/pi05 \
  --namespace gpu-offload-pi05 \
  --create-namespace \
  --set image.registry=localhost \
  --set "model.hostPath=$model_path" \
  --set "huggingFaceCache.hostPath=$cache_path" \
  --set "policy.dryRun=${PI05_DRY_RUN:-true}"

server="pi05-control-remote-server-gpu"
kubectl --context "$GPU_OFFLOAD_KUBE_CONTEXT" wait --for=create \
  "deployment/$server" \
  --namespace gpu-offload-pi05 \
  --timeout=180s
# The server stage is generated from the client deployment, so the client has to exist
# first. Park it at zero replicas while the GPU pod settles: a client that calls load()
# against a server that is still being replaced leaves the call queued behind a
# connection to a pod that no longer exists.
kubectl --context "$GPU_OFFLOAD_KUBE_CONTEXT" scale deployment/pi05-control \
  --namespace gpu-offload-pi05 \
  --replicas=0
# An exclusive GPU cannot be surged: the replacement pod stays Pending on
# "Insufficient nvidia.com/gpu" until the outgoing pod releases the device.
kubectl --context "$GPU_OFFLOAD_KUBE_CONTEXT" patch "deployment/$server" \
  --namespace gpu-offload-pi05 \
  --type=merge \
  --patch '{"spec":{"strategy":{"type":"Recreate","rollingUpdate":null}}}'
kubectl --context "$GPU_OFFLOAD_KUBE_CONTEXT" rollout restart "deployment/$server" \
  --namespace gpu-offload-pi05
kubectl --context "$GPU_OFFLOAD_KUBE_CONTEXT" rollout status "deployment/$server" \
  --namespace gpu-offload-pi05 \
  --timeout=600s
kubectl --context "$GPU_OFFLOAD_KUBE_CONTEXT" scale deployment/pi05-control \
  --namespace gpu-offload-pi05 \
  --replicas=1
kubectl --context "$GPU_OFFLOAD_KUBE_CONTEXT" rollout status deployment/pi05-control \
  --namespace gpu-offload-pi05 \
  --timeout=300s
