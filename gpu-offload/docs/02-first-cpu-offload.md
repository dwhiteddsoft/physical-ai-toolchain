---
title: First CPU Offload
description: Build and run a complete CPU-backed remote function example
ms.date: 2026-08-10
ms.topic: tutorial
---

# First CPU Offload

Run a client function transparently in a separate server-stage pod. The example squares four integers and returns the hostname of the pod that executed the function.

## Prerequisites

Complete [Local Kubernetes Setup](./01-local-kubernetes-setup.md). Run all commands from the repository root.

## Build Images

Build the admission controller and the shared client/server runtime image:

```bash
docker build \
  --file gpu-offload/controller/Containerfile \
  --tag xavier-mutate:local \
  gpu-offload/controller

docker build \
  --file gpu-offload/examples/first-run/Containerfile \
  --tag gpu-offload-first-run:local \
  .

docker image inspect xavier-mutate:local gpu-offload-first-run:local >/dev/null

docker save xavier-mutate:local gpu-offload-first-run:local | \
  docker exec --interactive desktop-control-plane \
  ctr --namespace k8s.io images import --all-platforms -
```

Docker Desktop Kubernetes uses a containerd image store separate from the Docker image store. Import both images into the `desktop-control-plane` node before installing the chart. The example sets `imagePullPolicy: Never` so Kubernetes uses these local images and does not contact a registry.

## Install the Controller

Install the chart with the local controller image:

```bash
helm upgrade --install gpu-offload gpu-offload/helm/gpu-offload \
  --namespace gpu-offload \
  --create-namespace \
  --set image.registry="" \
  --set mutate.image.repository=xavier-mutate \
  --set mutate.image.tag=local \
  --set image.pullPolicy=Never

kubectl rollout status deployment/gpu-offload-mutate \
  --namespace gpu-offload \
  --timeout=120s
```

## Run the Example

Apply the namespace, runtime RBAC, offload configuration, and client Deployment:

```bash
kubectl apply -f gpu-offload/examples/first-run/manifests.yaml

kubectl rollout status deployment/first-run-client \
  --namespace gpu-offload-demo \
  --timeout=120s

kubectl rollout status deployment/first-run-client-remote-server-cpu \
  --namespace gpu-offload-demo \
  --timeout=120s
```

The controller creates `first-run-client-remote-server-cpu`; it is not declared directly in the example manifest.

## Verify Remote Execution

List both pods:

```bash
kubectl get pods --namespace gpu-offload-demo -o wide
```

Read the client output:

```bash
kubectl logs deployment/first-run-client \
  --namespace gpu-offload-demo \
  --follow
```

Successful output has this shape:

```json
{"executed_by": "first-run-client-remote-server-cpu-...", "predictions": [1, 4, 9, 16]}
```

The `executed_by` value must start with `first-run-client-remote-server-cpu`, not `first-run-client`. This proves that `demo_model.predict` ran in the remote server-stage pod.

## Inspect the Offload

Confirm that admission injected the runtime configuration:

```bash
kubectl get deployment first-run-client \
  --namespace gpu-offload-demo \
  --output jsonpath='{.spec.template.spec.containers[0].env}'
```

Inspect controller and server logs:

```bash
kubectl logs deployment/gpu-offload-mutate --namespace gpu-offload
kubectl logs deployment/first-run-client-remote-server-cpu --namespace gpu-offload-demo
```

## Cleanup

Remove the example and controller:

```bash
kubectl delete -f gpu-offload/examples/first-run/manifests.yaml
helm uninstall gpu-offload --namespace gpu-offload
kubectl delete namespace gpu-offload
```

## Next Step

Replace `demo_model.predict` with a model inference function after this example succeeds. Build the model and runtime into the same image, then update `serverimage` in `remote.yaml`.

For NVIDIA, add a GPU limit to the server stage only after the cluster advertises GPU capacity:

```yaml
resources:
  limits:
    nvidia.com/gpu: 1
```
