# Phase 3 — Containers and Continuous Integration Evidence

> Status: Validated
> Recorded on: 2026-10-02 (Asia/Bangkok)
> Source commit: `7cce0dc9963eda7226d8f1e0a5ee1ec6f3cd4da1`
> Pull request: <https://github.com/MyoMyatMin/k8slab/pull/1>
> Publication workflow: <https://github.com/MyoMyatMin/k8slab/actions/runs/36984313577>

## 1. Published release identity

API image:

```text
ghcr.io/myomyatmin/k8slab-api@sha256:44efb6d2bcb8968e5ac01986e70f523b969fa448c6c250da01dd3129fb786fef
```

API platform manifests:

```text
linux/amd64 sha256:6c7e3ed5d79f3dea600df7727f31f6efa01385572f7be3a2b8fc9ddde49b3890
linux/arm64 sha256:5ce90bb857c1f92206cc8a96dfbba7b456b0b527b3649c2f2bd81e17923549b5
```

Frontend image:

```text
ghcr.io/myomyatmin/k8slab-frontend@sha256:689936c57951b9a4c41ec4183891e2b253ed32122b1d0b12bffc0fcb52f0bf2d
```

Frontend platform manifests:

```text
linux/amd64 sha256:5f8719901cf64ec3dfcb220abf9f6d019dc7759522c6100b2b065e197a4cf7c6
linux/arm64 sha256:d8ae19cb13cd38189377cd1aa99fdd1c9165bb8af610364d1b1cce9daff2e2ab
```

The release identities are the top-level multi-platform index digests, not
the individual platform-manifest digests.

## 2. CI and runtime restrictions

Both the branch-push and pull-request CI runs passed before merge. The
main-branch publication workflow repeated the complete validation gate before
receiving publication permissions.

The successful main CI run recorded these effective runtime identities:

```text
api uid=10001
frontend uid=101
redis uid=999
```

The same run passed checks for read-only root filesystems. Compose configured
all services with `cap_drop: [ALL]` and `no-new-privileges:true`; Redis was not
published to the host.

## 3. Scan result summary

- Trivy version: `0.74.0`.
- Dockerfile misconfiguration scan: no HIGH or CRITICAL findings.
- API and frontend HIGH/CRITICAL report steps completed.
- The release gate was configured to fail on fixable CRITICAL findings and
  passed for both images.
- The API report included unfixed upstream operating-system findings; they
  remained visible rather than being silently ignored.
- No project-specific vulnerability exceptions were added.

## 4. SBOM verification

BuildKit attached an SPDX 2.3 SBOM to each platform image. Verification used:

```bash
docker buildx imagetools inspect --format '{{json .SBOM}}' \
  ghcr.io/myomyatmin/k8slab-api@sha256:44efb6d2bcb8968e5ac01986e70f523b969fa448c6c250da01dd3129fb786fef

docker buildx imagetools inspect --format '{{json .SBOM}}' \
  ghcr.io/myomyatmin/k8slab-frontend@sha256:689936c57951b9a4c41ec4183891e2b253ed32122b1d0b12bffc0fcb52f0bf2d
```

Observed summary:

| Image | Platform | SPDX version | Package count |
|---|---|---:|---:|
| API | `linux/amd64` | 2.3 | 158 |
| API | `linux/arm64` | 2.3 | 158 |
| Frontend | `linux/amd64` | 2.3 | 71 |
| Frontend | `linux/arm64` | 2.3 | 71 |

## 5. Provenance verification

GitHub stored one signed build-provenance attestation for each top-level image
digest. Verification constrained the expected repository, signer workflow,
source branch, and source commit:

```bash
gh attestation verify \
  oci://ghcr.io/myomyatmin/k8slab-api@sha256:44efb6d2bcb8968e5ac01986e70f523b969fa448c6c250da01dd3129fb786fef \
  --repo MyoMyatMin/k8slab \
  --signer-workflow MyoMyatMin/k8slab/.github/workflows/publish.yml \
  --source-ref refs/heads/main \
  --source-digest 7cce0dc9963eda7226d8f1e0a5ee1ec6f3cd4da1

gh attestation verify \
  oci://ghcr.io/myomyatmin/k8slab-frontend@sha256:689936c57951b9a4c41ec4183891e2b253ed32122b1d0b12bffc0fcb52f0bf2d \
  --repo MyoMyatMin/k8slab \
  --signer-workflow MyoMyatMin/k8slab/.github/workflows/publish.yml \
  --source-ref refs/heads/main \
  --source-digest 7cce0dc9963eda7226d8f1e0a5ee1ec6f3cd4da1
```

Result: both verifications passed.

## 6. Public pull-by-digest verification

Both packages are public. These anonymous digest pulls succeeded:

```bash
docker pull \
  ghcr.io/myomyatmin/k8slab-api@sha256:44efb6d2bcb8968e5ac01986e70f523b969fa448c6c250da01dd3129fb786fef

docker pull \
  ghcr.io/myomyatmin/k8slab-frontend@sha256:689936c57951b9a4c41ec4183891e2b253ed32122b1d0b12bffc0fcb52f0bf2d
```

Phase 4 must deploy these top-level digests rather than rebuilding or using a
mutable tag.

## 7. Publication incident and recovery

The first publication attempt built and pushed the API image but failed when
`actions/attest` tried to persist a GitHub attestation for a user-owned private
repository. GitHub reported that the feature was unavailable for that
repository visibility and account plan.

Before changing visibility, the current tree, every reachable Git commit, and
existing Actions logs were scanned for high-confidence secret signatures. No
credentials were found. The repository was then made public, and the failed
publication job was rerun against the same source commit. The rerun published
both images and stored both attestations successfully without widening
pull-request workflow permissions.

## 8. Repository protection

The public repository protects `main` with:

- pull requests required;
- the GitHub Actions `Test, build, and scan` check required;
- branches required to be current before merge;
- stale reviews dismissed and conversations required to be resolved;
- enforcement for administrators;
- force-pushes and branch deletion disabled.
