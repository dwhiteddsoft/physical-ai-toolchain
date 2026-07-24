# Open items

These are follow-up items surfaced during integration. They are recorded for later
action by the Microsoft Research Xavier team and by this repository — they are **not**
acted on as part of this integration. See [PROVENANCE.md](./PROVENANCE.md) for the
adaptation rules and [AUDIT.md](./AUDIT.md) for the sanitization result.

## Images and registry access

- **Digest-stable, AcrPull-accessible images.** The offloading engine ships as prebuilt
  external images (`xavier-mutate`, `pyremote`). The source project referenced mutable
  per-build tags. Before any real deployment, guarantee **AcrPull** access to the
  hosting registry and pin images by **digest** (or hand over a digest-pinned mirror)
  so that `helm/gpu-offload/values.yaml` can reference immutable references.
- **Upstream image build.** The repository that builds the four platform images
  (`xavier-mutate`, `pyremote`, `ml_proxy`, `watcher`) is **not** present in the source
  reference project. Identify and document the upstream build source so the images can
  be reproduced, scanned, and released.

## Out-of-scope capabilities

- **`ml_proxy` / MCP remain out of scope.** The `ml_proxy` component and its MCP server
  are an orthogonal agentic-control capability that depends on `ml_proxy` and Microsoft
  Foundry. They are intentionally excluded here and could become a **separate future
  example** aligned to the toolchain's agentic-workflows story, rather than being folded
  into GPU offloading.

## Carry mechanism

- **Upstream the LeRobot ROS 2 bridge.** The ROS 2 bridge modules under
  [examples/so101-real-hardware/ros2_bridge](./examples/so101-real-hardware/ros2_bridge)
  are vendored (Option A). A follow-up should evaluate upstreaming the bridge to the
  `lerobot` project (task 04 Option C) so this domain can depend on it directly instead
  of vendoring a copy. See
  [examples/so101-real-hardware/CARRY-DECISION.md](./examples/so101-real-hardware/CARRY-DECISION.md).

## Validation

- **Real-hardware example is not runtime-verified.** The SO-101 example is authored and
  lint-validated only. A future task should validate it end-to-end on real hardware once
  the prebuilt images are available, and record the results.
