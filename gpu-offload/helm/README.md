# GPU-Offload Helm Chart

Deploys the transparent GPU-offloading platform components — a mutating admission
webhook and a privileged node agent — that let opt-in workloads run their GPU stages
remotely. The chart is registry-parameterized and consumes prebuilt external images;
it does not build them.

## 📋 Prerequisites

| Requirement       | Detail                                                                       |
|-------------------|------------------------------------------------------------------------------|
| Kubernetes        | 1.27+ with admission webhooks enabled                                        |
| Helm              | 3.12+                                                                        |
| cert-manager      | Installed cluster-wide when `mutate.certManager.enabled` is `true` (default) |
| Offloading images | `xavier-mutate` and `pyremote` mirrored into your registry                   |
| Registry access   | Workload identity (preferred) or an image pull secret                        |

> [!IMPORTANT]
> This chart is inert without the external `xavier-mutate` and `pyremote` images. It
> carries the deployment topology only; the offloading engine ships as prebuilt
> images that you supply via `image.registry`.

## 🚀 Quick Start

```bash
helm install gpu-offload gpu-offload/helm/gpu-offload \
  --namespace gpu-offload --create-namespace \
  --set image.registry=example.azurecr.io \
  --set mutate.image.digest=sha256:<mutate-digest> \
  --set nodeAgent.image.digest=sha256:<pyremote-digest>
```

Render the manifests without installing to review them first:

```bash
helm template gpu-offload gpu-offload/helm/gpu-offload \
  --set image.registry=example.azurecr.io
```

## ⚙️ Configuration

| Value                         | Default                      | Description                                                                  |
|-------------------------------|------------------------------|------------------------------------------------------------------------------|
| `image.registry`              | `<your-registry>.azurecr.io` | Registry hosting the offloading images. Set to your registry.                |
| `image.pullPolicy`            | `IfNotPresent`               | Pull policy applied to every container.                                      |
| `imagePullSecrets`            | `[]`                         | Pull secret references. Prefer workload identity; leave empty when using it. |
| `mutate.image.repository`     | `xavier-mutate`              | Mutate controller image name within `image.registry`.                        |
| `mutate.image.tag`            | `""`                         | Mutable tag. Leave empty and prefer a digest.                                |
| `mutate.image.digest`         | `""`                         | `sha256:` digest pin. Wins over `tag` when set.                              |
| `mutate.webhookPort`          | `6443`                       | TLS port for the webhook Service and endpoint.                               |
| `mutate.logLevel`             | `warning`                    | Mutate controller log verbosity.                                             |
| `mutate.certManager.enabled`  | `true`                       | Provision webhook TLS and CA injection via cert-manager.                     |
| `mutate.certManager.duration` | `4320h`                      | Serving certificate validity window.                                         |
| `nodeAgent.image.repository`  | `pyremote`                   | Node agent image name within `image.registry`.                               |
| `nodeAgent.image.tag`         | `""`                         | Mutable tag. Leave empty and prefer a digest.                                |
| `nodeAgent.image.digest`      | `""`                         | `sha256:` digest pin. Wins over `tag` when set.                              |
| `libPath`                     | `/opt/xavier/lib`            | Host path where the node agent stages the client library.                    |
| `serverPort`                  | `30000`                      | GPU-stage server port.                                                       |
| `remoterPort`                 | `30001`                      | Client remoter port (exported as `REMOTERPORT`).                             |

## 🔑 External-image prerequisite

The chart references two real image names — `xavier-mutate` and `pyremote` — but only
through `image.registry`. Mirror both images into a registry you control, then point
`image.registry` at it. No internal registry FQDN is embedded in the chart.

```bash
# Example: mirror into your registry (source registry supplied out of band).
crane copy <source-registry>/xavier-mutate@sha256:<digest> \
  example.azurecr.io/xavier-mutate@sha256:<digest>
crane copy <source-registry>/pyremote@sha256:<digest> \
  example.azurecr.io/pyremote@sha256:<digest>
```

Grant the cluster pull access with workload identity where possible:

- Assign the `AcrPull` role to the cluster's managed identity (or kubelet identity).
- Configure a federated credential so pods authenticate without stored secrets.
- Leave `imagePullSecrets` empty.

When workload identity is unavailable, create an image pull secret out of band and
reference it by name in `imagePullSecrets`. Never inline registry credentials in
values files.

## 📌 Digest-pinning guidance

Pin both images to immutable `sha256:` digests rather than mutable tags. A digest is
tamper-evident and reproducible; a tag can be repointed after review.

- Set `mutate.image.digest` and `nodeAgent.image.digest`; leave the `tag` fields empty.
- When a digest is set it takes precedence over any tag.
- When neither digest nor tag is set, the runtime resolves the registry default
  (typically `:latest`) — acceptable only for throwaway evaluation.

Resolve a digest from a tag before pinning:

```bash
crane digest example.azurecr.io/xavier-mutate:<tag>
```

## ⚠️ Safety caveat

Offloading is opt-in: only workloads labeled `xavier: "true"` are mutated. Offloading a
control-loop `get_action` call across machines injects network latency and jitter into a
15-50 Hz loop, which is a stability and safety risk. Same-node offload is safe;
cross-machine offload of control-loop functions requires explicit review.

## 🏗️ Components

| Template                              | Kind                                    | Purpose                                                          |
|---------------------------------------|-----------------------------------------|------------------------------------------------------------------|
| `templates/mutate-deployment.yaml`    | Deployment, Service, RBAC, cert-manager | Runs the mutate controller and its serving certificate.          |
| `templates/mutating-webhook.yaml`     | MutatingWebhookConfiguration            | Registers the `/mutate` webhook, selected on the `xavier` label. |
| `templates/node-agent-daemonset.yaml` | DaemonSet                               | Stages the client library to each node's `libPath`.              |

---

This reference architecture originates with the Microsoft Research Xavier team, whose
`xavier-tutorial` project defined the transparent GPU-offloading contract and
deployment topology adapted here. This repository carries the consumer-facing contract
and deployment scaffolding only; the offloading engine ships as prebuilt external
images.
