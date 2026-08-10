---
title: GPU Offload TODO
description: Track pending GPU-offload implementation work
ms.date: 2026-08-10
ms.topic: reference
---

# GPU Offload TODO

Track implementation work that has been identified but not completed. Remove each task after its code changes and validation are merged.

## Bound Log Rollover Failure Handling

Target file: [`runtime/remoter/simplelog.py`](../runtime/remoter/simplelog.py)

The logger invokes `lsof` during process startup to avoid rotating a log file that another process has open. A missing `lsof` executable now returns `False`, but other subprocess and filesystem failures can still block startup indefinitely.

### Failure Modes

- `subprocess.run()` has no timeout. A stalled `lsof` process stalls logger and application initialization.
- `rollover()` catches every exception and retries with a new filename in an unbounded loop.
- Persistent filesystem errors, including a read-only directory, insufficient permissions, exhausted storage, or rename failures, cause infinite retries.
- An execution error other than `FileNotFoundError`, such as `PermissionError`, enters the same unbounded retry loop.
- The current implementation provides no final error identifying why rollover could not complete.

### Implementation

- [ ] Add a short timeout to the `lsof` invocation.
- [ ] Treat `FileNotFoundError`, `subprocess.TimeoutExpired`, and other expected `OSError` failures as an unavailable `lsof` check.
- [ ] Preserve argument-list invocation and continue to avoid `shell=True`.
- [ ] Replace the unbounded rollover loop with a finite number of filename attempts.
- [ ] Raise a clear exception containing the original failure after all attempts are exhausted.
- [ ] Preserve the existing log retention behavior when rollover succeeds.
- [ ] Remove the duplicate `os` import while editing the module.

### Acceptance Criteria

- Application startup completes when `lsof` is not installed.
- Application startup does not wait indefinitely when `lsof` stalls.
- A persistent filesystem failure exits rollover after a bounded number of attempts.
- The final exception identifies the target log path and preserves the underlying error as its cause.
- Existing log files continue to rotate according to the `keep` value.
- Paths are passed as subprocess arguments without shell interpolation.

### Validation

- [ ] Add focused tests that replace `subprocess.run()` with missing-command, timeout, open-file, and closed-file outcomes.
- [ ] Add focused tests for successful rollover and persistent filesystem failure.
- [ ] Verify the persistent-failure test completes within a fixed test timeout.
- [ ] Run the GPU-offload runtime test suite.
- [ ] Start the first-run client in the slim container image, where `lsof` is absent, and verify remote execution reaches the server pod.
