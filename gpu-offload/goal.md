
# Goal

Create an example deployment that utilizes the technique for use of the "mutatator" controller to deploy a pod/container that offloads GPU using the mechanism that employs the "base" container or "python" package install of the

**MUST** use the pattern for the actual "workload" container that auto-offloads GPU as described in "/home/workstation4/g/scicoria/xavier-pai-integration-test/tutorial" path...

# Workspaces --
All the various projects needed for context in the the base path -- there are three
Base path is `/home/workstation4/g/scicoria`

## Current working project workspace
`physical-ai-toolchain`
This contains the primary deliverable

## Trained model that is desired to be a example in the examples path in gpu-offload
`ur10e-single`

**IMPORTANT** this relies on LARGE files for the model, which is at

**IMPORTANT** all docs, artifacts, etc. must only affect the path `physical-ai-toolchain/gpu-offload`
ur10e-single
xavier-pai-integration-test


## Offload pattern package
Located in `/home/workstation4/g/scicoria/xavier-pai-integration-test/tutorial/` --

- focus on the "tutorial" as guidance -- with the goal of the `ur10e-single` being THE container that requires the "offloading"

# Compostion
- The "mutating controller" deployment is already there -- but if there are changes in that code clearly that may need to be deplyed.


# Guidance
0. Any place for permanent or temp artifacts shold be physical-ai-toolchain/gpu-offload -- docs are important
1. It is not necessary to have a "base" container as in the tutorial files
2. the "remoter" image that is in the tutorial example Docker file `ARG REMOTER_IMAGE=pyremote:latest` -- that is the path in this workspace at `/home/workstation4/g/scicoria/physical-ai-toolchain/gpu-offload/runtime` --
3. Ideally there is a "local" registry on the machine that from the machine itself tools can push to the registry -- this is a single node K3s cluster -- and that "local" registry must be the place that all image pulls come from.
4. Ideally any "large" models etc. are in some cache on the host to mitigrate and prevent constant pulls as the internet is slow
5. Ideally uv is used for ALL python work -- AND there is a "host" mount or whatever that caches the UV package cache to mitigate long internet pulls
