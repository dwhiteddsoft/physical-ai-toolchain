#!/usr/bin/env bash
# Build the first-run client and GPU server-stage images with Podman
set -o errexit -o nounset

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GPU_OFFLOAD_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$GPU_OFFLOAD_DIR"
eval "$(scripts/detect-platform.sh --export)"

uv_args=""
if [ -n "${UV_INDEX_URL:-}" ]; then
  uv_args="--build-arg UV_INDEX_URL=$UV_INDEX_URL"
fi

# shellcheck disable=SC2086
podman build $uv_args \
  --file examples/first-run/Containerfile \
  --tag localhost/gpu-offload-first-run:local \
  .
podman image exists localhost/gpu-offload-first-run:local

if [ "$GPU_OFFLOAD_GPU_ENABLED" = "true" ]; then
  # shellcheck disable=SC2086
  podman build $uv_args \
    --file examples/first-run/Containerfile.gpu \
    --tag localhost/gpu-offload-first-run-gpu:local \
    .
  podman image exists localhost/gpu-offload-first-run-gpu:local
fi
