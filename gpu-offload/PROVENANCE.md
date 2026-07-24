# Provenance and attribution

This `gpu-offload` domain adapts a GPU-offloading reference architecture: it carries the
offloading **contract and deployment topology** as documented reference material, not the
offloading engine itself. The engine ships as prebuilt external images. The domain is
delivered under this repository's MIT license.

The bundled ROS 2 bridge under `examples/so101-real-hardware/ros2_bridge/` derives from
the [LeRobot](https://github.com/huggingface/lerobot) project and stays under its Apache
2.0 license, as recorded in those files' headers.

## SPDX header block

Every source file begins with a two-line header: an SPDX identifier and an attribution
line, using the comment syntax for the file's language.

Python, shell, and YAML:

```yaml
# SPDX-License-Identifier: MIT
# Adapted from an upstream GPU-offloading reference implementation.
```

Terraform / HCL and other `//`-comment languages:

```hcl
// SPDX-License-Identifier: MIT
// Adapted from an upstream GPU-offloading reference implementation.
```

Markdown documents do not carry an SPDX comment.

## Image names

The image names `xavier-mutate` and `pyremote` are the prebuilt offloading-engine images
this domain consumes. Always reference them through a parameterized registry
(`{{ .Values.image.registry }}/...`) rather than a hard-coded registry.
