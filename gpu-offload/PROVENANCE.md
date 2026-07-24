# Provenance and attribution

This directory adapts the **GPU-offloading reference architecture** from the internal
Microsoft Research `xavier-tutorial` project. This repository carries the offloading
**contract and deployment topology** as documented reference material — not the closed
offloading engine. The `gpu-offload` domain is delivered under this repository's MIT
license with Legal/OSPO clearance recorded by the integrator.

## SPDX header block

Every new source file MUST begin with a two-line header: an SPDX identifier and an
attribution line. Use the comment syntax for the file's language.

Python, shell, and YAML:

```yaml
# SPDX-License-Identifier: MIT
# Adapted from Microsoft Research "xavier-tutorial" (GPU-offloading reference architecture).
```

Terraform / HCL and other `//`-comment languages:

```hcl
// SPDX-License-Identifier: MIT
// Adapted from Microsoft Research "xavier-tutorial" (GPU-offloading reference architecture).
```

Markdown documents carry attribution as a footer line (see the next section) rather
than an SPDX comment.

## Attribution paragraph

Place the following attribution in every example README, either inline or as a footer:

> This reference architecture originates with the Microsoft Research Xavier team, whose
> `xavier-tutorial` project defined the transparent GPU-offloading contract and
> deployment topology adapted here. This repository carries the consumer-facing contract
> and deployment scaffolding only; the offloading engine ships as prebuilt external
> images.

## Sanitization denylist

The following identifiers MUST NOT appear in any file created under `gpu-offload/` (or
anywhere else in this repository). Replace each with the noted placeholder or omit it.

| Category                    | Denylisted value                                                                                                                 | Replacement                                           |
|-----------------------------|----------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------|
| Internal ACR registry       | the internal reference-platform ACR registry FQDN (`<internal-name>.azurecr.io`) and its bare registry name                      | Helm value / placeholder `<your-registry>.azurecr.io` |
| Azure identifiers           | subscription IDs, tenant IDs, resource GUIDs                                                                                     | omit; use placeholders                                |
| Mutable image tags          | mutable per-build image tags                                                                                                     | parameterize the tag; recommend digest pinning        |
| Internal program references | internal program, compliance, CI/build-system, network, remote, and hostname references from the source project                  | omit                                                  |
| Secrets                     | any value from the source project's environment files; credentials such as passwords, secrets, tokens, keys, or PEM private keys | never copy; zero secret values                        |

> [!NOTE]
> The real image **names** `xavier-mutate` and `pyremote` are allowed because this
> domain consumes those exact prebuilt images — but only via a parameterized registry
> (`{{ .Values.image.registry }}/...`), never the internal ACR FQDN.
