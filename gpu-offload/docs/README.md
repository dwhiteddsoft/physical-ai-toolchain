---
title: GPU Offload First Run
description: Start GPU offload from a local Kubernetes environment
ms.date: 2026-08-10
ms.topic: get-started
---

# GPU Offload First Run

Build the GPU-offload components locally and run a complete CPU-backed remote function call before adding GPU infrastructure.

## Start Here

1. [Set up local Kubernetes](./01-local-kubernetes-setup.md).
2. [Run the first CPU offload](./02-first-cpu-offload.md).

The first run uses CPU resources intentionally. It validates image building, admission mutation, server-stage creation, peer discovery, transport, and remote execution without requiring GPU hardware.
