# Phase 1 — Prerequisites, Tooling, and Context Safety

> Status: Complete  
> Completed by learner: 2026-09-29  
> Last validated: 2026-09-29 on macOS arm64 with OrbStack 2.2.3  
> Version baseline selected: 2026-09-29 for macOS arm64

## 1. Why this phase matters

Later phases depend on several command-line tools, a working container engine, enough local capacity, and a safe way to distinguish the lab cluster from any other Kubernetes cluster.

This phase creates that foundation. You will inspect what is already installed, understand why each tool is needed, install or upgrade missing tools yourself, verify exact versions, and practice a context guard that blocks commands when the lab cluster is not selected.

This phase does **not** create a Kubernetes cluster. Cluster creation belongs to Phase 4.

## 2. Learning objectives

By the end of this phase, you can:

- explain the purpose of every required workstation tool;
- distinguish a command-line client from the server or engine it controls;
- explain why tool and image versions are pinned;
- verify CPU architecture, memory, disk capacity, and container-engine access;
- inspect Kubernetes contexts without changing cluster state;
- use the project context guard before destructive Kubernetes actions;
- recognize a client/server version mismatch;
- produce a complete, secret-free prerequisite report.

## 3. Prerequisites

- Phase 0 is complete.
- You are working on the same Mac used for the initial inspection.
- You can use a terminal and understand basic shell commands.
- You can authorize Homebrew changes when you choose to install packages.
- You have reviewed what an installation command will change before running it.

## 4. Files created or changed

| Path | Purpose |
|---|---|
| `docs/00-project-guide.md` | Records learner completion of Phase 0 |
| `docs/01-prerequisites-and-tooling.md` | This guided phase |
| `kubernetes-reliability-platform.md` | Tracks Phase 0 as complete and Phase 1 as draft |
| `versions.env` | Pins the selected tool and Kubernetes baseline |
| `scripts/verify-prerequisites.sh` | Performs read-only prerequisite verification |
| `scripts/require-lab-context.sh` | Blocks later operations outside the named lab context |
| `.gitignore` | Excludes common local, generated, and sensitive files |

Read each script before executing it. A repository script is not trustworthy merely because it is part of the project.

## 5. Before you change anything: predict

Write your answers before installing or upgrading tools:

1. Which checks will succeed if the Docker CLI exists but its engine is stopped?
2. If Homebrew installs a new `kubectl` but `/usr/local/bin/kubectl` comes first on `PATH`, which version will run?
3. Why should the context guard fail before the `kind-k8slab` cluster exists?
4. Which project components are likely to consume the most disk space?
5. What reproducibility problem is created by an unpinned kind node image?

Keep these predictions. Compare them with your observations at the phase gate.

## 6. Initial workstation assessment

A read-only inspection on 2026-09-29 found:

| Area | Detected state | Phase 1 interpretation |
|---|---|---|
| Operating system | macOS 26.5.1 | Supported for this local lab |
| Architecture | Apple silicon, `arm64` | Use Darwin ARM64 binaries and multi-architecture images |
| Free workspace disk | About 27 GiB | Below the 40 GiB gate; free space before creating the cluster |
| Homebrew | 7.0.7 | Available as the package manager |
| Git | 2.50.1, Apple build | Available |
| OrbStack | 2.2.3 | Selected local container environment |
| Docker CLI | 29.4.0 | Available |
| Docker context | `orbstack` | A Docker-compatible OrbStack engine is selected |
| Docker engine check | Inaccessible from the assistant sandbox | You must run `docker info` in your own terminal |
| kubectl | 1.33.9 | Installed but older than the chosen Kubernetes 1.37 baseline |
| kind | 0.31.0 | Installed but older than the selected 0.33.0 baseline |
| Helm | Missing | Install |
| standalone Kustomize | Missing | Install; `kubectl`'s embedded version does not replace the pinned CLI for this course |
| SOPS and age | Missing | Install for encrypted GitOps secrets |
| k6 | Missing | Install for repeatable load tests |
| jq | Apple 1.7.1 outside Conda; Anaconda 1.6 in the active `base` environment | Homebrew 1.8.2 is installed, but Conda currently shadows it in the learner's terminal |
| yq | Missing | Install for deliberate YAML inspection and automation |
| GitHub CLI | 2.70.0 | Available; authentication is checked now and used later |

The disk finding is a gate, not a suggestion. Container images, kind node filesystems, Helm charts, and observability data can consume substantial space.

## 7. Tool roles

| Tool | Role in this project |
|---|---|
| OrbStack Docker-compatible engine | Builds images and runs kind's Kubernetes node containers |
| `kubectl` | Reads and changes Kubernetes API objects |
| kind | Creates and deletes the local Kubernetes cluster |
| Helm | Renders and packages upstream platform components |
| Kustomize | Builds application bases and environment overlays |
| SOPS | Encrypts structured secret files while preserving their format |
| age | Supplies local public-key encryption identities to SOPS |
| k6 | Generates repeatable application traffic and load |
| jq | Queries JSON output from APIs and CLIs |
| yq | Queries and modifies YAML explicitly |
| Git | Records source, desired state, decisions, and learning history |
| GitHub CLI | Supports repository and CI workflows in later phases |

Installing a client does not install its server. For example, a functioning `docker` command does not prove the Docker-compatible engine is running, and `kubectl` does not create Kubernetes.

## 8. Pinned compatibility baseline

The authoritative machine-readable baseline is [`versions.env`](../versions.env).

| Component | Pinned version | Reason or compatibility note |
|---|---|---|
| OrbStack | 2.2.3 | Selected workstation container environment |
| Kubernetes node image | 1.37.0 | Image and digest are provided by the selected kind release |
| kubectl | 1.37.1 | Official patch release; same minor version as the cluster avoids unnecessary skew |
| kind | 0.33.0 | Provides the pinned Kubernetes 1.37 node image |
| kind node image | Kubernetes 1.37.0 plus digest | Digest guarantees the intended image content |
| Helm | 4.3.0 | Current stable major; used with charts verified by later guides |
| Kustomize | 5.8.1 | Includes Helm 4 compatibility fixes |
| SOPS | 3.13.3 | Pinned encryption CLI |
| age | 1.3.2 | Pinned encryption backend |
| k6 | 2.3.0 | Pinned load-generator CLI |
| yq | 4.54.1 | Official patch release installed and verified on the workstation |
| jq | 1.8.2 | Includes security fixes absent from the detected Apple 1.7.1 build |

Do not replace these values with `latest`. A newer version is not automatically wrong, but adopting it is a dependency update: review release notes, update `versions.env`, rerun affected gates, and update the validation date.

## 9. Capacity gate

### 9.1 Inspect hardware

Run:

```bash
uname -m
system_profiler SPHardwareDataType | grep -E 'Chip|Memory'
df -h /Users/m3/Desktop/k8slab
```

Expected architecture:

```text
arm64
```

Project capacity targets:

- 16 GiB total host memory or more;
- at least 8 GiB memory available to the container engine during the full observability phases;
- at least 4 CPU cores available to the container engine;
- at least 40 GiB free disk before cluster creation; 60 GiB is more comfortable.

Record the detected memory and disk in your learning record.

### 9.2 Free disk space safely

Inspect before deleting anything:

```bash
docker system df
du -sh /Users/m3/Desktop/k8slab
```

Use your normal storage-management workflow to identify files or unused container data you recognize. Do not blindly run `docker system prune`, remove Docker/OrbStack storage directories, or delete unrelated files. Those actions can remove other projects' images, containers, volumes, or data.

Repeat `df -h /Users/m3/Desktop/k8slab` until at least 40 GiB is available.

## 10. Verify the container engine

The selected Docker context is `orbstack`. This is the canonical local container environment for the project. kind will use OrbStack's Docker-compatible engine to run its node containers.

Run in your terminal:

```bash
docker context show
docker version
docker info
docker run --rm hello-world
```

Predict before running: which commands need only the CLI, and which require a reachable engine?

Expected outcome:

- the context is the engine you intend to use;
- both client and server information appear in `docker version`;
- `docker info` reports a running engine;
- the test container exits successfully and is removed by `--rm`.

If you intentionally choose Docker Desktop instead of OrbStack, record the decision in your learning notes. Do not keep switching contexts during the project without checking where images and kind clusters live.

## 11. Install and upgrade the command-line tools

### 11.1 Preview Homebrew changes

First inspect the selected formulas:

```bash
brew info kubernetes-cli kind helm kustomize sops age k6 jq yq
```

Read the output. Confirm that Homebrew will install ARM64 packages under `/opt/homebrew`.

### 11.2 Install missing tools and update selected old tools

When you are satisfied with the preview, run:

```bash
brew install kubernetes-cli helm kustomize sops age k6 jq yq
brew upgrade kind
```

Homebrew may say a formula is already installed. That is acceptable. Do not use `sudo` with Homebrew.

These commands intentionally omit broad `brew upgrade` because upgrading every package on the workstation is outside this project.

### 11.3 Inspect command resolution

Run:

```bash
type -a kubectl kind helm kustomize sops age k6 jq yq
```

The first path for Homebrew-managed ARM64 tools should normally be under `/opt/homebrew/bin`. If an older `/usr/local/bin` or `/usr/bin` command comes first, do not delete it yet. Inspect your `PATH` and correct command precedence deliberately.

For this Mac, the initial `kubectl` was `/usr/local/bin/kubectl`. The interactive terminal's active Conda `base` environment later resolved `jq` to `/opt/anaconda3/bin/jq` version 1.6 even though Homebrew jq 1.8.2 was installed.

For the project terminal, deactivate the unrelated Conda environment and clear the shell command cache:

```bash
conda deactivate
hash -r
type -a jq
jq --version
```

The first resolved path should be `/opt/homebrew/bin/jq`, and the version should be `jq-1.8.2`. This does not uninstall or modify Anaconda. If you intentionally need Conda for another task, reactivate it in that task's terminal rather than allowing its bundled jq to control this project.

### 11.4 Verify exact versions

Run:

```bash
kubectl version --client=true --output=yaml
kind version
helm version --short
kustomize version
sops --version
age --version
k6 version
jq --version
yq --version
```

Compare the results with `versions.env`. If Homebrew has moved beyond the pinned version since this guide was written, stop and record the difference. Do not silently edit the expected version and do not automatically downgrade. Decide whether to adopt the update or install the pinned release after reviewing upstream release notes.

## 12. Git and GitHub readiness

### 12.1 Inspect identity without publishing it

Run:

```bash
git --version
git config --get user.name
git config --get user.email
gh --version
gh auth status
```

Do not paste private tokens into notes or chat. `gh auth status` should describe status without requiring you to reveal a token.

If name or email is unset, configure it using the identity you want attached to project commits. Configuration is your choice; the guide does not prescribe or expose it.

### 12.2 Initialize the learning repository

The project directory was not a Git repository during the initial inspection. From the project root, run:

```bash
cd /Users/m3/Desktop/k8slab
git init
git status
```

Before the first commit, inspect every file and confirm that no credentials, private keys, local caches, or unrelated data are included. Remote repository creation and CI permissions are handled in Phase 3.

## 13. Kubernetes context safety

List existing contexts without changing them:

```bash
kubectl config get-contexts
kubectl config current-context
```

The future kind cluster name is `k8slab`, so its kubectl context will be `kind-k8slab`.

Before any destructive Kubernetes operation later in the project, run:

```bash
bash scripts/require-lab-context.sh
```

The script refuses to continue unless the current context is exactly `kind-k8slab`. It does not make a dangerous command safe by itself; you must still check namespace and resource names.

Never solve a context mismatch by removing unknown kubeconfig files or deleting existing clusters. Inspect first.

## 14. Automated verification

From the repository root, run:

```bash
bash scripts/verify-prerequisites.sh
```

The script is read-only. It checks:

- required commands;
- pinned versions;
- Docker-engine reachability;
- available disk space;
- current Kubernetes context information.

Read every line rather than looking only at the exit code. Fix one failed category at a time and rerun the script.

The script does not verify total memory reliably across every environment, so the manual hardware check remains part of the gate.

## 15. Controlled failure exercise

### Hypothesis

Before the lab cluster exists, the context guard should return a nonzero exit code because the current context is not `kind-k8slab`.

### Safety

The guard is read-only. It reads the current kubectl context and exits; it does not connect to or change a cluster.

### Test

Run:

```bash
bash scripts/require-lab-context.sh
printf 'exit code: %s\n' "$?"
```

Expected result before Phase 4:

```text
BLOCKED: expected Kubernetes context kind-k8slab, but current context is ...
exit code: 1
```

Explain why this failure is a successful safety test. Do not create a fake context merely to make the script pass.

In Phase 4, repeat this exercise after cluster creation and expect exit code `0` only when `kind-k8slab` is selected.

## 16. Troubleshooting

| Symptom | Evidence to collect | Likely cause | Next test |
|---|---|---|---|
| `docker` exists but `docker info` fails | `docker context show`, `docker version` | Engine stopped, inaccessible socket, or wrong context | Start the intended engine and inspect `docker context ls` |
| Installed tool still reports old version | `type -a TOOL`, `echo "$PATH"` | Another binary appears earlier on PATH | Invoke both absolute paths and compare |
| Homebrew installs Intel package | `uname -m`, `brew --prefix` | Terminal or Homebrew architecture mismatch | Confirm `/opt/homebrew` ARM64 installation before proceeding |
| kind version is correct but node image differs | `versions.env`, later cluster config | Image tag was not pinned by digest | Use the exact `KIND_NODE_IMAGE` value in Phase 4 |
| jq reports 1.6 or 1.7.1 | `type -a jq`, `jq --version` | Conda or macOS jq precedes Homebrew jq | Deactivate unrelated Conda environment or correct PATH; do not delete either installation |
| Verification reports low disk | `df -h`, `docker system df` | Images, volumes, or unrelated files consume capacity | Inspect ownership and remove only data you intentionally choose |
| `gh auth status` fails | Command output without tokens | Not authenticated or expired credentials | Use `gh auth login` interactively if you intend to use GitHub |
| Context guard blocks | `kubectl config current-context` | Expected safety behavior before Phase 4 or wrong cluster selected | Do not bypass; inspect contexts |

## 17. Production considerations

- Developer workstations are convenient but not controlled CI environments.
- Homebrew improves usability but is not a complete reproducible supply-chain solution.
- Production pipelines should verify checksums, signatures, provenance, and dependency policies automatically.
- A local Docker-compatible engine and kind do not reproduce cloud networking, storage, identity, or failure domains.
- Production access should use separate identities, least privilege, audited authentication, and strict context separation.
- The context guard is a learning safety layer, not an authorization boundary.

## 18. Cleanup or rollback

No Kubernetes resources exist yet.

Do not uninstall working tools merely because one version differs. Record the mismatch and decide deliberately. If a Homebrew installation fails, use `brew info FORMULA` and `brew doctor` to diagnose it before removing files manually.

The `hello-world` container used in the engine check exits and is removed automatically; its small image may remain cached.

## 19. Definition of done

- [ ] Phase 0 is marked complete.
- [ ] The machine is confirmed as macOS ARM64.
- [ ] Total memory is recorded and meets the project target.
- [ ] At least 40 GiB disk space is free.
- [ ] The intended Docker-compatible engine is reachable.
- [ ] `hello-world` runs successfully.
- [ ] Every required command is installed and resolves to the intended path.
- [ ] Tool versions match `versions.env`, or an intentional reviewed update is documented.
- [ ] Git identity is configured without exposing credentials.
- [ ] GitHub CLI authentication status is understood.
- [ ] The project directory is initialized as a Git repository and inspected before committing.
- [ ] `scripts/verify-prerequisites.sh` passes.
- [ ] The context guard fails safely before the lab cluster exists.
- [ ] No cluster was created during this phase.
- [ ] Review questions can be answered in your own words.

When every item is true, change this guide and Phase 1 in the canonical documentation map from `Draft` to `Complete`.

## 20. Review questions

1. Why does installing `kubectl` not create Kubernetes?
2. Why are the kind node image tag and digest both recorded?
3. What is the risk of using `latest` in a learning environment?
4. Why can `docker --version` succeed while `docker info` fails?
5. Why should you inspect `type -a kubectl` after installing a new version?
6. What protection does the context guard provide, and what does it not provide?
7. Why is 27 GiB of free space treated as a blocker for this project?
8. What steps are required before adopting a newer tool version than the baseline?
9. Why is a broad Homebrew upgrade outside this phase's scope?
10. Which checks remain manual even after the verification script passes?

## 21. Further study

- Kubernetes version-skew policy: <https://kubernetes.io/releases/version-skew-policy/>
- Kubernetes 1.37 release: <https://kubernetes.io/releases/1.37/>
- kind releases and pinned node images: <https://github.com/kubernetes-sigs/kind/releases>
- Helm releases: <https://github.com/helm/helm/releases>
- Kustomize releases: <https://github.com/kubernetes-sigs/kustomize/releases>
- SOPS releases: <https://github.com/getsops/sops/releases>
- age releases: <https://github.com/FiloSottile/age/releases>
- k6 releases: <https://github.com/grafana/k6/releases>
- jq releases and security fixes: <https://github.com/jqlang/jq/releases>
- Homebrew documentation: <https://docs.brew.sh/>
- Docker contexts: <https://docs.docker.com/engine/manage-resources/contexts/>

## 22. Next phase

After passing this phase gate, continue to `docs/02-demo-application.md`.

Phase 2 will design and build the frontend, FastAPI service, and Redis behavior locally. It will introduce health semantics, structured logs, application metrics, trace context, controlled failure endpoints, and unit tests before any Kubernetes deployment exists.
