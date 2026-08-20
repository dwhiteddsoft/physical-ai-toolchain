#!/usr/bin/env bash
# Push local Podman images to the host-local registry the cluster pulls from
set -o errexit -o nounset

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || (cd "$SCRIPT_DIR/../.." && pwd))"
# shellcheck source=../../scripts/lib/common.sh
source "$REPO_ROOT/scripts/lib/common.sh"

show_help() {
  cat << EOF
Usage: $(basename "$0") <repository:tag> [repository:tag...]

Tag locally built images into the host registry and push them over plain HTTP.
Each argument is a bare repository and tag such as gpu-offload-ur10e:local; the
registry endpoint is prepended. The pushed reference is what the Helm charts
must request so the cluster never reaches an external registry.

OPTIONS:
    -h, --help               Show this help message
    --config-preview         Print configuration and exit

ENVIRONMENT:
    GPU_OFFLOAD_REGISTRY_HOST   Registry endpoint (default: localhost:5000)

EXAMPLES:
    $(basename "$0") gpu-offload-ur10e:local
    $(basename "$0") xavier-mutate:local pyremote:local
EOF
}

# Defaults
config_preview=false
images=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)         show_help; exit 0 ;;
    --config-preview)  config_preview=true; shift ;;
    -*)                fatal "Unknown option: $1" ;;
    *)                 images+=("$1"); shift ;;
  esac
done

require_tools podman curl

#------------------------------------------------------------------------------
# Gather Configuration
#------------------------------------------------------------------------------

registry_host="${GPU_OFFLOAD_REGISTRY_HOST:-localhost:5000}"

if [[ "$config_preview" == "true" ]]; then
  section "Configuration Preview"
  print_kv "Registry endpoint" "$registry_host"
  print_kv "Images" "${images[*]:-none}"
  exit 0
fi

[[ ${#images[@]} -gt 0 ]] || fatal "No images given; see --help"

curl --silent --fail "http://$registry_host/v2/" > /dev/null \
  || fatal "No registry on http://$registry_host/v2/; run scripts/registry-start.sh first"

#------------------------------------------------------------------------------
# Push
#------------------------------------------------------------------------------
section "Push"

for image in "${images[@]}"; do
  # Accept both the bare repository:tag and an already qualified reference so
  # the script is safe to re-run with either form.
  reference="${image#localhost/}"
  reference="${reference#"$registry_host"/}"
  target="$registry_host/$reference"

  if podman image exists "localhost/$reference"; then
    source_image="localhost/$reference"
  elif podman image exists "$target"; then
    source_image="$target"
  else
    fatal "No local image localhost/$reference; build it first"
  fi

  podman tag "$source_image" "$target"
  podman push --tls-verify=false "$target"
  info "Pushed $target"
done

#------------------------------------------------------------------------------
# Summary
#------------------------------------------------------------------------------
section "Summary"
print_kv "Registry endpoint" "$registry_host"
print_kv "Images pushed" "${#images[@]}"
