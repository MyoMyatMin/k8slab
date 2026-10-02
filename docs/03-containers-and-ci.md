# Phase 3 — Containers and Continuous Integration

> Status: Complete
> Last validated: 2026-10-02
> Version baseline selected: 2026-09-29 for macOS arm64, Docker Compose 5.1.2, Buildx 0.33.0, and GitHub Actions
> Exercise mode: Challenge-first

## 1. Why this phase matters

Phase 2 proved the application on one workstation. That is not yet a reproducible release artifact. A reliability platform needs the same reviewed artifact to pass tests, run locally, publish through CI, and later deploy to Kubernetes without being rebuilt differently at every step.

This phase turns the frontend and API into immutable OCI images, runs the complete system on a container network, verifies least-privilege runtime behavior, scans the images, and publishes multi-platform images to GitHub Container Registry (GHCR).

The central delivery rule is:

```text
source commit
    -> tests
    -> image build
    -> security scan
    -> immutable digest
    -> SBOM and provenance
    -> GHCR
```

Kubernetes deployment is deliberately excluded. Phase 4 will consume the image digests produced here.

## 2. Learning objectives

By the end of this phase, you can:

- distinguish an image, layer, container, tag, manifest, and digest;
- explain why a tag is convenient but a digest is the immutable deployment identity;
- design small build contexts and useful `.dockerignore` files;
- use multi-stage builds to separate build-time and runtime dependencies;
- run application containers as non-root with reduced privileges;
- connect services by container DNS rather than host-only addresses;
- explain the difference between local architecture and multi-platform images;
- design CI with least-privilege permissions and untrusted pull requests in mind;
- use BuildKit cache without treating cache contents as release artifacts;
- scan images and distinguish findings from a risk-based release policy;
- generate and inspect SBOM and provenance attestations;
- publish images to GHCR and record the immutable digest.

## 3. Exercise mode

This is a core DevOps phase, so it uses the **challenge-first** mode.

You receive:

- an operational contract;
- exact safety and version constraints;
- verification commands;
- expected evidence;
- progressive hints.

You do not receive complete Dockerfiles, Compose configuration, or GitHub Actions workflows before your first attempt. Ask for a review after each checkpoint; do not wait until the entire phase is finished if one design choice is unclear.

## 4. Prerequisites

- Phase 2 is complete and pushed to `origin/main`.
- OrbStack's Docker-compatible engine is reachable.
- `docker compose version` reports 5.1.2.
- `docker buildx version` reports 0.33.0.
- GitHub CLI is authenticated as `MyoMyatMin`.
- The repository `MyoMyatMin/k8slab` exists. It is public at completion so
  GitHub can store artifact attestations on the selected account plan.
- At least 30 GiB of disk remains available.
- No unrelated credentials or `.env` files are staged.

Start from a clean checkpoint:

```bash
cd /Users/m3/Desktop/k8slab
git status --short
git log -1 --oneline
git remote -v
```

If Phase 2 has not been committed and pushed, finish that checkpoint before continuing. Do not mix the Phase 2 implementation and Phase 3 container work in one commit.

Create a learning branch:

```bash
git switch -c phase-3-containers-ci
```

If that branch already exists, inspect it before switching. Do not recreate or overwrite an existing branch blindly.

## 5. Files you will create or change

```text
.github/
└── workflows/
    ├── ci.yml
    └── publish.yml
app/
├── api/
│   ├── .dockerignore
│   ├── Dockerfile
│   ├── requirements.lock
│   └── requirements-dev.lock
└── frontend/
    ├── .dockerignore
    ├── Dockerfile
    └── nginx.conf
compose.yaml
.trivy.yaml
docs/
└── 03-containers-and-ci-evidence.md
```

Do not create Kubernetes YAML yet.

## 6. Concepts and vocabulary

| Term | Meaning in this project |
|---|---|
| Build context | Files the builder may read; it should be intentionally small |
| Layer | Immutable filesystem change produced by a build instruction |
| Image | Ordered layers plus OCI configuration and metadata |
| Container | Runtime instance of an image with writable process state |
| Tag | Mutable human-friendly image reference such as `sha-abc1234` |
| Digest | Content-addressed immutable identity such as `sha256:...` |
| Manifest | Description of one platform-specific image |
| Image index | Multi-platform collection mapping platforms to manifests |
| Multi-stage build | Build stages that leave tools and temporary artifacts outside the runtime image |
| SBOM | Inventory of packages and software components in an image |
| Provenance | Evidence describing where and how an artifact was built |
| GHCR | GitHub Container Registry at `ghcr.io` |

Record this distinction in your notes:

```text
tag answers: "which release name?"
digest answers: "which exact bytes?"
```

## 7. Pinned Phase 3 baseline

The executable values live in `versions.env`.

| Purpose | Pinned baseline |
|---|---|
| API base | `python:3.14.7-slim-bookworm@sha256:82bc...ff56` |
| Redis | `redis:8.10.2-alpine3.23@sha256:3811...e5a0` |
| Frontend base | `nginxinc/nginx-unprivileged:1.31.6-alpine3.24@sha256:26b0...a4af` |
| Trivy CLI | `v0.74.0` |
| pip-tools | `7.6.1` |
| Target platforms | `linux/amd64,linux/arm64` |
| Registry | `ghcr.io` |
| API package | `ghcr.io/myomyatmin/k8slab-api` |
| Frontend package | `ghcr.io/myomyatmin/k8slab-frontend` |

The Python container patch is newer than the Phase 2 host patch. Both remain Python 3.14; the runtime base is separately pinned to a current digest so rebuilding does not silently change it.

## 8. Before you build: predict

Write brief answers before creating files:

1. Which files would leak into the image if the repository root were used as an unrestricted build context?
2. Why does installing development dependencies into the runtime image increase risk?
3. What happens when `localhost` is used as `REDIS_URL` inside the API container?
4. Why can a tag point to different bytes later while a digest cannot?
5. Why should pull-request CI not receive package-publishing permission?
6. Which container should be reachable from the host, and which service can remain internal?
7. What evidence would prove that a container is running as non-root rather than merely declaring a user in prose?

Do not skip these predictions; revisit them after the Compose failure exercise.

## 9. Install the Phase 3 security tool

Trivy is not installed yet.

```bash
brew install trivy
trivy --version
```

Expected baseline:

```text
Version: 0.74.0
```

If Homebrew provides a newer patch or minor release, stop and update `versions.env` and this guide together rather than silently changing the baseline.

Trivy downloads vulnerability databases. A database-update failure is different from a clean scan; never interpret “scanner could not update” as “no vulnerabilities.”

## 10. Resolve Python dependencies reproducibly

Direct pins in `requirements.txt` do not pin transitive dependencies or their distribution hashes. This phase adds generated lock files.

Install the pinned resolver inside the API virtual environment:

```bash
cd /Users/m3/Desktop/k8slab/app/api
source .venv/bin/activate
python -m pip install pip-tools==7.6.1
```

Challenge:

- Generate `requirements.lock` from `requirements.txt`.
- Generate `requirements-dev.lock` from `requirements-dev.txt`.
- Include hashes.
- Use Python 3.14 for generation.
- Keep the small human-edited input files and commit the generated lock files.
- Make the runtime image install with `--require-hashes` from `requirements.lock`.
- Make CI tests install with `--require-hashes` from `requirements-dev.lock`.

Verification:

```bash
rg -- '--hash=sha256:' requirements.lock requirements-dev.lock
python -m pip install --dry-run --require-hashes -r requirements-dev.lock
```

<details>
<summary>Hint</summary>

Investigate `pip-compile --generate-hashes`. The input and output must be named explicitly so the two dependency roles remain clear.

</details>

## 11. Design the API image

Create `app/api/Dockerfile` without copying a completed reference.

### Required contract

- Use the exact pinned Python base tag and digest.
- Use more than one stage.
- Build wheels or an equivalent installable dependency artifact in the builder stage.
- Install runtime dependencies from `requirements.lock` with hash enforcement.
- Do not copy tests, `.venv`, `.pytest_cache`, Git data, or development dependencies into the runtime stage.
- Create a dedicated numeric UID/GID such as `10001`.
- Run Uvicorn as that non-root user.
- Bind to `0.0.0.0:8000`.
- Use exec-form `CMD` or `ENTRYPOINT` so signals reach Uvicorn correctly.
- Set unbuffered logging and disable bytecode writes.
- Add OCI source, revision, and version labels through build arguments.
- Do not bake `REDIS_URL`, passwords, tokens, or environment-specific secrets into the image.

Create `app/api/.dockerignore` that permits only the files needed for the build.

Build checkpoint:

```bash
cd /Users/m3/Desktop/k8slab
docker build --tag k8slab-api:dev app/api
docker image inspect k8slab-api:dev --format '{{json .Config.User}}'
docker run --rm --entrypoint id k8slab-api:dev
docker history --no-trunc k8slab-api:dev
```

The configured and effective UID must be non-zero. Inspect history for unexpected credentials, local paths, or development-only commands.

Runtime checkpoint without Redis:

```bash
docker run --rm --name k8slab-api-check \
  --read-only \
  --tmpfs /tmp \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --publish 8000:8000 \
  k8slab-api:dev
```

From another terminal, liveness should return 200 and readiness should return 503. Stop the exact foreground container with `Ctrl+C`.

<details>
<summary>Progressive hints</summary>

- A builder stage may create wheels in a directory copied into the runtime stage.
- Use `COPY` ordering so dependency layers remain cached when only application code changes.
- The runtime needs the package, not the virtual environment from macOS.
- Debian's `useradd`/`groupadd` or equivalent numeric-user tools belong in one cleaned layer.

</details>

## 12. Design the frontend image

Create `app/frontend/Dockerfile`, `app/frontend/.dockerignore`, and `app/frontend/nginx.conf`.

### Required contract

- Use the exact pinned `nginx-unprivileged` tag and digest.
- Keep the inherited non-root runtime identity.
- Listen on port 8080.
- Serve only `index.html`, `app.js`, and `styles.css`.
- Use a foreground NGINX process supplied by the base image.
- Return `index.html` for `/`.
- Add safe baseline response headers without inventing a production TLS policy.
- Do not add package managers, shells, or build tools merely for health checks.
- Do not embed credentials.

Build and verify:

```bash
cd /Users/m3/Desktop/k8slab
docker build --tag k8slab-frontend:dev app/frontend
docker image inspect k8slab-frontend:dev --format '{{json .Config.User}}'
docker run --rm --entrypoint id k8slab-frontend:dev
docker run --rm --name k8slab-frontend-check \
  --read-only \
  --tmpfs /tmp \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --publish 8080:8080 \
  k8slab-frontend:dev
```

Open `http://127.0.0.1:8080`, inspect response headers, and then stop the exact foreground container.

## 13. Explain image layers

For both images, collect:

```bash
docker image ls k8slab-api:dev k8slab-frontend:dev
docker history k8slab-api:dev
docker history k8slab-frontend:dev
```

Answer:

1. Which layer changes when only `main.py` changes?
2. Which layer changes when `requirements.lock` changes?
3. Why should dependency installation happen before application source is copied?
4. Which builder-stage tools are absent from the final API image?
5. Does smaller always mean safer? What other evidence is required?

## 14. Compose the complete system

Create `compose.yaml` at the repository root.

### Required topology

```text
host browser
    | :8080
    v
frontend container

host tools
    | :8000
    v
API container -- redis://redis:6379/0 --> Redis container
```

### Required contract

- Build frontend and API from their own directories.
- Use the exact pinned Redis image and digest.
- Set `REDIS_URL=redis://redis:6379/0` for the API.
- Publish frontend 8080 and API 8000 to `127.0.0.1` only.
- Do not publish Redis to the host.
- Add health checks for Redis, API readiness, and the frontend.
- Make API startup depend on Redis health, while keeping runtime failure visible after startup.
- Use a named application network or a clearly understood Compose default network.
- Run all services with dropped capabilities and `no-new-privileges` where supported.
- Use read-only root filesystems plus scoped `tmpfs` mounts where the images allow it.
- Keep Redis intentionally non-persistent for this lab phase.
- Set `ENABLE_FAILURE_INJECTION=true` only in this local lab configuration.
- Do not put secrets in Compose YAML.

Validate before starting anything:

```bash
docker compose config --quiet
docker compose config
```

Inspect the rendered configuration for accidental secrets and floating image tags.

Start and verify:

```bash
docker compose up --build --wait
docker compose ps
curl -i http://127.0.0.1:8080/
curl -i http://127.0.0.1:8000/health/live
curl -i http://127.0.0.1:8000/health/ready
curl -i http://127.0.0.1:8000/api/v1/visits
```

Use service names, not container IP addresses. Container IPs are replaceable implementation details; Compose DNS is the stable discovery mechanism.

## 15. Container-network failure exercise

### Hypothesis

Stopping only the Redis service should leave the API process live, make it unready, and make the visit endpoint fail safely. Restarting Redis should recover the same API container without rebuilding images.

### Safety

- Operate only on the Compose project in this repository.
- Do not use broad container-pruning commands.
- Confirm service names with `docker compose ps`.

### Introduce and observe

```bash
docker compose stop redis
curl -i http://127.0.0.1:8000/health/live
curl -i http://127.0.0.1:8000/health/ready
curl -i http://127.0.0.1:8000/api/v1/visits
docker compose logs --since 2m api
```

Expected: 200, 503, 503, with safe correlated logs.

### Recover

```bash
docker compose start redis
docker compose ps
curl -i http://127.0.0.1:8000/health/ready
curl -i http://127.0.0.1:8000/api/v1/visits
```

Record what changed and what did not:

- Redis process identity changed or restarted;
- API image and container did not need rebuilding;
- dependency health recovered through the network;
- the ephemeral visit value may differ.

## 16. Verify runtime restrictions

Collect evidence rather than trusting Dockerfile text:

```bash
docker compose exec api id
docker compose exec frontend id
docker compose exec redis id
docker compose exec api sh -c 'test ! -w / && echo root-filesystem-not-writable'
docker inspect "$(docker compose ps -q api)" --format '{{json .HostConfig.CapDrop}}'
docker inspect "$(docker compose ps -q api)" --format '{{json .HostConfig.SecurityOpt}}'
```

Do not weaken read-only or non-root settings simply to make an unexplained write succeed. Determine which exact path the process needs and whether a scoped volume or `tmpfs` is justified.

## 17. Scan configuration and images

Create `.trivy.yaml` with an explicit, reviewed policy. The learning baseline is:

- scan vulnerabilities, secrets, and misconfiguration where applicable;
- report HIGH and CRITICAL findings;
- fail the release on fixable CRITICAL findings;
- document, rather than silently ignore, accepted exceptions;
- keep the vulnerability database current;
- do not commit large raw reports unless reviewed and required as evidence.

Run local checks:

```bash
trivy config --severity HIGH,CRITICAL .
trivy image --severity HIGH,CRITICAL k8slab-api:dev
trivy image --severity HIGH,CRITICAL k8slab-frontend:dev
```

Then run the blocking form selected by your policy. Record:

- target image digest;
- database update time;
- vulnerability ID;
- installed and fixed version;
- whether the finding is reachable or relevant;
- remediation or time-bounded acceptance decision.

Never solve a scan by changing the threshold until it turns green without explaining the risk.

## 18. Multi-platform build reasoning

Your Mac uses arm64 while standard GitHub-hosted Linux runners use amd64. The published images must contain both.

Inspect the pinned bases:

```bash
docker buildx imagetools inspect "$(awk -F= '/^PYTHON_BASE_IMAGE=/{print $2}' versions.env)"
docker buildx imagetools inspect "$(awk -F= '/^NGINX_UNPRIVILEGED_IMAGE=/{print $2}' versions.env)"
```

Challenge:

- Build each image for `linux/amd64` and `linux/arm64` with Buildx.
- Understand why a multi-platform result cannot always be loaded into the classic local image store with `--load`.
- Use single-platform `--load` for local runtime tests.
- Use multi-platform `--push` for GHCR publication.
- Do not claim multi-platform support merely because the base image supports both platforms; your final index must contain both manifests.

## 19. Design least-privilege CI

Create two workflows.

### `.github/workflows/ci.yml`

Trigger on pull requests and pushes. It must:

- default to `permissions: contents: read`;
- check out code using a full commit SHA pin;
- install the exact Python version and hashed development dependencies;
- run `pytest -q`;
- validate Compose configuration;
- build both images without publishing;
- run non-root and smoke checks;
- scan source/configuration and images;
- avoid registry login and package-write permission;
- use BuildKit caching keyed separately for API and frontend;
- cancel superseded runs on the same branch where practical.

### `.github/workflows/publish.yml`

Trigger on a push to `main` and optionally manual dispatch. It must:

- run only after or repeat the required validation gate;
- use `contents: read` and `packages: write`;
- add `id-token: write`, `attestations: write`, and `artifact-metadata: write` only for attestation work;
- log in to GHCR with `${{ github.actor }}` and `${{ secrets.GITHUB_TOKEN }}`;
- publish API and frontend for amd64 and arm64;
- tag each image with the Git commit identity;
- attach an SBOM and max-level provenance;
- print image names and digests to the workflow summary;
- never publish pull-request code;
- never expose tokens in build arguments, labels, logs, or attestations.

Separating validation and publication keeps write permissions out of the workflow that handles untrusted pull-request changes.

## 20. Pin every GitHub Action by commit SHA

Use a full 40-character commit SHA in every `uses:` field and retain the release as a comment:

```text
uses: owner/action@FULL_COMMIT_SHA # vX.Y.Z
```

The approved baseline is stored in `versions.env`. Important examples include:

| Action | Release | Commit SHA |
|---|---|---|
| `actions/checkout` | v7.0.0 | `9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0` |
| `actions/setup-python` | v7.0.0 | `5fda3b95a4ea91299a34e894583c3862153e4b97` |
| `docker/setup-qemu-action` | v4.2.0 | `96fe6ef7f33517b61c61be40b68a1882f3264fb8` |
| `docker/setup-buildx-action` | v4.3.0 | `37fe631027851001ddb9b187196cc803df7f5f0e` |
| `docker/login-action` | v4.6.0 | `dbcb813823bdd20940b903addbd779551569679f` |
| `docker/metadata-action` | v6.2.0 | `dc802804100637a589fabce1cb79ff13a1411302` |
| `docker/build-push-action` | v7.2.0 | `f9f3042f7e2789586610d6e8b85c8f03e5195baf` |
| `actions/attest` | v4.2.2 | `1e69f48acb82d1966a394da916b4c1698aa569d6` |
| `aquasecurity/trivy-action` | v0.36.0 | `ed142fd0673e97e23eac54620cfb913e5ce36c25` |

This is especially important for third-party actions. Trivy's maintainers disclosed a 2026 tag-compromise incident; immutable releases and commit-SHA pins reduce exposure to mutable tag attacks. A SHA pin is not a substitute for reviewing an action's permissions and behavior.

## 21. Tags, digests, and release identity

Use tags for discoverability and digests for deployment.

Required publication behavior:

- produce a commit-derived tag for every published image;
- optionally produce a `main` convenience tag;
- do not depend on `latest`;
- record the digest returned by the build action;
- Phase 4 Kubernetes manifests must eventually consume `name@sha256:digest`.

Do not confuse the per-platform manifest digest with the top-level multi-platform index digest. Record the digest returned for the published multi-platform image.

## 22. SBOM and provenance

For registry publication, configure Buildx to attach:

- SBOM: `sbom: true`;
- provenance: `mode=max`;
- OCI labels and annotations identifying repository and revision.

Build arguments are not secret storage. Max-level provenance may expose build argument values. Use BuildKit secret mounts if a future build genuinely requires a secret, and ensure the secret does not persist in a layer.

Verify after publication using Docker Buildx and GitHub CLI. Record the exact verification commands that worked for your private repository.

## 23. GitHub workflow checkpoint

Before pushing:

```bash
git diff --check
git status --short
rg -n 'uses:.*@(main|master|v[0-9])' .github/workflows
rg -n 'latest' Dockerfile app compose.yaml .github/workflows versions.env
docker compose config --quiet
```

Interpret matches instead of deleting words mechanically. A human-readable comment such as `# v7.0.0` is allowed; a floating executable action reference is not.

Commit the branch in coherent steps, then push it:

```bash
git push -u origin phase-3-containers-ci
```

Open a pull request and inspect every workflow permission before running or approving it.

## 24. GHCR publication and digest evidence

After the reviewed branch reaches `main`, inspect the publish workflow and both packages.

Create `docs/03-containers-and-ci-evidence.md` containing no tokens and at least:

```text
Source commit:
Workflow run URL:
API image name:
API multi-platform digest:
Frontend image name:
Frontend multi-platform digest:
Platforms present:
Non-root evidence:
Scan result summary:
SBOM verification:
Provenance verification:
Recorded on:
```

Confirm that an anonymous pull by digest works for both public packages. If a
future package is deliberately private, use an approved credential flow and
never paste a token into the document or shell history.

## 25. Troubleshooting

| Symptom | Evidence to collect | Likely causes | Next test |
|---|---|---|---|
| Build context is unexpectedly large | Build output and `.dockerignore` | `.venv`, cache, or repository files included | Compare sent context before and after ignore rules |
| API cannot reach Redis | `docker compose logs`, rendered environment | `localhost` used instead of service DNS | Resolve `redis` inside API container and inspect `REDIS_URL` safely |
| Read-only container fails at startup | Exact denied path | Runtime writes to an undeclared location | Add only the required scoped `tmpfs` or fix application behavior |
| Image says root despite Dockerfile user | `docker image inspect`, `id` | Final stage reset `USER` or inherited root | Inspect the final stage and effective UID |
| Frontend works but API calls fail | Browser network panel and CORS headers | Wrong host port, origin, or API URL | Curl API directly, then compare browser origin |
| arm64 works but amd64 fails | Image index and CI logs | Platform-specific dependency or missing QEMU | Build and smoke-test amd64 explicitly |
| Trivy cannot update database | Scanner logs and network status | Rate limit or registry connectivity | Separate DB update failure from scan findings |
| CI can test but cannot push | Job permissions and package settings | Missing `packages: write` or GHCR linkage | Inspect effective workflow permissions and package access |
| Attestation missing | Build output type and flags | Image loaded locally instead of pushed | Verify registry output plus SBOM/provenance inputs |
| Pull request can access write token | Workflow event and permissions | Over-broad top-level permissions | Split validation from publication immediately |

## 26. Production considerations

- A single Uvicorn process is adequate for this lab; production concurrency should be sized and measured deliberately.
- Container non-root is one layer, not a complete sandbox. Kubernetes security contexts and policies arrive later.
- Redis is ephemeral here; production persistence, authentication, backup, and licensing require explicit decisions.
- Vulnerability databases change after an image is published, so scanning only at build time is insufficient for long-lived production images.
- Digest pinning improves reproducibility but requires an intentional update process for security patches.
- CI caches improve speed but must never bypass tests, scans, or content-addressed publication.
- GHCR visibility is controlled separately from repository visibility. This
  lab uses public packages so Phase 4 can pull immutable digests without image
  pull credentials.
- Provenance says how something was built; it does not prove the source or build process was free of malicious behavior.

## 27. Cleanup and rollback

Stop only this Compose project:

```bash
cd /Users/m3/Desktop/k8slab
docker compose down --remove-orphans
```

Do not use global prune commands. They can delete unrelated images, caches, volumes, and containers.

The local images are reproducible and may be removed individually after confirming their exact names:

```bash
docker image ls k8slab-api:dev k8slab-frontend:dev
```

If a published tag is wrong, do not silently rebuild the same claimed release. Publish a corrected commit-derived tag and update the recorded digest through review.

## 28. Definition of done

- [x] Phase 2 is committed and pushed separately.
- [x] Phase 3 work is performed on a dedicated branch.
- [x] Dependency lock files include hashes and install successfully.
- [x] API and frontend Dockerfiles use pinned base-image digests.
- [x] Build contexts exclude local and sensitive files.
- [x] Both images build on the local arm64 environment.
- [x] Runtime containers execute as non-root.
- [x] Read-only root filesystem and dropped capabilities are verified.
- [x] Compose connects API to Redis through service DNS.
- [x] Redis is not published to the host.
- [x] The complete UI/API/Redis system works through Compose.
- [x] The Redis failure is diagnosed and recovered without rebuilding.
- [x] Trivy configuration and image scans run with a documented policy.
- [x] Pull-request CI has read-only permissions and publishes nothing.
- [x] All actions are pinned to full commit SHAs.
- [x] Main-branch publication produces amd64 and arm64 images.
- [x] GHCR contains API and frontend packages.
- [x] SBOM and provenance attestations are present.
- [x] Published multi-platform digests are recorded without secrets.
- [x] A clean commit produces the same tested publication path.
- [x] Review questions can be answered in your own words.

When every item is true, change this guide and Phase 3 in the canonical
documentation map from `Validated` to `Complete`.

## 29. Review questions

1. Why is an image digest a stronger deployment identity than a tag?
2. What is the difference between a platform manifest and a multi-platform image index?
3. Why should dependency files be copied before application source in a Dockerfile?
4. What does a multi-stage build remove from the final runtime image?
5. What evidence proves non-root execution?
6. Why does `localhost` not identify Redis from inside the API container?
7. Why is Redis intentionally not exposed to the host?
8. What is the difference between an SBOM and provenance?
9. Why can build arguments leak into provenance?
10. Why must pull-request jobs avoid package-write permissions?
11. What did the Redis Compose failure prove beyond the Phase 2 host-process failure?
12. Why is a successful vulnerability scan not permanent evidence that an image remains safe?
13. What is the risk of pinning a GitHub Action only to a mutable version tag?
14. Why does Phase 4 need the published digest rather than rebuilding the image?

## 30. Official references

- Dockerfile overview: <https://docs.docker.com/build/concepts/dockerfile/>
- Multi-stage builds: <https://docs.docker.com/build/building/multi-stage/>
- Build contexts and `.dockerignore`: <https://docs.docker.com/build/concepts/context/>
- Compose networking: <https://docs.docker.com/compose/how-tos/networking/>
- Buildx multi-platform builds: <https://docs.docker.com/build/building/multi-platform/>
- Build attestations: <https://docs.docker.com/build/metadata/attestations/>
- Docker GitHub Actions: <https://docs.docker.com/build/ci/github-actions/>
- GitHub publishing containers: <https://docs.github.com/actions/use-cases-and-examples/publishing-packages/publishing-docker-images>
- GitHub workflow permissions: <https://docs.github.com/actions/security-for-github-actions/security-guides/automatic-token-authentication>
- GitHub artifact attestations: <https://docs.github.com/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations>
- GHCR documentation: <https://docs.github.com/packages/working-with-a-github-packages-registry/working-with-the-container-registry>
- Trivy action: <https://github.com/aquasecurity/trivy-action>
- Trivy 2026 security advisory: <https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23>
- pip-tools: <https://pip-tools.readthedocs.io/>
- NGINX unprivileged image: <https://github.com/nginx/docker-nginx-unprivileged>

## 31. Next phase

After this gate passes, continue to `docs/04-kubernetes-foundation.md`.

Phase 4 will create the multi-node kind cluster, consume the immutable images from this phase, introduce application Deployments and Services through Kustomize, and exercise Pod replacement and Kubernetes-native health probes.
