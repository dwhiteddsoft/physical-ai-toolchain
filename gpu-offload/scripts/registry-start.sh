#!/usr/bin/env bash
# Start the host-local image registry and point the k3s container runtime at it
set -o errexit -o nounset

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || (cd "$SCRIPT_DIR/../.." && pwd))"
# shellcheck source=../../scripts/lib/common.sh
source "$REPO_ROOT/scripts/lib/common.sh"

show_help() {
  cat << EOF
Usage: $(basename "$0") [OPTIONS]

Run a registry:2 container on the host and register it as a k3s mirror so every
cluster image pull resolves locally instead of reaching the internet.

The registry listens on 127.0.0.1 only. k3s runs on the host, so its containerd
reaches the same loopback endpoint the build tooling pushes to.

OPTIONS:
    -h, --help               Show this help message
    --config-preview         Print configuration and exit

ENVIRONMENT:
    GPU_OFFLOAD_REGISTRY_HOST   Registry endpoint (default: localhost:5000)
    GPU_OFFLOAD_REGISTRY_DATA   Blob storage on the host
    GPU_OFFLOAD_REGISTRY_IMAGE  Registry image reference

EXAMPLES:
    $(basename "$0")
    $(basename "$0") --config-preview
EOF
}

# Defaults
config_preview=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)         show_help; exit 0 ;;
    --config-preview)  config_preview=true; shift ;;
    *)                 fatal "Unknown option: $1" ;;
  esac
done

require_tools podman curl kubectl

#------------------------------------------------------------------------------
# Gather Configuration
#------------------------------------------------------------------------------

eval "$("$SCRIPT_DIR/detect-platform.sh" --export)"

registry_host="${GPU_OFFLOAD_REGISTRY_HOST:-localhost:5000}"
registry_port="${registry_host##*:}"
registry_data="${GPU_OFFLOAD_REGISTRY_DATA:-$HOME/.local/share/gpu-offload/registry}"
registry_image="${GPU_OFFLOAD_REGISTRY_IMAGE:-docker.io/library/registry:2}"
container_name="gpu-offload-registry"
registries_file="/etc/rancher/k3s/registries.yaml"

if [[ "$registry_port" == "$registry_host" ]]; then
  fatal "GPU_OFFLOAD_REGISTRY_HOST must include a port, for example localhost:5000"
fi

if [[ "$config_preview" == "true" ]]; then
  section "Configuration Preview"
  print_kv "Registry endpoint" "$registry_host"
  print_kv "Registry data" "$registry_data"
  print_kv "Registry image" "$registry_image"
  print_kv "Container name" "$container_name"
  print_kv "Cluster runtime" "$GPU_OFFLOAD_RUNTIME"
  print_kv "k3s registries file" "$registries_file"
  exit 0
fi

if [[ "$GPU_OFFLOAD_RUNTIME" != "k3s" ]]; then
  fatal "The host registry mirror targets k3s; runtime $GPU_OFFLOAD_RUNTIME nests its node in a container and cannot reach 127.0.0.1 on the host"
fi

#------------------------------------------------------------------------------
# Registry Container
#------------------------------------------------------------------------------
section "Registry Container"

mkdir -p "$registry_data"

if podman container exists "$container_name"; then
  # A stopped container keeps its blob volume; starting it back up preserves
  # every image already pushed.
  if [[ "$(podman inspect --format '{{.State.Running}}' "$container_name")" != "true" ]]; then
    podman start "$container_name" > /dev/null
    info "Started existing registry container"
  else
    info "Registry container already running"
  fi
else
  podman run --detach \
    --name "$container_name" \
    --restart always \
    --publish "127.0.0.1:$registry_port:5000" \
    --volume "$registry_data:/var/lib/registry:z" \
    "$registry_image" > /dev/null
  info "Created registry container"
fi

for _ in $(seq 1 30); do
  if curl --silent --fail "http://$registry_host/v2/" > /dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl --silent --fail "http://$registry_host/v2/" > /dev/null \
  || fatal "Registry did not answer on http://$registry_host/v2/"
info "Registry answering on http://$registry_host/v2/"

#------------------------------------------------------------------------------
# k3s Mirror Registration
#------------------------------------------------------------------------------
section "k3s Mirror Registration"

# containerd rejects a plain-HTTP registry unless the endpoint is declared. The
# mirror entry is also what makes every pull of "$registry_host/..." stay local.
desired_config="$(
  cat << EOF
mirrors:
  "$registry_host":
    endpoint:
      - "http://$registry_host"
configs:
  "$registry_host":
    tls:
      insecure_skip_verify: true
EOF
)"

if sudo test -f "$registries_file" && [[ "$(sudo cat "$registries_file")" == "$desired_config" ]]; then
  info "k3s already mirrors $registry_host"
else
  sudo mkdir -p "$(dirname "$registries_file")"
  printf '%s\n' "$desired_config" | sudo tee "$registries_file" > /dev/null
  info "Wrote $registries_file"
  # containerd reads registries.yaml only at k3s startup.
  sudo systemctl restart k3s
  kubectl --context "$GPU_OFFLOAD_KUBE_CONTEXT" wait --for=condition=Ready node --all --timeout=180s > /dev/null
  info "Restarted k3s and reloaded the mirror configuration"
fi

#------------------------------------------------------------------------------
# Summary
#------------------------------------------------------------------------------
section "Summary"
print_kv "Registry endpoint" "$registry_host"
print_kv "Registry data" "$registry_data"
print_kv "Container name" "$container_name"
print_kv "k3s registries file" "$registries_file"
info "Push with: podman push --tls-verify=false $registry_host/<repository>:<tag>"
