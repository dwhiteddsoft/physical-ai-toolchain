---
title: Local Kubernetes Setup
description: Prepare Docker Desktop Kubernetes for the GPU offload first run
ms.date: 2026-08-10
ms.topic: get-started
---

# Local Kubernetes Setup

Prepare a local Kubernetes cluster for the CPU-backed GPU-offload first run. These steps target WSL2 with Docker Desktop Kubernetes.

## Prerequisites

| Tool | Supported version | Verify |
|------|-------------------|--------|
| WSL | WSL2 | `uname -r` contains `microsoft-standard-WSL2` |
| Docker Desktop | 4.34 or later | `docker version` |
| Docker Engine | 27 or later | `docker version --format '{{.Server.Version}}'` |
| Kubernetes | 1.27 or later | `kubectl version` |
| kubectl | Within one minor version of the cluster | `kubectl version` |
| Helm | 3.12 or later | `helm version` |
| mise | Current stable | `mise --version` |

The validated development environment uses WSL2 on Ubuntu 24.04, Docker Desktop 4.86, Docker Engine 29.7, and Kubernetes 1.36.

## Enable Kubernetes

1. Open Docker Desktop on Windows.
2. Open **Settings > Kubernetes**.
3. Enable Kubernetes and wait for the status indicator to report running.
4. Open the WSL terminal at the repository root.

Verify Docker and Kubernetes:

```bash
docker run --rm hello-world
kubectl config use-context docker-desktop
kubectl cluster-info
kubectl get nodes
```

The node must report `Ready`. GPU capacity is not required for the first run.

## Install Helm

Install Helm through mise:

```bash
mise install helm@3
mise use --global helm@3
helm version
```

Render the chart before building images:

```bash
helm template gpu-offload gpu-offload/helm/gpu-offload \
  --namespace gpu-offload \
  --set image.registry=local
```

## CPU-Only Configuration

Do not install a GPU device plugin. The first-run manifest requests CPU and memory only. Kubernetes schedules both the client and remote server on the Docker Desktop node.

Confirm that CPU containers run:

```bash
docker run --rm alpine:3.22 sh -c 'uname -m; echo CPU-only container works'
```

Continue to [Run the First CPU Offload](./02-first-cpu-offload.md).

## NVIDIA Setup

> [!NOTE]
> NVIDIA setup is a placeholder. Complete and validate this section on an NVIDIA-backed WSL2 or Linux host before using it as an installation procedure.

An NVIDIA-backed setup requires a supported NVIDIA GPU, a current Windows or Linux NVIDIA driver, NVIDIA Container Toolkit support in Docker, and the NVIDIA Kubernetes device plugin or GPU Operator. The completed procedure must validate both commands:

```bash
docker run --rm --gpus all nvidia/cuda:<validated-tag> nvidia-smi
kubectl get nodes -o custom-columns='NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu'
```

Do not add `nvidia.com/gpu` resource limits until Kubernetes reports a positive allocatable value.

## Troubleshooting

### Docker works but Kubernetes does not

Confirm the active context and reset Kubernetes from Docker Desktop when the `docker-desktop` context is absent:

```bash
kubectl config get-contexts
kubectl config use-context docker-desktop
kubectl cluster-info
```

### Docker reports no GPU adapters

Continue with the CPU first run. The NVIDIA runtime cannot create GPU containers without an NVIDIA adapter visible to WSL2.
