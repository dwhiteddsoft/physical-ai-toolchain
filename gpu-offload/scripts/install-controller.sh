#!/usr/bin/env bash
# Install the admission controller in the resolved cluster
set -o errexit -o nounset

cd "$(dirname "${BASH_SOURCE[0]}")/.."
eval "$(scripts/detect-platform.sh --export)"

registry_host="${GPU_OFFLOAD_REGISTRY_HOST:-localhost:5000}"

# Prefer the host-local registry: it needs no privileges. Only k3s runs on the
# host and gets a containerd mirror pointed at it (registry-up.sh); a kind node
# runs in its own container and cannot reach the host's loopback address, so it
# always falls back to an image already loaded into the node (see
# load-images.sh) and referenced without a registry host.
if [ "$GPU_OFFLOAD_RUNTIME" = "k3s" ] && curl --silent --fail --max-time 2 "http://$registry_host/v2/" > /dev/null 2>&1; then
  image_registry="$registry_host"
  pull_policy="IfNotPresent"
else
  image_registry="localhost"
  pull_policy="Never"
fi

helm --kube-context "$GPU_OFFLOAD_KUBE_CONTEXT" upgrade --install gpu-offload helm/gpu-offload \
  --namespace gpu-offload \
  --create-namespace \
  --set image.registry="$image_registry" \
  --set mutate.image.repository=xavier-mutate \
  --set mutate.image.tag=local \
  --set image.pullPolicy="$pull_policy"
kubectl --context "$GPU_OFFLOAD_KUBE_CONTEXT" rollout status deployment/gpu-offload-mutate \
  --namespace gpu-offload \
  --timeout=180s
