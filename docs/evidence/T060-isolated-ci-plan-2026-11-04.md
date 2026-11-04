# T060 isolated ML CI reconstruction: static-only plan and evidence

Date: 2026-11-04 UTC. Status: **review_required; actual isolation and ML NOT_RUN**.
This is new reconstruction after the earlier unpublished T060 files were lost.
It does not reuse their tests or treat their results as evidence for this code.
ADR 0012 and ADR 0013 remain the privacy and export contracts.

## Authorization and acceptance boundary

The prior native ML run was denied because Microsoft's ORT telemetry behavior
had not been safely bounded. That denial remains in force. This change prepares
source and runs only fresh mock/standard-library tests. It does **not** authorize
Docker, image acquisition/build, dependency installation, ML imports, native
models, network connectivity probes, browser ML, remote CI, publication or merge.
No such actions were performed for this reconstruction.

The workflow's entire `linux-training` job requires both `workflow_dispatch` and
the boolean `run_isolated_ml: true`; the input defaults to false. Push and PR
cannot select this job. Both ordinary lanes explicitly clear the policy-suite
opt-in variables. Dispatch UI/API availability for a branch whose workflow is not
on the default branch is **NOT_RUN**. Do not merge main or add an automatic
fallback to work around this. A manual run requires a separately approved,
reviewed exact revision and available dispatch route. Before any Docker command,
acquisition or build, the script requires GITHUB_ACTIONS=true,
RUNNER_ENVIRONMENT=github-hosted, the named workflow/expected workflow file,
workflow_dispatch, explicit opt-in, and both GITHUB_SHA and GITHUB_WORKFLOW_SHA
matching the expected commit. Missing/persistent/
self-hosted context is rejected. These environment checks prevent accidental
misuse; they are not authentication against a malicious local owner able to
forge variables or alter the program. The trust assumption is the reviewed
GitHub-hosted workflow executing the reviewed source revision.

## Fixed preparation recipe, not tested image compatibility

- Runner: ordinary `ubuntu-24.04`, with the existing commit-pinned setup actions
  providing Python 3.12.14 and Node 24.22.1.
- Candidate base: `mcr.microsoft.com/playwright:v1.64.1-noble@sha256:2f05f8a734509a7b3f26a912639488ee08f58a7b292d14d62271bcff9038768f`, explicitly `linux/amd64`.
  The digest is an OCI index from the official indexed
  [MCR tag metadata](https://mcr.microsoft.com/en-us/artifact/mar/playwright/tag/v1.64.1-noble).
  Live image resolution, layer acquisition, architecture, ABI and Chromium
  execution are **NOT_RUN**. There is no unpinned/tag-only fallback.
- The [official versioned Playwright Dockerfile](https://github.com/microsoft/playwright/blob/v1.64.1/utils/docker/Dockerfile.noble)
  installs Node by major version and bakes the corresponding browsers/system
  libraries. Its Node patch is not our exact Node guarantee.
- Copy only the exact official tool prefixes
  `/opt/hostedtoolcache/Python/3.12.14/x64` and
  `/opt/hostedtoolcache/node/24.22.1/x64`. Reject links escaping those prefixes and
  special files. Preserve Python's absolute prefix. Set LD_LIBRARY_PATH only to
  that prefix's `/lib`, never inherit a host path. This follows the
  [setup-python source](https://github.com/actions/setup-python/blob/main/src/find-python.ts)
  without assuming portable runtime linking. Never copy a host virtualenv,
  home directory, Docker socket or credentials.
- In the image, standard-library-only Python/version and Node-version checks
  precede installation. Create a new `/opt/edgevision/backend/.venv-delivery`
  using `scripts/install_ml.py --delivery` and the joint hash-locked wheels.
  Use `npm ci --ignore-scripts --no-audit --no-fund`. No build-time model probe,
  ML import or model execution is permitted.
- `ORT_DISABLE_TELEMETRY=1` is set in the image and all command environments.
  The boundary entry uses Python `-I -S`, so site initialization and `.pth` files
  cannot import ML before the kernel boundary check. Child ML interpreters start
  only after that check and inherit the opt-out setting.

### Exact source binding

The workflow requires a separately reviewed full SHA in the manual `approved_commit` input, passed through the quoted `EDGEVISION_APPROVED_COMMIT` environment variable. It does not derive authorization from its own `GITHUB_SHA`. Empty/abbreviated/mismatched values fail before preparation. The runtime and workflow source SHAs must both equal that independent input. Preparation requires HEAD
at that exact commit and a clean tracked/untracked state for the relevant source
roots. Both checks repeat after freezing. It reads the commit's `git ls-tree`
and `git cat-file` blobs, verifies each Git blob object ID, and writes only
regular allowed source/configuration bytes. It never copies live worktree/index
bytes. The Dockerfile and acquisition script are frozen from the same commit;
only that frozen acquisition script may execute.

Allowed roots are backend, web, scripts and contracts, plus the one named CI
Dockerfile. Dotfiles, environment files, private evidence, logs, databases,
models, node_modules, screenshots and build outputs are excluded. JSON is limited
to named project configuration/OpenAPI files rather than generic runtime JSON.
The one fixed official YOLO11n asset enters the private context separately, with
size 5,613,764 and SHA-256
`0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1` checked again.
It is never committed, attached or published.

### Local daemon and cache boundary

Reject Docker host/context/TLS/cert/config and Buildx/BuildKit endpoint overrides.
The Docker client gets a new empty config and a minimal environment without host
credentials or proxy settings. Before any build, inspect the default context and
require exactly `unix:///var/run/docker.sock`. Use the explicitly selected default
builder. The [Docker builder documentation](https://docs.docker.com/build/builders/)
binds that builder to the current daemon/context. No remote builder, registry
output, image push, cache export, SSH forwarding or build secret is configured.

The build context and command logs live in a temporary private directory removed
before public success. The owned execution container and final local image must
also be confirmed absent. **This is not a claim to erase Docker's build cache.**
Preparation layers may retain approved source, installed public dependencies and
the fixed public base asset until the fresh GitHub-hosted runner is destroyed.
No runtime training outputs, generated images, credentials, databases or private
runtime fingerprints enter that build cache. Do not upload/export it and do not
prune unrelated default-builder state. A persistent/self-hosted runner is outside
this plan.

## Execution boundary and failure handling

Create, do not directly run, an exact local `sha256:` image ID with pull disabled.
The random container has an ownership label and runs as `10001:10001`, with network
none, all capabilities dropped, no-new-privileges, private IPC/cgroup namespaces,
256 MiB shared memory, 512 PIDs, 6 GiB memory including swap, and 2 CPUs. There are
no ports, host PID/IPC/network modes, mounts, devices, health checks or restart
policy. API, Worker, Vite and Chromium communicate only through loopback in this
single container. Writable dependency/project files belong to the non-root user.

Before starting, inspect the **stopped** container and validate its exact image,
entrypoint/arguments, non-root user, strict complete environment, ownership,
network, security options, namespaces, mounts and resource limits. Any unexpected
value prevents `start`. Inside it, before any ML child, check nonzero UIDs, a
network namespace different from the supplied opaque host namespace identity,
only `lo`, no usable non-loopback/default IPv4 or IPv6 routes, effective
capabilities zero, NoNewPrivs=1 and Seccomp=2. Kernel unreachable IPv6 defaults on
loopback are allowed only with RTF_REJECT and no gateway. No external connection
attempt is used to test isolation. Any failure exits; there is no host fallback.

Six canonical stages, in order:

1. Structural isolation verification.
2. `tests/training_http_probe.py`.
3. `tests/export_http_probe.py`, consuming the completed training HTTP root.
4. `tests/test_onnx_runtime_policy.py`, with EDGEVISION_ONNX_POLICY_ROOT set.
5. `tests/test_training_ml_policy.py`, with EDGEVISION_ML_POLICY_ROOT set.
6. `scripts/e2e.py --delivery --ml-asset ...`, using its own disposable data root.

Both policy roots point to the same private HTTP root. Policy suites additionally
require nonzero executed JUnit cases, zero skips, zero failures and zero errors;
a skipped suite cannot pass. All child output/tracebacks and JUnit/browser reports
stay private. Only reconstructed schema-version-1 stage/status fields are public.
An uncertain start's stages are `unverified`, not falsely `NOT_RUN`. Missing,
extra, duplicate, malformed, reordered or incomplete summary fields are rejected.

After execution, inspect the stopped/exited container again. A success exit alone
is insufficient: all six canonical stages must pass, post-execution inspection
must pass, and owned container/image/local context cleanup must complete before
public success. Cleanup failure overturns success while preserving previously sanitized child
outcomes; a late context/report-writing fault cannot relabel executed stages
NOT_RUN. Create attempts are recorded
**before** invoking the client. After timeout, reconcile exact name + label + image
ownership; never remove a preexisting or unowned object. A build timeout before
its image ID, or a create timeout before daemon visibility, remains explicitly
`cleanup_unknown`/failed. Absence of an early handle is not proof of cleanup.

Budgets remain 20 minutes for the GitHub job, at most 600 seconds for build,
480 seconds shared across outer create/inspect/start/post-inspect, 450 seconds
shared across all inner child stages, and 30 seconds shared for cleanup. No retry
or fallback silently enlarges these budgets. SIGTERM/client failures attempt
owned cleanup; an uncertain cleanup never produces a success claim.

## Evidence and outstanding work

Files: `ci/isolated-ml.Dockerfile`, `scripts/isolated_ml_ci.py`,
`scripts/isolated_ml_entry.py`, `backend/tests/test_isolated_ml_ci.py`,
`.github/workflows/t020-ci.yml`, and this plan.

The supplied lightweight Python environment ran only
`python -m pytest backend/tests/test_isolated_ml_ci.py -q --basetemp /tmp/edgevision-ci-tests-20261104h`:
**exit 0, 127 passed in 0.24 seconds**. These are fresh mock/static tests, not native
isolation evidence. They cover rejected stopped inspections/no start, unsafe
network/capability/mount/env, local endpoint guards, private-output filtering,
canonical stage checks, shared deadlines, skips, create/start timeouts, delayed
create visibility, no-image-ID build timeout, ownership refusal, post-execution
inspection, failed/no-op removals, interrupted execution, local context cleanup,
exact Git blobs, modified/untracked recipe rejection, hosted-workflow guards,
signal cleanup, late-report outcome preservation and dispatch-default-false.
Python AST syntax parsing, workflow YAML parsing and `git diff --check` also
completed with exit 0; these do not execute the workflow or validate Docker.

This isolated-CI branch alone deliberately lacks integration-owned joint-lock and
export-probe files. Preparation rejects their absence; there are no success
placeholders. Integrate the reviewed installer/lock/backend/UI work, then repeat
static review and lightweight checks at the exact combined commit.

Docker commands, image ABI/browser validation, runtime dependency installation,
model acquisition, training/export/ORT execution, real policy probes, browser ML,
branch dispatch and native isolation are all **NOT_RUN**. No E acceptance, I/P,
Windows ML, CUDA, RKNN/NPU, accuracy or thesis completion is claimed. Any approved
future native run must produce new evidence; it cannot inherit this mocked pass.
