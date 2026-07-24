# GPU Offload Contract

Authoritative description of the opt-in GPU-offloading contract a workload consumes,
independent of any specific robot or demo. This document specifies the contract this
domain consumes; it does not describe the closed offloading engine beyond the
observable, consumer-facing behavior.

## Purpose

Transparent GPU offloading runs a light control/main container next to the robot while
heavy inference executes in a GPU **server-stage** pod. Fully-qualified Python classes
and functions named in an offload spec execute in the server-stage pod instead of the
main container, with no application code change. The main container calls its policy as
if it ran locally; the platform intercepts the named symbols and routes their execution
to the GPU pod.

This separation keeps the robot-facing control container lightweight and schedulable on
non-GPU hardware, while GPU capacity is reserved for the inference stages that need it.

## Opt-in mechanism

A workload opts in through three signals. All three are required; omitting any one
disables offloading for that workload.

| Signal                    | Location                                    | Value                                                   | Role                                                                            |
|---------------------------|---------------------------------------------|---------------------------------------------------------|---------------------------------------------------------------------------------|
| Label `xavier`            | Workload metadata and pod template metadata | `"true"` (also accepts `True`, `TRUE`, `1`)             | Selects the workload for the mutating webhook                                   |
| Annotation `xavierconfig` | Workload metadata                           | Inline config referencing the offload ConfigMap by name | Points the platform at the `remote.yaml` offload spec and declares injected env |
| Env `REMOTERPORT`         | Main container                              | Server-stage port (for example `30000`)                 | Tells the main container where to reach the remoting server                     |

The `xavierconfig` annotation references a ConfigMap that holds the `remote.yaml`
offload spec and lists environment variables to inject into the workload. The offload
spec schema is defined in [remote-spec-schema.md](./remote-spec-schema.md).

```yaml
metadata:
  labels:
    xavier: "true"
  annotations:
    xavierconfig: |
      remoteablecm: <offload-configmap-name>
      env:
        - name: REMOTERPORT
          value: "30001"
```

## Runtime topology

The mutating webhook injects a GPU server-stage pod alongside the main container. A
node-agent DaemonSet stages the remoting library onto each node so the main container
can load it without shipping it in the application image.

| Component            | Origin                    | Responsibility                                                                                     |
|----------------------|---------------------------|----------------------------------------------------------------------------------------------------|
| Main container       | Consumer workload         | Runs the control loop; calls offloaded symbols through the remoting library                        |
| Server-stage pod     | Injected by the webhook   | Holds GPU resources (for example `nvidia.com/gpu: 1`) and executes offloaded classes and functions |
| Node-agent DaemonSet | Platform (prebuilt image) | Stages the remoting library to `/opt/xavier/lib` (`libPath`) on every node                         |
| Mutating webhook     | Platform (prebuilt image) | Matches the `xavier` label and injects the server-stage pod and wiring                             |

Two ports carry offload traffic:

| Port          | Default | Purpose                                                             |
|---------------|---------|---------------------------------------------------------------------|
| `serverPort`  | `30000` | Remoting server inside the server-stage pod                         |
| `remoterPort` | `30001` | Remoter endpoint the main container connects to (env `REMOTERPORT`) |

The remoting library is staged to `/opt/xavier/lib` on the host and made available to
the main container by the node-agent; the workload does not build or vendor it.

## What you provide vs. what the platform provides

The consumer owns the opt-in surface. The platform owns the engine, delivered as
prebuilt external images.

| Responsibility                                        | Provided by consumer | Provided by platform |
|-------------------------------------------------------|----------------------|----------------------|
| Workload label `xavier: "true"`                       | Yes                  | —                    |
| Annotation `xavierconfig`                             | Yes                  | —                    |
| Offload ConfigMap holding `remote.yaml`               | Yes                  | —                    |
| Env `REMOTERPORT` on the main container               | Yes                  | —                    |
| Choice of `serverPort` / `remoterPort`                | Yes                  | —                    |
| Mutating webhook that injects the server-stage pod    | —                    | Yes (prebuilt image) |
| Node-agent DaemonSet that stages the remoting library | —                    | Yes (prebuilt image) |
| Remoting library at `/opt/xavier/lib`                 | —                    | Yes                  |
| GPU scheduling of the server-stage pod                | —                    | Yes                  |

The platform images are an external prerequisite pulled from a parameterized registry.
This domain does not build them.

## Safety and performance

Offloading a symbol moves its execution off the main container. When the server-stage
pod runs on a different machine, every call to that symbol crosses the network.

> [!WARNING]
> Cross-machine offload of a control-loop call such as `get_action` injects network
> latency and jitter into a 15–50 Hz control loop. Round-trip variance on each cycle
> degrades closed-loop stability and can create a safety hazard on real hardware.
> Offload closed-loop control calls to a **same-node** server-stage pod only. Reserve
> cross-machine offload for non-real-time stages (for example one-shot model loading or
> batch inference) where added latency does not enter the control loop.

For closed-loop control, keep the server-stage pod on the same node as the main
container so offload traffic stays on the loopback or host network rather than the
cluster fabric.

## Cross-reference

See [remote-spec-schema.md](./remote-spec-schema.md) for the `remote.yaml` schema:
`serverstages`, `remoteclasses`, and `remotefuncs`, including the `singleinstance`
flag.
