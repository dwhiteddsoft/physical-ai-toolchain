# Sanitization and secrets audit

This report records the sanitization and secrets audit performed over the entire
`gpu-offload/` tree before the domain was integrated into `physical-ai-toolchain`.
It complements [PROVENANCE.md](./PROVENANCE.md), which defines the attribution,
SPDX, and denylist rules this audit enforces.

## Scope

- **Tree audited:** `gpu-offload/` (29 tracked files after removing redundant placeholders).
- **Excluded:** transient local virtual environments (`**/.venv/**`).
- **Source of adapted material:** the internal Microsoft Research "xavier-tutorial"
  GPU-offloading reference architecture. The source tree was treated as read-only.

## File inventory

| Type             | Count | Notes                                                         |
|------------------|-------|---------------------------------------------------------------|
| Markdown (`md`)  | 10    | Specs, READMEs, provenance, carry decision, open items, audit |
| Python (`py`)    | 9     | Vendored ROS 2 bridge modules and the SO-101 offload example  |
| YAML (`yaml`)    | 8     | Helm chart/values/templates, example manifests, `remote.yaml` |
| Template (`tpl`) | 1     | Helm `_helpers.tpl`                                           |
| Text (`txt`)     | 1     | Helm `NOTES.txt`                                              |

## Patterns checked

The following denylist patterns were swept across the whole tree.

| Pattern class               | Regex / literal probed                                                          | Result            |
|-----------------------------|---------------------------------------------------------------------------------|-------------------|
| Internal ACR registry name  | the internal reference-platform ACR registry name and its `.azurecr.io` FQDN    | 0 hits            |
| Azure resource GUIDs        | `[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}`                  | 0 hits            |
| Internal program references | internal compliance, CI/build-system, network, remote, and hostname identifiers | 0 hits            |
| Mutable per-build image tag | the source project's mutable image tag                                          | 0 hits            |
| Secret markers              | `PASSWORD=`, `SECRET=`, `TOKEN=`, `API_KEY`, `-----BEGIN`                       | 0 hits            |
| Non-placeholder registries  | `[a-z0-9-]+\.azurecr\.io`                                                       | placeholders only |

### Registry references

Every `.azurecr.io` occurrence resolves to a documented, non-internal placeholder
(`<your-registry>.azurecr.io` in Helm values and `example.azurecr.io` in usage
examples). No internal registry FQDN or bare registry name is present.

### Provenance document self-check

The denylist table in [PROVENANCE.md](./PROVENANCE.md) intentionally describes the
categories of values to sanitize. It was reworded to name only generic categories
(for example "internal compliance, CI/build-system, network, remote, and hostname
references") rather than embedding any specific internal program codename, registry
name, or mutable tag literal, so the shipped provenance guidance itself contains no
denylisted value.

## Secrets from the source environment file

The source project's `scripts/.env` file was **not** copied in any form. Its key
names were enumerated (15 keys) and each was searched for across `gpu-offload/`:

- Zero secret **values** from the source environment file appear anywhere in the tree.
- Two generic key-name substrings surfaced as coincidental matches inside
  [examples/so101-real-hardware/ros2_bridge/examples/so101_ros/run_vla.py](./examples/so101-real-hardware/ros2_bridge/examples/so101_ros/run_vla.py):
  - `FPS` matched the local constant `DEFAULT_FPS = 10`.
  - `REPO_ID` matched the CLI variable `DATASET_REPO_ID`, whose default is the
    non-secret literal `"local/lift_cube_abs_joint"`.

Both are ordinary, self-contained identifiers and carry no data derived from the
source environment file.

**Statement:** No secrets were copied from the source `scripts/.env` file. No
credentials, tokens, keys, or PEM private-key material are present in `gpu-offload/`.

## Attribution and license verification

- Every Python (`.py`), shell (`.sh`), and Helm template (`.tpl`, `templates/*.yaml`)
  file carries the required `SPDX-License-Identifier: MIT` header **and** the
  "Adapted from ... xavier-tutorial" attribution line.
- No file asserts a license other than MIT, and no third-party non-MIT license text
  was introduced.
- Redundant `.gitkeep` placeholders were removed from `specifications/` and
  `examples/` once those directories held real content.

## Result

The `gpu-offload/` tree passes the sanitization and secrets audit: zero denylist
hits, zero copied secrets, complete SPDX/attribution coverage, and MIT-only
licensing.
