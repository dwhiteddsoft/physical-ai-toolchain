---
title: Local Podman and kind Setup
description: Prepare a Podman-backed kind cluster for CPU-only or WSL NVIDIA GPU offload verification
ms.date: 2026-08-11
ms.topic: get-started
---

<!-- cspell:ignore crun -->

Prepare a rootless Podman-backed kind cluster for the first GPU-offload run. Use the CPU path on any Linux host or the NVIDIA path in WSL2 with a GPU exposed through `/dev/dxg`.

## Clone the Repository

Clone the repository and enter its root directory:

```bash
git clone https://github.com/microsoft/physical-ai-toolchain.git
cd physical-ai-toolchain
```

Existing clones must run the remaining commands from the repository root:

```bash
git pull --ff-only
git rev-parse --show-toplevel
```

## Prerequisites

| Tool                     | Validated version               | Verify                 |
|--------------------------|---------------------------------|------------------------|
| Ubuntu                   | 24.04 on Linux or WSL2          | `cat /etc/os-release`  |
| Podman                   | 4.9.3 or later                  | `podman version`       |
| kind                     | 0.30.0                          | `kind version`         |
| Kubernetes               | 1.35.0                          | `kubectl version`      |
| Helm                     | 3.21.3                          | `helm version`         |
| NVIDIA Container Toolkit | 1.19.1 or later for NVIDIA only | `nvidia-ctk --version` |

Install the base host packages:

```bash
sudo apt-get update
sudo apt-get install --yes curl jq podman
podman info --format '{{.Host.Security.Rootless}} {{.Host.OCIRuntime.Name}}'
```

The final command must print `true crun`. Install kind, kubectl, and Helm with mise when they are not already available:

```bash
mise use --global kind@0.30.0 kubectl@1.35.1 helm@3.21.3
eval "$(mise activate bash)"
kind version
kubectl version --client
helm version
```

Render the controller chart before creating a cluster:

```bash
helm template gpu-offload gpu-offload/helm/gpu-offload \
  --namespace gpu-offload \
  --set image.registry=localhost >/dev/null
```

## Podman kind CPU Only

Create a single-node cluster without NVIDIA configuration:

```bash
export KIND_EXPERIMENTAL_PROVIDER=podman

kind create cluster \
  --name gpu-offload \
  --image kindest/node:v1.35.0

kubectl config use-context kind-gpu-offload
kubectl wait \
  --for=condition=Ready \
  node/gpu-offload-control-plane \
  --timeout=120s
kubectl get nodes -o wide
```

Confirm that Podman and Kubernetes run CPU workloads:

```bash
podman run --rm docker.io/library/alpine:3.22 \
  sh -c 'uname -m; echo Podman CPU container works'

kubectl run cpu-check \
  --image=docker.io/library/alpine:3.22 \
  --restart=Never \
  --command -- sh -c 'uname -m; echo Kubernetes CPU pod works'
kubectl wait pod/cpu-check \
  --for=jsonpath='{.status.phase}'=Succeeded \
  --timeout=120s
kubectl logs pod/cpu-check
kubectl delete pod/cpu-check
```

Continue to the [CPU-only offload](./02-first-cpu-offload.md#podman-kind-cpu-only).

## Podman kind NVIDIA on WSL2

Use this path on WSL2 when the Windows NVIDIA driver exposes `/dev/dxg`. Do not install a Linux display driver in the WSL distribution.

> [!IMPORTANT]
> The WSL2 path uses a generic Kubernetes device plugin for `/dev/dxg`. NVIDIA's standard device plugin requires NVML behavior that is not available in this nested WSL2 and kind topology.

### Install NVIDIA Container Toolkit

Install NVIDIA Container Toolkit from NVIDIA's apt repository:

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor --yes \
  --output /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null

sudo apt-get update
sudo apt-get install --yes nvidia-container-toolkit
sudo mkdir -p /etc/cdi
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
nvidia-ctk cdi list
```

The CDI list must include `nvidia.com/gpu=all`.

### Verify Podman GPU Access

Verify WSL and rootless Podman before creating Kubernetes:

```bash
nvidia-smi
test -c /dev/dxg

podman run --rm \
  --security-opt=label=disable \
  --device nvidia.com/gpu=all \
  docker.io/nvidia/cuda:12.8.1-base-ubuntu24.04 \
  nvidia-smi
```

Both `nvidia-smi` commands must list the same adapter.

### Create the NVIDIA kind Cluster

Create the kind node with the WSL device and driver directory mounted into it:

```bash
export KIND_EXPERIMENTAL_PROVIDER=podman

cat <<'EOF' >/tmp/gpu-offload-kind.yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    extraMounts:
      - hostPath: /dev/dxg
        containerPath: /dev/dxg
      - hostPath: /usr/lib/wsl
        containerPath: /usr/lib/wsl
        readOnly: true
EOF

kind create cluster \
  --name gpu-offload \
  --image kindest/node:v1.35.0 \
  --config=/tmp/gpu-offload-kind.yaml

kubectl config use-context kind-gpu-offload
kubectl wait \
  --for=condition=Ready \
  node/gpu-offload-control-plane \
  --timeout=120s
```

Confirm GPU access inside the kind node:

```bash
podman exec gpu-offload-control-plane sh -c \
  'driver_dir=$(find /usr/lib/wsl/drivers -mindepth 1 -maxdepth 1 -type d | head -n 1); LD_LIBRARY_PATH="/usr/lib/wsl/lib:${driver_dir}" /usr/lib/wsl/lib/nvidia-smi'
```

### Configure the Node Runtime

Add the WSL driver directory to kind's existing OCI base specification. Containerd reads this file at startup, so restart it after the update:

```bash
podman exec gpu-offload-control-plane sh -c \
  'jq '\''if any(.mounts[]; .destination == "/usr/lib/wsl") then . else .mounts += [{"destination":"/usr/lib/wsl","type":"none","source":"/usr/lib/wsl","options":["rbind","ro","nosuid","nodev"]}] end'\'' /etc/containerd/cri-base.json > /etc/containerd/cri-base.json.new && mv /etc/containerd/cri-base.json.new /etc/containerd/cri-base.json'

podman exec gpu-offload-control-plane systemctl restart containerd
kubectl wait \
  --for=condition=Ready \
  node/gpu-offload-control-plane \
  --timeout=180s
```

This local runtime configuration makes the read-only WSL driver tree available to every container in the kind node. Do not use it as a production Kubernetes configuration.

### Register the WSL GPU

Load the pinned generic device plugin image into kind:

```bash
podman pull docker.io/squat/generic-device-plugin:0.2.0
podman save \
  --output /tmp/generic-device-plugin-0.2.0.tar \
  docker.io/squat/generic-device-plugin:0.2.0

kind load image-archive \
  /tmp/generic-device-plugin-0.2.0.tar \
  --name gpu-offload
```

Register `/dev/dxg` as one `nvidia.com/gpu` resource:

```bash
kubectl apply -f - <<'EOF'
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: wsl-gpu-device-plugin
  namespace: kube-system
spec:
  selector:
    matchLabels:
      app: wsl-gpu-device-plugin
  template:
    metadata:
      labels:
        app: wsl-gpu-device-plugin
    spec:
      priorityClassName: system-node-critical
      tolerations:
        - operator: Exists
      containers:
        - name: device-plugin
          image: docker.io/squat/generic-device-plugin@sha256:66c8d5c270eb2b721f1064c549b9b7898152a6d2f0163380a5d37dc7636c20ff
          imagePullPolicy: IfNotPresent
          args:
            - --domain=nvidia.com
            - --device={"name":"gpu","groups":[{"paths":[{"path":"/dev/dxg"}]}]}
          securityContext:
            privileged: true
          volumeMounts:
            - name: device-plugins
              mountPath: /var/lib/kubelet/device-plugins
            - name: dxg
              mountPath: /dev/dxg
      volumes:
        - name: device-plugins
          hostPath:
            path: /var/lib/kubelet/device-plugins
        - name: dxg
          hostPath:
            path: /dev/dxg
            type: CharDevice
EOF

kubectl rollout status daemonset/wsl-gpu-device-plugin \
  --namespace kube-system \
  --timeout=120s

kubectl get nodes \
  -o custom-columns='NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu'
```

Wait for the `GPU` column to report `1` before continuing.

### Verify Kubernetes GPU Access

Load the CUDA image into kind and run a pod that requests the registered resource:

```bash
podman pull docker.io/nvidia/cuda:12.8.1-base-ubuntu24.04
podman save \
  --output /tmp/nvidia-cuda-12.8.1.tar \
  docker.io/nvidia/cuda:12.8.1-base-ubuntu24.04

kind load image-archive \
  /tmp/nvidia-cuda-12.8.1.tar \
  --name gpu-offload

kubectl apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: wsl-gpu-check
spec:
  restartPolicy: Never
  containers:
    - name: cuda
      image: docker.io/nvidia/cuda:12.8.1-base-ubuntu24.04
      imagePullPolicy: IfNotPresent
      command: ["/bin/sh", "-c"]
      args:
        - |
          driver_dir=$(find /usr/lib/wsl/drivers -mindepth 1 -maxdepth 1 -type d | head -n 1)
          export LD_LIBRARY_PATH="/usr/lib/wsl/lib:${driver_dir}"
          test -c /dev/dxg
          /usr/lib/wsl/lib/nvidia-smi
      resources:
        limits:
          nvidia.com/gpu: "1"
EOF

kubectl wait pod/wsl-gpu-check \
  --for=jsonpath='{.status.phase}'=Succeeded \
  --timeout=120s
kubectl logs pod/wsl-gpu-check
kubectl delete pod/wsl-gpu-check
```

The log must list the NVIDIA adapter. Continue to the [NVIDIA offload](./02-first-cpu-offload.md#podman-kind-nvidia-on-wsl2).

## Troubleshooting

### kind selects another provider

Set the provider for every kind command:

```bash
export KIND_EXPERIMENTAL_PROVIDER=podman
```

### Podman cannot resolve the CDI device

Regenerate the system CDI file and verify its device names:

```bash
sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
nvidia-ctk cdi list
```

### Kubernetes reports no GPU capacity

Inspect the generic device plugin and the node resource state:

```bash
kubectl logs daemonset/wsl-gpu-device-plugin --namespace kube-system
kubectl describe node gpu-offload-control-plane
podman exec gpu-offload-control-plane ls -l /dev/dxg
```

The plugin log must show registration for `nvidia.com/gpu`, and `/dev/dxg` must exist in the node.

### The GPU pod cannot find WSL libraries

Confirm that the OCI base spec contains the read-only mount, then restart containerd:

```bash
podman exec gpu-offload-control-plane \
  jq '.mounts[] | select(.destination == "/usr/lib/wsl")' \
  /etc/containerd/cri-base.json

podman exec gpu-offload-control-plane systemctl restart containerd
kubectl wait \
  --for=condition=Ready \
  node/gpu-offload-control-plane \
  --timeout=180s
```

## Cleanup

Delete the selected local cluster:

```bash
export KIND_EXPERIMENTAL_PROVIDER=podman
kind delete cluster --name gpu-offload
rm -f /tmp/gpu-offload-kind.yaml
```
