# remote.yaml offload-spec schema

Schema for the `remote.yaml` offload specification that a workload's ConfigMap carries.
`remote.yaml` names the GPU stages, classes, and functions that execute transparently in
a server-stage pod. This schema is generic and embodiment-agnostic — it constrains no
specific policy, robot, or framework.

## Top-level keys

`remote.yaml` declares three top-level keys. Each maps offloadable Python symbols onto a
named GPU stage.

| Key             | Type               | Required | Meaning                                                               | Example                                                    |
|-----------------|--------------------|----------|-----------------------------------------------------------------------|------------------------------------------------------------|
| `serverstages`  | list of stage maps | Yes      | Named GPU worker pods that host offloaded classes and functions.      | one stage `gpu` with `nvidia.com/gpu: 1`                   |
| `remoteclasses` | list of class maps | No       | Fully-qualified Python classes whose method calls execute in a stage. | `mypackage.policy/Policy` → stage `gpu`                    |
| `remotefuncs`   | list of func maps  | No       | Fully-qualified Python functions that execute in a stage.             | `mypackage.checkpoint/Checkpoint/get_action` → stage `gpu` |

A workload that offloads at least one symbol declares `serverstages` plus at least one of
`remoteclasses` or `remotefuncs`.

## serverstages

A **stage** is a GPU worker pod that hosts the offloaded classes and functions. Each
`remoteclasses` and `remotefuncs` entry targets a stage by name through its `remoteloc`
field.

| Field       | Type   | Required | Meaning                                                                                      | Example                    |
|-------------|--------|----------|----------------------------------------------------------------------------------------------|----------------------------|
| `name`      | string | Yes      | Stage identifier referenced by `remoteloc` in class and function entries.                    | `gpu`                      |
| `perclient` | bool   | Yes      | `false`: one shared stage pod serves every client. `true`: a dedicated stage pod per client. | `false`                    |
| `resources` | map    | Yes      | Kubernetes resource requests/limits for the stage pod, including the GPU count.              | `limits.nvidia.com/gpu: 1` |

The `resources` map follows the standard Kubernetes container resources shape. GPU
allocation is expressed under `resources.limits` with the `nvidia.com/gpu` key.

```yaml
serverstages:
  - name: gpu
    perclient: false
    resources:
      limits:
        nvidia.com/gpu: 1
```

## remoteclasses

Each entry is a single-key map: the key is a fully-qualified class path, and its value
selects the target stage. Method calls on instances of the class execute transparently in
the stage pod — no application code change is required at the call site.

| Field       | Type   | Required | Meaning                                                     | Example                   |
|-------------|--------|----------|-------------------------------------------------------------|---------------------------|
| _(map key)_ | string | Yes      | Fully-qualified class path in `module.path/ClassName` form. | `mypackage.policy/Policy` |
| `remoteloc` | string | Yes      | `name` of the `serverstages` entry that hosts the class.    | `gpu`                     |

```yaml
remoteclasses:
  - "mypackage.policy/Policy":
      remoteloc: gpu
```

## remotefuncs

Each entry is a single-key map: the key is a fully-qualified function or method path, and
its value selects the target stage and declares instancing semantics. Calls to the
function execute transparently in the stage pod.

| Field            | Type   | Required | Meaning                                                                                                                                            | Example                                      |
|------------------|--------|----------|----------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------|
| _(map key)_      | string | Yes      | Fully-qualified path in `module.path/ClassName/method` or `module.path/function` form.                                                             | `mypackage.checkpoint/Checkpoint/get_action` |
| `singleinstance` | bool   | No       | `true`: the underlying object (e.g. a loaded model) is instantiated once and shared across all calls. Omit or set `false` for per-call instancing. | `true`                                       |
| `remoteloc`      | string | Yes      | `name` of the `serverstages` entry that hosts the function.                                                                                        | `gpu`                                        |

Set `singleinstance: true` on the function that loads a heavy resource so the model loads
once in the stage pod and every subsequent call reuses it. Leave it off for functions that
must not share state between calls.

```yaml
remotefuncs:
  - "mypackage.checkpoint/Checkpoint/load_model":
      singleinstance: true
      remoteloc: gpu
  - "mypackage.checkpoint/Checkpoint/get_action":
      remoteloc: gpu
```

## Minimal valid remote.yaml

The following is a complete, internally consistent `remote.yaml`. It declares one shared
GPU stage `gpu`, offloads one class, and offloads two functions — one that loads a model
once and shares it, one that runs per call. Every `remoteloc` references the declared
stage `name`.

```yaml
serverstages:
  - name: gpu
    perclient: false
    resources:
      limits:
        nvidia.com/gpu: 1
remoteclasses:
  - "mypackage.policy/Policy":
      remoteloc: gpu
remotefuncs:
  - "mypackage.checkpoint/Checkpoint/load_model":
      singleinstance: true
      remoteloc: gpu
  - "mypackage.checkpoint/Checkpoint/get_action":
      remoteloc: gpu
```

> [!NOTE]
> A workload opts into offloading with the label `xavier: "true"` and an annotation
> `xavierconfig` that points at a ConfigMap. That ConfigMap holds the `remote.yaml`
> documented here under its `data.remote.yaml` key. The offload opt-in contract —
> label, annotation, and ConfigMap wiring — is specified in
> [gpu-offload.specification.md](./gpu-offload.specification.md).

## Scheduling

No scheduling hints beyond `resources` appear in the `remote.yaml` body; pod placement
(node selectors, runtime class) is configured on the workload rather than in the offload
spec.
