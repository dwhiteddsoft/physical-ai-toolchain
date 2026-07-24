# GPU Offload

Transparent GPU offloading for robot inference: run a light control/main container next
to the robot while heavy inference executes in a GPU server-stage pod, with no
application code change. Offloading is opt-in through a workload label and annotation
contract. This domain carries the offloading **contract and deployment topology**; the
offloading engine ships as prebuilt external images.

## 🧭 Overview

A workload opts into offloading with the label `xavier: "true"` and an annotation
`xavierconfig` that points at a ConfigMap holding a `remote.yaml` offload spec. A
mutating webhook injects a GPU **server-stage** pod alongside the main container, and a
node-agent DaemonSet stages the remoting library onto the node. Fully-qualified Python
classes and functions named in `remote.yaml` execute transparently in the server-stage
pod.

## 📋 Prerequisites

- A Kubernetes cluster with GPU nodes and the NVIDIA device plugin available.
- The offloading engine images (`xavier-mutate` and `pyremote`), published to a
  registry your cluster can pull from. This domain does **not** build these images;
  supply them and set the registry through the Helm value `image.registry` (see
  [OPEN-ITEMS.md](./OPEN-ITEMS.md) for the digest-pinning and registry-access follow-ups).
- Helm 3 and `kubectl` configured against the target cluster.
- A robot control workload that can be annotated to opt into offloading (the bundled
  example targets an SO-101 arm over ROS 2).

## 🚀 Quick Start

1. Install the offloading control plane with the parameterized registry:

   ```bash
   helm install gpu-offload ./helm/gpu-offload \
     --set image.registry=<your-registry>.azurecr.io
   ```

2. Follow the end-to-end walkthrough in the SO-101 real-hardware example, which wires a
   control workload to a GPU server-stage pod via a `remote.yaml` offload spec:
   [examples/so101-real-hardware/README.md](./examples/so101-real-hardware/README.md).

See [helm/README.md](./helm/README.md) for the full chart values and digest-pinning
guidance.

## 🗂️ Layout

```text
gpu-offload/
├── specifications/            # Offload contract and remote.yaml schema
│   ├── gpu-offload.specification.md
│   └── remote-spec-schema.md
├── helm/                      # Parameterized deployable scaffolding
│   ├── README.md
│   └── gpu-offload/           # Chart: webhook, mutation, node-agent DaemonSet
└── examples/
    └── so101-real-hardware/   # SO-101 offload example (not runtime-verified)
        ├── remote.yaml
        ├── manifests/         # ConfigMap + control workload
        └── ros2_bridge/       # Vendored LeRobot ROS 2 bridge (lint-only reference)
```

## ⚠️ Scope & limitations

- No Isaac Sim / LeIsaac content.
- No `ml_proxy`, `watcher`, XApp CRD, or MCP server.
- The offloading engine images are an external prerequisite; this domain does not build
  them.
- The real-hardware example is authored and lint-validated, **not** runtime-verified.

## 🧩 Tier mapping

GPU offloading is a cluster-level deployment-topology capability: a mutating webhook, a
node-agent DaemonSet, and injected GPU server-stage pods. It therefore aligns with the
**T3–T4-style deployment and fleet-delivery concerns** described in the canonical
[tier-model.md](../docs/design/tier-model.md) — single-site declarative Kubernetes
deployment (T3 — Production) extending to multi-site scale (T4 — Scale). It is not a
fleet-intelligence (T5) capability: it delivers and runs inference topology and performs
no drift detection, retraining, or aggregate analytics. This mapping references the
canonical tiers rather than redefining them; consult the tier model for authoritative
tier boundaries and vocabulary.
