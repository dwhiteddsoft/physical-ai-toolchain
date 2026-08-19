#!/usr/bin/env bash
# Install the admission controller in the resolved cluster
set -o errexit -o nounset

cd "$(dirname "${BASH_SOURCE[0]}")/.."
eval "$(scripts/detect-platform.sh --export)"
helm --kube-context "$GPU_OFFLOAD_KUBE_CONTEXT" upgrade --install gpu-offload helm/gpu-offload \
  --namespace gpu-offload \
  --create-namespace \
  --set image.registry=localhost \
  --set mutate.image.repository=xavier-mutate \
  --set mutate.image.tag=local \
  --set image.pullPolicy=Never
kubectl --context "$GPU_OFFLOAD_KUBE_CONTEXT" rollout status deployment/gpu-offload-mutate \
  --namespace gpu-offload \
  --timeout=180s
