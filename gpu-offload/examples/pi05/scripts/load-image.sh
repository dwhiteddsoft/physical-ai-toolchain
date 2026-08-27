#!/usr/bin/env bash
# Load the pi05 image into the resolved cluster runtime
set -o errexit -o nounset

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GPU_OFFLOAD_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$GPU_OFFLOAD_DIR"
exec scripts/load-images.sh localhost/gpu-offload-pi05:local
