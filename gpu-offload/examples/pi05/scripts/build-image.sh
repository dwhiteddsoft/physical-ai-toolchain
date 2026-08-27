#!/usr/bin/env bash
# Build the pi05 example client/server image with Podman
set -o errexit -o nounset

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GPU_OFFLOAD_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$GPU_OFFLOAD_DIR"

uv_args=""
if [ -n "${UV_INDEX_URL:-}" ]; then
  uv_args="--build-arg UV_INDEX_URL=$UV_INDEX_URL"
fi

# Share the host uv cache with the build. The cu128 torch wheels alone are several
# gigabytes; without this every rebuild re-downloads the whole dependency set.
# Rootless Podman maps container root to the invoking user, so wheels fetched during
# the build land in the same cache a local `uv sync` uses.
cache_dir="${UV_CACHE_DIR:-$HOME/.cache/uv}"
mkdir -p "$cache_dir"

# shellcheck disable=SC2086
podman build $uv_args \
  --volume "$cache_dir:/root/.cache/uv" \
  --file examples/pi05/Containerfile \
  --tag localhost/gpu-offload-pi05:local \
  .
podman image exists localhost/gpu-offload-pi05:local
