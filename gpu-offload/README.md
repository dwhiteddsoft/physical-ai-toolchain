---
title: GPU Offload (Xavier) Integration
description: Transparent GPU offloading for robot inference
ms.date: 2026-08-10
ms.topic: overview
---

Transparent GPU offloading for robot inference: run a lightweight control container
next to the robot while heavy inference executes in a GPU server-stage pod. Offloading
is opt-in through workload label and annotation.

## 📋 Prerequisites

| Requirement | Minimum |
|---|---|
| Kubernetes cluster | GPU nodes with NVIDIA device plugin |
| Container images | `xavier-mutate` and `pyremote` in accessible registry |
| Tools | Helm 3 and `kubectl` configured |
| Python (controller tests) | 3.12 |
| Podman (local development) | Latest stable |

## 🚀 Quick Start (cluster)

1. Install the control plane:

   ```bash
   helm install gpu-offload ./helm/gpu-offload \
     --set image.registry=<your-registry>.azurecr.io
   ```

2. Add the `xavier: "true"` label and annotate workloads with `xavierconfig` pointing
   to a ConfigMap holding `remote.yaml`.

3. See [examples/so101-real-hardware/README.md](./examples/so101-real-hardware/README.md)
   for an end-to-end example (SO-101 arm with ROS 2 bridge)

## ⚙️ Configuration

Workload opt-in requires three signals:

| Signal | Location | Value | Purpose |
|---|---|---|---|
| Label `xavier` | Pod metadata | `"true"` | Select for mutation |
| Annotation `xavierconfig` | Workload metadata | ConfigMap name | Reference remote.yaml |
| Env `REMOTERPORT` | Main container | Port (e.g. 30001) | Server endpoint |

The `xavierconfig` annotation points to a ConfigMap containing `remote.yaml`. See
[specifications/remote-spec-schema.md](./specifications/remote-spec-schema.md) for
schema documentation.

## 🏗️ Architecture

Controller-based mutation that watches Pods, Deployments, Jobs, and StatefulSets.
When a workload carries the opt-in signals, the controller:

1. Adds a ConfigMap volume mount for remote.yaml
2. Injects standard environment variables
3. Creates or reconciles server Deployments from configured server stages
4. Adds a readiness probe to generated server containers
5. Does not add hostPath volumes, host namespaces, or privileged contexts

Application and server images must contain the runtime SDK from `runtime/`.

## 📦 Repository Structure

| Path | Content |
|---|---|
| `controller/` | Mutation controller (Python) |
| `helm/gpu-offload/` | Helm chart for control plane |
| `runtime/` | Xavier remoting SDK with MessagePack transport |
| `specifications/` | Remote.yaml schema and opt-in contract |
| `examples/so101-real-hardware/` | SO-101 end-to-end example |

Additional reference documents:

- [XAVIER-PORTING.md](./XAVIER-PORTING.md): porting decisions and deviations
- [PROVENANCE.md](./PROVENANCE.md): upstream snapshot and licensing

## 📤 Implementation Status

| Feature | Status | Notes |
|---|---|---|
| Controller mutation | Implemented | Label-selected admission with annotation configuration |
| ConfigMap volume mount | Implemented | Read-only, mounted at /xavierconfig |
| Env var injection | Implemented | REMOTER_CONFIG, downward API fields |
| Server readiness probe | Implemented | Checks /ready.txt written by the runtime |
| MessagePack codec | Implemented | Versioned envelope and explicit adapters |
| Server deployment generation | Implemented | Supports global and per-stage settings |
| Per-client deployments | Implemented | Reconciled from admitted client Pods |

## ⚠️ Scope

This domain provides the offload contract, controller, runtime SDK, deployment
scaffolding, and examples. The real-hardware example is reference material; adapt it
to your hardware and build the SDK into both application and server images.

## 🧩 Tier Model

GPU offloading aligns with T3–T4 deployment topology concerns (single-site Kubernetes
to multi-site scale). It is NOT a T5 fleet-intelligence capability. See
[docs/design/tier-model.md](../docs/design/tier-model.md) for authoritative tier
definitions.

## 🔍 Troubleshooting

### Mutation does not occur

Verify the workload has label `xavier: "true"`, annotation
`xavierconfig` referencing a valid ConfigMap, and `REMOTERPORT` in its runtime container.

### Server-stage pod fails to start

Check that the server image is available from the configured registry and GPU nodes
have available capacity.
