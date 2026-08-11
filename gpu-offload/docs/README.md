---
title: GPU Offload First Run
description: Start CPU-only or WSL NVIDIA GPU offload with Podman and kind
ms.date: 2026-08-11
ms.topic: get-started
---

Build the GPU-offload components with rootless Podman and run a complete remote function call on a Podman-backed kind cluster. Follow the CPU-only path for pipeline verification or the WSL2 NVIDIA path for device-backed offload verification.

## 🚀 Start Here

1. [Set up Podman and kind](./01-local-kubernetes-setup.md).
2. Select [Podman kind CPU Only](./02-first-local-offload.md#podman-kind-cpu-only) or [Podman kind NVIDIA on WSL2](./02-first-local-offload.md#podman-kind-nvidia-on-wsl2).

Both paths validate Podman image building, admission mutation, server-stage creation, peer discovery, transport, and remote execution. The NVIDIA path also verifies Podman CDI, Kubernetes GPU capacity, `/dev/dxg` allocation to the generated server, and execution from that server pod.

## 📋 Path Selection

| Path                       | Hardware                                      | Verification                                                                   |
|----------------------------|-----------------------------------------------|--------------------------------------------------------------------------------|
| Podman kind CPU Only       | Any supported Linux or WSL2 host              | Remote execution in a CPU server-stage pod                                     |
| Podman kind NVIDIA on WSL2 | NVIDIA GPU exposed to WSL2 through `/dev/dxg` | Remote execution in a server-stage pod allocated one `nvidia.com/gpu` resource |

The NVIDIA setup mounts the WSL GPU device and driver files into the kind node, registers `/dev/dxg` with a pinned generic device plugin, and verifies `nvidia-smi` in a GPU-allocated pod before deploying the offload example.
