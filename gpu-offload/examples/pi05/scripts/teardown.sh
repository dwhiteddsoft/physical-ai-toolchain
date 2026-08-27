#!/usr/bin/env bash
# Remove the pi05 workloads and demo namespace from the cluster
set -o errexit -o nounset

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GPU_OFFLOAD_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$GPU_OFFLOAD_DIR"
eval "$(scripts/detect-platform.sh --export)"
helm --kube-context "$GPU_OFFLOAD_KUBE_CONTEXT" uninstall pi05 \
  --namespace gpu-offload-pi05 --ignore-not-found
kubectl --context "$GPU_OFFLOAD_KUBE_CONTEXT" delete namespace gpu-offload-pi05 --ignore-not-found
# Retained PersistentVolumes outlive the release and would block a reinstall.
kubectl --context "$GPU_OFFLOAD_KUBE_CONTEXT" delete pv pi05-model pi05-hf-cache --ignore-not-found
echo "pi05 workloads removed; the checkpoint on the node is untouched"
