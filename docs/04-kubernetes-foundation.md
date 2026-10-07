# Phase 4 — Kubernetes Foundation

> Status: Complete
> Last validated: 2026-10-07
> Version baseline selected: 2026-09-29 for macOS arm64, kind 0.33.0, Kubernetes 1.37.0, kubectl 1.37.1, and Kustomize 5.8.1
> Exercise mode: Challenge-first

## 1. Why this phase matters

Phase 3 produced immutable, multi-platform application images. Those images are
release artifacts, but they are not yet a running platform. This phase teaches
the Kubernetes control loop that turns declarative workload configuration into
running Pods and continually repairs differences between desired and observed
state.

The phase builds this path:

```text
Kustomize base + local overlay
    -> Kubernetes API desired state
    -> Deployment and ReplicaSet controllers
    -> scheduled Pods on kind workers
    -> Services and cluster DNS
    -> host verification through kubectl port-forward
```

Gateway API, network policies, and GitOps are deliberately deferred to Phases
5 and 6. In this phase, `kubectl port-forward` is the temporary host entry path
and `kubectl apply -k` is the deployment mechanism.

## 2. Learning objectives

By the end of this phase, you can:

- explain the roles of the control plane, worker nodes, kubelet, scheduler, and
  controllers;
- distinguish a Pod, ReplicaSet, Deployment, and Service;
- explain labels, selectors, owner references, and Service endpoints;
- create a reproducible multi-node kind cluster with a predictable context;
- organize application manifests as a reusable Kustomize base and local
  overlay;
- deploy immutable images by digest without rebuilding them;
- use ConfigMaps for non-sensitive configuration and explain why Kubernetes
  Secrets are not encrypted merely because their values are base64 encoded;
- design liveness, readiness, and startup behavior without confusing their
  purposes;
- specify and inspect CPU/memory requests and limits;
- explain how scheduling constraints and topology spreading affect placement;
- investigate rollouts, conditions, events, logs, Services, and endpoints;
- predict and prove what happens when a controller-owned Pod is deleted;
- distinguish process liveness from dependency readiness;
- delete and recreate the complete cluster from versioned configuration.

## 3. Exercise mode

This is a core platform phase, so it uses **challenge-first** mode.

You receive the operational contract, constraints, progressive hints, and
verification evidence. You should create each Kubernetes artifact yourself
before asking for a reference implementation. Complete one checkpoint at a
time and request a review when behavior differs from the expected result.

Do not copy a large manifest bundle without understanding which controller
reads each field.

## 4. Prerequisites and safety boundary

- Phases 0–3 are complete on `main`.
- The Phase 3 API and frontend packages are public and pullable by digest.
- OrbStack's Docker-compatible engine is running.
- At least 40 GiB of disk space is available.
- `bash scripts/verify-prerequisites.sh` passes.
- No unrelated local Kubernetes cluster is named `k8slab`.
- No real credential will be stored in a manifest, command history, or Git.

The only authorized cluster name in this phase is `k8slab`; its expected
kubectl context is `kind-k8slab`.

Before every destructive cluster operation:

```bash
kubectl config current-context
bash scripts/require-lab-context.sh
kind get clusters
```

If the context guard blocks, stop and identify the mismatch. Never weaken the
guard merely to make a command run.

## 5. Pinned Phase 4 baseline

Executable version pins remain in `versions.env`.

| Purpose | Pinned value |
|---|---|
| kind | `v0.33.0` |
| Kubernetes | `v1.37.0` |
| kind node image | `kindest/node:v1.37.0@sha256:a1ed...ae5` |
| kubectl | `v1.37.1` |
| Kustomize | `v5.8.1` |
| Cluster name | `k8slab` |
| kubectl context | `kind-k8slab` |
| Application namespace | `reliability` |

Phase 3 recorded the exact release identities in
`docs/03-containers-and-ci-evidence.md`. Phase 4 must consume these top-level
multi-platform digests:

```text
ghcr.io/myomyatmin/k8slab-api@sha256:44efb6d2bcb8968e5ac01986e70f523b969fa448c6c250da01dd3129fb786fef
ghcr.io/myomyatmin/k8slab-frontend@sha256:689936c57951b9a4c41ec4183891e2b253ed32122b1d0b12bffc0fcb52f0bf2d
```

Do not replace these with `latest`, a mutable tag, or a locally rebuilt image.

## 6. Files you will create or change

```text
cluster/
└── kind/
    └── kind.yaml
kubernetes/
├── base/
│   ├── kustomization.yaml
│   ├── api-deployment.yaml
│   ├── api-service.yaml
│   ├── frontend-deployment.yaml
│   ├── frontend-service.yaml
│   ├── redis-deployment.yaml
│   └── redis-service.yaml
└── overlays/
    └── local/
        ├── kustomization.yaml
        ├── namespace.yaml
        ├── resource-quota.yaml
        └── limit-range.yaml
docs/
└── 04-kubernetes-foundation-evidence.md
```

You may split patches into clearly named files if that makes your design easier
to review. Do not add Gateway, Ingress, Argo CD, monitoring, or network-policy
resources in this phase.

## 7. Concepts and vocabulary

| Term | Meaning in this project |
|---|---|
| Cluster | One Kubernetes control plane plus worker capacity |
| Node | A machine-like Kubernetes worker; in kind it is a container |
| Control plane | API server and controllers that store and reconcile desired state |
| Pod | Smallest scheduled unit; one or more tightly coupled containers |
| ReplicaSet | Controller that keeps a selected number of matching Pods present |
| Deployment | Controller that manages ReplicaSets and rolling application updates |
| Service | Stable virtual address and DNS name selecting a changing set of Pods |
| EndpointSlice | API representation of the ready backends selected by a Service |
| Label | Key/value metadata used for grouping and selection |
| Selector | Query that binds controllers or Services to labeled objects |
| ConfigMap | Non-sensitive configuration stored in the Kubernetes API |
| Secret | Sensitive-data API object; base64 representation is not encryption |
| Probe | Kubelet check for startup, liveness, or readiness behavior |
| Request | Resource amount used by the scheduler when placing a Pod |
| Limit | Runtime ceiling enforced by the node where supported |
| Event | Short-lived Kubernetes record explaining recent decisions or failures |
| Reconciliation | Repeated work to make observed state match desired state |
| Overlay | Environment-specific transformation of reusable Kustomize resources |

Remember this ownership chain:

```text
Deployment -> ReplicaSet -> Pod -> container
Service -----------------------> selected ready Pod IPs
```

Deleting a Pod does not delete its Deployment. The ReplicaSet notices that its
observed replica count is below the desired count and creates a replacement.

## 8. Step 1 — Create the learning branch

Start only after the guide itself is on `main`:

```bash
cd /Users/m3/Desktop/k8slab
git switch main
git pull --ff-only origin main
git status --short
git switch -c phase-4-kubernetes-foundation
```

Expected: `git status --short` is empty before branch creation.

Do not mix later Phase 5 networking work into this branch.

## 9. Step 2 — Verify prerequisites and record predictions

Run:

```bash
cd /Users/m3/Desktop/k8slab
bash scripts/verify-prerequisites.sh
kind version
kubectl version --client
kustomize version
docker info >/dev/null
kind get clusters
```

Before creating anything, write answers in your learning notes:

1. Which component decides which node receives a new Pod?
2. If a Pod IP changes, why can clients continue using the same Service name?
3. What should happen when one API Pod in a two-replica Deployment is deleted?
4. Why should Redis failure affect API readiness but not API liveness?
5. What is lost when the kind cluster is deleted, and what remains in Git?
6. Why is a Kubernetes Secret not automatically safe to commit?
7. What is the difference between a resource request and a limit?
8. Which fields must match for a Service to select its intended Pods?

These predictions become part of the phase evidence.

## 10. Step 3 — Design the kind topology

Create `cluster/kind/kind.yaml`.

### Operational contract

- Use kind configuration API `kind.x-k8s.io/v1alpha4`.
- Name the cluster `k8slab`.
- Define exactly one control-plane node and two worker nodes.
- Give both workers the label `reliability.dev/workload=true`.
- Do not map application ports from a worker container to the host; Phase 4
  uses `kubectl port-forward`, and Phase 5 will own external traffic.
- Do not remove the control-plane scheduling taint.
- Do not embed host-specific absolute paths.

### Predict

Why are two workers useful for a replacement and scheduling exercise even
though they still share one laptop and one container engine?

### Progressive hints

<details>
<summary>Hint 1</summary>

A kind cluster configuration has `kind: Cluster`, an `apiVersion`, a `name`,
and a `nodes` list. Each list item declares a role.

</details>

<details>
<summary>Hint 2</summary>

kind node entries support a `labels` map. Apply the same workload label to each
worker, not to the control-plane node.

</details>

Review the file before cluster creation:

```bash
sed -n '1,220p' cluster/kind/kind.yaml
grep -c 'role: worker' cluster/kind/kind.yaml
grep -c 'reliability.dev/workload' cluster/kind/kind.yaml
```

Expected: two worker entries and two workload-label entries.

## 11. Step 4 — Create the pinned cluster safely

First confirm that no cluster with this name exists:

```bash
kind get clusters
```

If `k8slab` already exists, do not overwrite it. Inspect its context and decide
whether it is the lab cluster from an earlier attempt.

Load the pinned node-image value and create the cluster:

```bash
cd /Users/m3/Desktop/k8slab
set -a
source versions.env
set +a

kind create cluster \
  --name k8slab \
  --image "$KIND_NODE_IMAGE" \
  --config cluster/kind/kind.yaml \
  --wait 120s
```

Immediately verify the safety boundary:

```bash
kubectl config current-context
bash scripts/require-lab-context.sh
kubectl cluster-info --context kind-k8slab
kubectl get nodes -o wide
```

Expected:

- current context is `kind-k8slab`;
- three nodes report `Ready`;
- the Kubernetes version is 1.37.0;
- one node is control-plane and two are workers.

Do not continue if any node remains `NotReady`. Inspect first:

```bash
kubectl describe node <exact-node-name>
kubectl get events -A --sort-by=.metadata.creationTimestamp
docker ps --filter name=k8slab
```

## 12. Step 5 — Investigate the control plane and scheduling inputs

Collect evidence:

```bash
kubectl get nodes --show-labels
kubectl get pods -n kube-system -o wide
kubectl describe node k8slab-control-plane
kubectl describe node k8slab-worker
kubectl describe node k8slab-worker2
```

Answer before continuing:

1. Which control-plane components are visible as Pods?
2. Which taint normally prevents ordinary workloads from using the control
   plane?
3. Which two nodes have `reliability.dev/workload=true`?
4. Does three kind nodes mean three independent physical failure domains? Why
   not?

## 13. Step 6 — Design namespace resource boundaries

Create the local-overlay resources:

- `kubernetes/overlays/local/namespace.yaml`
- `kubernetes/overlays/local/resource-quota.yaml`
- `kubernetes/overlays/local/limit-range.yaml`

### Required contract

- Namespace name is `reliability`.
- All three objects explicitly identify that namespace where applicable.
- ResourceQuota allows at least 20 Pods, 2 CPU requests, 2 GiB memory requests,
  4 CPU limits, and 4 GiB memory limits.
- LimitRange prevents obviously unbounded individual containers without
  silently replacing the requirement to declare explicit resources.
- Names and labels follow the `app.kubernetes.io/*` label convention.

Do not apply them yet. First explain:

- what ResourceQuota limits across the namespace;
- what LimitRange constrains per object or container;
- why neither mechanism measures real application usage.

## 14. Step 7 — Design the reusable Kustomize base

Create `kubernetes/base/kustomization.yaml` and the six workload/Service files
listed in Section 6.

### Base-wide contract

- Use stable Kubernetes APIs: `apps/v1` for Deployments and `v1` for Services.
- Every object has `app.kubernetes.io/name`, `component`, `part-of`, and
  `managed-by` labels.
- Deployment selectors are explicit and immutable in meaning.
- Pod-template labels satisfy the matching Deployment selector.
- Service selectors use only stable identity labels, not version labels.
- Containers expose named ports.
- Every container declares CPU/memory requests and limits.
- All application images use `imagePullPolicy: IfNotPresent` with immutable
  digests supplied by the overlay.
- Workloads select nodes labeled `reliability.dev/workload=true` in the local
  environment.
- API and frontend run two replicas; Redis runs one replica.
- API and frontend replicas use topology spreading across
  `kubernetes.io/hostname` where possible.
- No Namespace, host port, NodePort, Gateway, Ingress, plaintext credential, or
  locally built image belongs in the base.

### Kustomize responsibility

The base owns reusable application behavior. The local overlay owns:

- namespace placement;
- exact Phase 3 image digests;
- kind-specific worker scheduling;
- local quotas and limits;
- replica changes that are specific to this environment.

Before writing YAML, sketch which fields belong in the base and which belong
in the overlay. Avoid duplicating a complete Deployment just to change one
field.

## 15. Step 8 — Add non-sensitive API configuration

Use `configMapGenerator` in the base or a dedicated ConfigMap manifest. Supply:

```text
APP_NAME=reliability-api
APP_VERSION=phase-4
APP_ENVIRONMENT=kubernetes-local
REDIS_URL=redis://redis:6379/0
ENABLE_FAILURE_INJECTION=true
LOG_LEVEL=INFO
OTEL_CONSOLE_EXPORTER=false
```

The API Deployment must consume this configuration without copying the same
values into multiple manifests.

Questions to answer:

1. Why does `redis` resolve inside the namespace?
2. Why would `127.0.0.1` be wrong inside the API Pod?
3. If Kustomize appends a content hash to a generated ConfigMap name, how can
   that help trigger a rollout after configuration changes?
4. Which of these values would be inappropriate in a ConfigMap if it were a
   real credential?

Do not put passwords or tokens in this ConfigMap.

## 16. Step 9 — Build the Redis workload and Service

Create the Redis Deployment and Service first.

### Required contract

- Use the exact Redis tag and digest from `versions.env`.
- Use one replica and document that it is ephemeral in this phase.
- The container port is named `redis` and is 6379.
- The Service is `ClusterIP`, named `redis`, and exposes port 6379.
- The Service selector exactly matches the Redis Pod identity labels.
- Use an exec readiness probe that proves Redis responds, not merely that its
  TCP port opened.
- Use a separate liveness probe with conservative timing.
- Declare explicit resource requests and limits.
- Do not publish Redis to the host.
- Do not add persistence, authentication, or a StatefulSet yet; record these as
  production gaps instead of hiding them.

Verification will later use `redis.reliability.svc.cluster.local`, although the
short name `redis` works for callers in the same namespace.

## 17. Step 10 — Build the API Deployment and Service

### Required contract

- The base refers to image name `ghcr.io/myomyatmin/k8slab-api`; the local
  overlay replaces it with the recorded digest.
- Use two replicas.
- Container port `http` is 8000; Service `api` exposes port 8000.
- Readiness checks `GET /health/ready`.
- Liveness checks `GET /health/live`.
- Add a startup probe if your initial-delay design otherwise risks premature
  liveness restarts.
- Set a termination grace period and allow enough time for Uvicorn shutdown.
- Consume the API ConfigMap.
- Declare explicit requests and limits.
- Retain the image's non-root user; do not override it to UID 0.
- Add pod-level and container-level security settings that preserve the Phase 3
  non-root, no-privilege-escalation, read-only-root-filesystem contract.
- Add only the scoped writable temporary storage the process actually needs.

Explain why the Redis-dependent readiness path must not also be used as the
liveness path.

## 18. Step 11 — Build the frontend Deployment and Service

### Required contract

- The base refers to image name `ghcr.io/myomyatmin/k8slab-frontend`; the local
  overlay replaces it with the recorded digest.
- Use two replicas.
- Container port `http` is 8080; Service `frontend` exposes port 80 and targets
  the named container port.
- Readiness and liveness use HTTP `GET /` against the named port.
- Preserve the image's non-root and read-only runtime restrictions.
- Declare explicit requests and limits.
- Spread replicas across workers where possible.

The frontend JavaScript still calls the API at host port 8000. During Phase 4,
you will run separate frontend and API port-forwards. Phase 5 will replace this
temporary access pattern with Gateway API routing.

## 19. Step 12 — Build the local overlay

Create `kubernetes/overlays/local/kustomization.yaml`.

### Required contract

- Reference `../../base`.
- Include Namespace, ResourceQuota, and LimitRange resources.
- Set `namespace: reliability` for namespaced resources.
- Replace API and frontend image names with the exact Phase 3 digests from
  Section 5.
- Apply the worker-node selector only in the local overlay if you want the base
  to remain portable.
- Use focused patches; do not duplicate whole base manifests.
- Do not add a mutable tag alongside a digest.

Inspect your Kustomize version before choosing patch syntax:

```bash
kustomize version
```

Prefer current `patches` syntax rather than deprecated patch fields.

## 20. Step 13 — Render and inspect before applying

Render locally:

```bash
cd /Users/m3/Desktop/k8slab
mkdir -p /tmp/k8slab-phase4
kubectl kustomize kubernetes/overlays/local \
  > /tmp/k8slab-phase4/rendered.yaml
```

Inspect for required and prohibited content:

```bash
grep -nE 'kind: (Deployment|Service|Namespace|ResourceQuota|LimitRange|ConfigMap)' \
  /tmp/k8slab-phase4/rendered.yaml
grep -n 'sha256:' /tmp/k8slab-phase4/rendered.yaml
grep -nE 'startupProbe|readinessProbe|livenessProbe|requests:|limits:' \
  /tmp/k8slab-phase4/rendered.yaml
grep -nE 'latest|NodePort|hostPort|replace-in-overlay|password|token' \
  /tmp/k8slab-phase4/rendered.yaml || true
```

Expected:

- three Deployments and three Services;
- one Namespace, ResourceQuota, LimitRange, and generated ConfigMap;
- both application digests and the pinned Redis digest;
- probes and resources for every container;
- no `latest`, NodePort, hostPort, password, or token.

First ask kubectl to validate the complete render locally:

```bash
bash scripts/require-lab-context.sh
kubectl apply --dry-run=client -k kubernetes/overlays/local
```

Server-side validation requires the target namespace to already exist. A
server-side dry-run Namespace is not persisted, so the API server cannot use it
for the later namespaced requests in the same command. Check for the namespace:

```bash
kubectl get namespace reliability
```

On the first run, `NotFound` is expected. Create only this intended namespace
from its versioned manifest:

```bash
kubectl apply -f kubernetes/overlays/local/namespace.yaml
```

This is the sole persisted object in Step 13. Step 14 will apply the overlay and
add its transformed labels. Now validate all rendered resources against the
live API schema and admission rules without persisting them:

```bash
kubectl apply --dry-run=server -k kubernetes/overlays/local
```

Fix schema, selector, namespace, and policy errors before the real apply.

## 21. Step 14 — Apply and observe reconciliation

Apply the overlay:

```bash
bash scripts/require-lab-context.sh
kubectl apply -k kubernetes/overlays/local
```

Observe rather than immediately retrying commands:

```bash
kubectl get all -n reliability
kubectl get pods -n reliability -o wide --watch
```

Stop the watch with `Ctrl+C` after all Pods are ready. Then verify each rollout:

```bash
kubectl rollout status deployment/redis -n reliability --timeout=120s
kubectl rollout status deployment/api -n reliability --timeout=120s
kubectl rollout status deployment/frontend -n reliability --timeout=120s
kubectl get deployments,replicasets,pods -n reliability -o wide
```

If a rollout fails, do not delete random Pods. Collect evidence:

```bash
kubectl describe deployment <exact-name> -n reliability
kubectl describe pod <exact-pod-name> -n reliability
kubectl logs <exact-pod-name> -n reliability --all-containers
kubectl get events -n reliability --sort-by=.metadata.creationTimestamp
```

## 22. Step 15 — Verify Services, endpoints, probes, and resources

Run:

```bash
kubectl get services -n reliability
kubectl get endpointslices -n reliability \
  -o custom-columns='NAME:.metadata.name,SERVICE:.metadata.labels.kubernetes\.io/service-name,ENDPOINTS:.endpoints[*].addresses[*],READY:.endpoints[*].conditions.ready'
kubectl get pods -n reliability -o custom-columns='NAME:.metadata.name,NODE:.spec.nodeName,READY:.status.containerStatuses[*].ready,RESTARTS:.status.containerStatuses[*].restartCount'
kubectl get resourcequota,limitrange -n reliability
kubectl describe resourcequota -n reliability
```

For one Pod from each workload, inspect:

```bash
kubectl describe pod <api-pod> -n reliability
kubectl describe pod <frontend-pod> -n reliability
kubectl describe pod <redis-pod> -n reliability
```

Prove these claims from output:

- Services select the intended ready Pod IPs.
- API and frontend replicas are distributed across workers where possible.
- requests and limits are visible for every container.
- API readiness differs in meaning from API liveness.
- no application Pod is scheduled on the control-plane node.

## 23. Step 16 — Reach the application from the host

Use two terminals and keep both commands in the foreground.

Terminal A:

```bash
kubectl port-forward -n reliability service/frontend 8080:80
```

Terminal B:

```bash
kubectl port-forward -n reliability service/api 8000:8000
```

From a third terminal:

```bash
curl -i http://127.0.0.1:8080/
curl -i http://127.0.0.1:8000/health/live
curl -i http://127.0.0.1:8000/health/ready
curl -i http://127.0.0.1:8000/api/v1/visits
```

Open `http://127.0.0.1:8080` and use the dashboard actions.

Expected:

- frontend returns 200;
- API liveness returns 200;
- API readiness returns 200 with Redis up;
- visits returns a counter and request ID;
- the dashboard reaches the separately forwarded API.

`port-forward` is a debugging tunnel, not a production ingress design.

## 24. Step 17 — Controlled failure: delete a controller-owned Pod

### Hypothesis

Deleting one API Pod should reduce the observed replica count briefly. The
ReplicaSet should create a new Pod because the Deployment still desires two.
The old Pod name must disappear, a new Pod name must appear, and the Service
should eventually have two ready API endpoints again.

### Safety and abort conditions

- Confirm context `kind-k8slab` with the guard script.
- Operate only in namespace `reliability`.
- Delete exactly one Pod selected by the API component label.
- Abort if more than one application workload becomes unavailable or if the
  replacement cannot become Ready within two minutes.
- Recovery is reapplying the overlay and inspecting rollout events; do not
  delete the namespace.

### Observe and inject

In one terminal:

```bash
kubectl get pods -n reliability -l app.kubernetes.io/component=api --watch
```

In another:

```bash
bash scripts/require-lab-context.sh
OLD_POD="$(kubectl get pods -n reliability \
  -l app.kubernetes.io/component=api \
  -o jsonpath='{.items[0].metadata.name}')"
printf 'Deleting %s\n' "$OLD_POD"
kubectl delete pod -n reliability "$OLD_POD"
kubectl rollout status deployment/api -n reliability --timeout=120s
```

Collect evidence:

```bash
kubectl get deployment,replicaset,pods -n reliability \
  -l app.kubernetes.io/component=api -o wide
kubectl get events -n reliability --sort-by=.metadata.creationTimestamp
kubectl get endpointslices -n reliability \
  -l kubernetes.io/service-name=api -o wide
```

Answer:

1. Which controller created the replacement?
2. Did the Deployment's desired replicas change?
3. Did the replacement retain the same Pod IP or name?
4. Which stable identity allowed the Service to include it?
5. Which event or condition proves scheduling and startup succeeded?

## 25. Step 18 — Controlled failure: dependency readiness

### Hypothesis

Scaling Redis to zero should leave API processes live but make API Pods
unready. Kubernetes should remove unready API Pods from normal Service traffic.
Restoring the declarative overlay should return Redis, API readiness, and
Service endpoints without rebuilding an image.

### Safety

- Stop or restart port-forwards as needed; a Service forward may terminate when
  it has no ready backend.
- Scope every command to namespace `reliability`.
- Do not edit the application image or weaken its probes.
- Abort after five minutes if recovery does not converge.

Start a direct forward to one API Deployment Pod:

```bash
kubectl port-forward -n reliability deployment/api 8000:8000
```

In another terminal, inject and observe:

```bash
bash scripts/require-lab-context.sh
kubectl scale deployment/redis -n reliability --replicas=0
kubectl get pods,endpointslices -n reliability --watch
```

From a third terminal:

```bash
curl -i http://127.0.0.1:8000/health/live
curl -i http://127.0.0.1:8000/health/ready
```

Expected: liveness remains 200; readiness becomes 503; API Pods transition to
not Ready; normal API Service endpoints cease being ready.

Recover through the versioned desired state:

```bash
kubectl apply -k kubernetes/overlays/local
kubectl rollout status deployment/redis -n reliability --timeout=120s
kubectl rollout status deployment/api -n reliability --timeout=120s
kubectl get pods,endpointslices -n reliability
curl -i http://127.0.0.1:8000/health/ready
```

Explain why restarting API Pods would not have repaired the missing Redis
dependency.

## 26. Step 19 — Secret representation exercise

This short exercise uses an explicitly non-sensitive value. It does not add a
Secret manifest to Git.

```bash
bash scripts/require-lab-context.sh
kubectl create secret generic phase4-example \
  -n reliability \
  --from-literal=example=not-a-real-credential
kubectl get secret phase4-example -n reliability -o yaml
kubectl get secret phase4-example -n reliability \
  -o jsonpath='{.data.example}' | base64 --decode
printf '\n'
kubectl delete secret phase4-example -n reliability
```

The exercise proves that base64 is representation, not encryption. Do not run
these commands with real credentials because shell history, terminal output,
and API access can expose them. Phase 14 introduces the SOPS/age workflow and
least-privilege secret access.

## 27. Step 20 — Prove full cluster recreation

This is the destructive phase gate. It permanently removes only the named kind
cluster and its cluster-local state; it does not move anything to macOS Trash.
Git-tracked configuration and registry images remain recoverable.

First save sanitized evidence and stop all port-forwards. Then verify scope:

```bash
kubectl config current-context
bash scripts/require-lab-context.sh
kind get clusters
git status --short
```

Delete only the named cluster:

```bash
kind delete cluster --name k8slab
kind get clusters
```

Recreate from the pinned configuration:

```bash
set -a
source versions.env
set +a

kind create cluster \
  --name k8slab \
  --image "$KIND_NODE_IMAGE" \
  --config cluster/kind/kind.yaml \
  --wait 120s

bash scripts/require-lab-context.sh
kubectl apply -k kubernetes/overlays/local
kubectl wait --for=condition=Available deployment --all \
  -n reliability --timeout=180s
kubectl get nodes
kubectl get all -n reliability
```

Repeat the four host requests from Step 16. The visit counter may restart
because Redis is deliberately ephemeral; application configuration and image
identity must remain the same.

## 28. Evidence record

Create `docs/04-kubernetes-foundation-evidence.md` only after the exercises.
Keep it concise and sanitized:

```markdown
# Phase 4 — Kubernetes Foundation Evidence

## Environment and source commit

## Cluster topology

## Rendered image identities

## Workload and Service verification

## Pod replacement timeline

## Dependency-readiness failure and recovery

## Cluster recreation result

## Explanation in my own words

## Gate result
```

Record commands and meaningful output, not huge logs. Do not include Secret
values, kubeconfig contents, tokens, or generated certificates.

## 29. Troubleshooting

| Symptom | Evidence to collect | Likely causes | Next falsifiable test |
|---|---|---|---|
| kind cluster creation fails | `kind` output, node containers, disk | engine unavailable, wrong digest, low capacity | `docker info`; inspect exact failed node container |
| Context guard blocks | current context and `kind get clusters` | wrong cluster selected | switch explicitly only after confirming `kind-k8slab` exists |
| Node stays `NotReady` | node conditions and kube-system Pods | CNI or kubelet startup failure | inspect `kubectl describe node` and control-plane logs |
| Kustomize render fails | exact file path and error | missing resource, invalid patch target, YAML error | render the base alone, then the overlay |
| Server dry-run rejects object | API error and rendered object | wrong API version, schema, immutable selector | inspect the exact rendered resource around the field |
| Pod is `Pending` | Pod events and node allocatable values | selector mismatch, requests too large, taint | compare node labels/taints with Pod scheduling fields |
| `ImagePullBackOff` | Pod events and image field | wrong digest, private package, registry/network failure | pull the exact digest from the host and inspect event reason |
| Pod is `CrashLoopBackOff` | current and previous logs | command/config/runtime write failure | `kubectl logs --previous` and inspect exit code/events |
| API never becomes Ready | API logs, readiness response, Redis Pod/Service/endpoints | Redis unavailable or wrong URL/selector | forward directly to API and query both health endpoints |
| Service has no ready endpoints | selectors, Pod labels, readiness | selector mismatch or all Pods unready | compare Service selector to Pod labels, then inspect probes |
| Port-forward disconnects | selected Pod and rollout status | target Pod replaced or no ready Service backend | restart forward after workload becomes Available |
| Quota blocks Pod creation | ReplicaSet and namespace events | summed requests/limits exceed quota | `kubectl describe resourcequota` and calculate requested totals |
| Replacement Pod never appears | Deployment/ReplicaSet status and events | controller absent, quota, scheduling, invalid template | inspect owner chain and newest ReplicaSet events |

Do not treat repeated deletion as diagnosis. Each next action should test one
specific hypothesis.

## 30. Production considerations

- kind nodes are containers on one laptop, not independent availability zones.
- One control-plane node is intentionally not highly available.
- `kubectl port-forward` is a debugging tool; Phase 5 introduces Gateway API.
- Redis is a single ephemeral Deployment. Production state normally requires a
  deliberate persistence, backup, availability, authentication, and licensing
  design.
- Requests and limits here are learning baselines, not capacity-planning
  results. Later phases measure and tune them under load.
- Liveness should detect an unrecoverable process, not restart an application
  merely because a dependency is unavailable.
- Readiness protects traffic routing but does not repair the dependency.
- A Secret without encryption-at-rest controls and restricted RBAC is not a
  complete secret-management solution.
- Namespace quotas reduce accidental contention but do not create hard tenant
  isolation by themselves.
- Digest pinning preserves identity but also requires an intentional update
  process for security fixes.
- Deployments are appropriate for the stateless frontend/API; stateful Redis
  design is intentionally deferred.

## 31. Cleanup and reset

To remove only the application while keeping the cluster:

```bash
kubectl config current-context
bash scripts/require-lab-context.sh
kubectl delete -k kubernetes/overlays/local
```

To remove only the named lab cluster:

```bash
kubectl config current-context
bash scripts/require-lab-context.sh
kind delete cluster --name k8slab
```

Cluster deletion is not recoverable from the cluster itself. It deletes Pods,
events, generated cluster credentials, and ephemeral Redis data. Recovery is
recreation from Git plus pulling the immutable registry images.

Do not run global Docker prune commands. They can remove unrelated user data.

## 32. Definition of done

- [x] Phase 3 is complete and the recorded image digests are pullable.
- [x] Phase 4 work is isolated on its own branch.
- [x] The kind configuration declares one control plane and two labeled workers.
- [x] Cluster creation uses the pinned kind node digest.
- [x] The active context is proven to be `kind-k8slab` before mutations.
- [x] All three nodes become Ready.
- [x] Namespace, ResourceQuota, and LimitRange are versioned.
- [x] Kustomize base and local overlay render without errors.
- [x] API and frontend deploy the recorded immutable Phase 3 digests.
- [x] Redis deploys its pinned image digest and is not exposed to the host.
- [x] All workload containers declare requests and limits.
- [x] Workloads preserve non-root and read-only runtime restrictions.
- [x] Liveness and readiness probes have distinct justified meanings.
- [x] Services select the intended ready endpoints.
- [x] Application Pods schedule only on labeled workers.
- [x] API and frontend replicas spread across workers where possible.
- [x] Frontend, API liveness, API readiness, and visits work from the host.
- [x] Deleting one API Pod produces a controller-created replacement.
- [x] Redis loss leaves API live but removes API readiness.
- [x] Dependency recovery occurs without rebuilding an image.
- [x] Secret representation is explained without committing a credential.
- [x] The cluster is deleted and recreated successfully from versioned files.
- [x] Sanitized phase evidence is recorded.
- [x] No plaintext secret, kubeconfig, token, or generated certificate is staged.
- [x] Review questions can be answered in your own words.

The guide remains `Draft` while you work. Change it and the canonical
documentation map to `Validated` only after every technical gate is reproduced.
Change them to `Complete` only after the troubleshooting, reset, evidence, and
review gates are also satisfied.

## 33. Review questions

1. What is the responsibility of the scheduler versus the kubelet?
2. What is the ownership chain from Deployment to a running container?
3. Why did deleting a Pod not reduce the desired replica count permanently?
4. How does a Service find replacement Pods without relying on their IPs?
5. What evidence distinguishes a selector mismatch from failed readiness?
6. Why is API dependency health appropriate for readiness but not liveness?
7. What is the difference between a ConfigMap and a Secret, and what protection
   does a Secret not provide by itself?
8. How do resource requests affect scheduling, and how do limits affect runtime?
9. Why can a Pod remain Pending even when the container image is valid?
10. What does topology spreading improve, and what can it not guarantee in a
    kind cluster on one laptop?
11. Why does the local overlay own kind-specific scheduling and exact digests?
12. Why are Service names more stable dependencies than Pod IP addresses?
13. Which data disappeared during cluster recreation, and why?
14. What evidence proves the recreated cluster matches the intended state?
15. Which Phase 4 shortcuts must change in a production design?

## 34. Official references

- kind configuration: <https://kind.sigs.k8s.io/docs/user/configuration/>
- Kubernetes components: <https://kubernetes.io/docs/concepts/overview/components/>
- Deployments: <https://kubernetes.io/docs/concepts/workloads/controllers/deployment/>
- Services: <https://kubernetes.io/docs/concepts/services-networking/service/>
- EndpointSlices: <https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/>
- Labels and selectors: <https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/>
- ConfigMaps: <https://kubernetes.io/docs/concepts/configuration/configmap/>
- Secrets: <https://kubernetes.io/docs/concepts/configuration/secret/>
- Probes: <https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/>
- Resource management: <https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/>
- ResourceQuota: <https://kubernetes.io/docs/concepts/policy/resource-quotas/>
- LimitRange: <https://kubernetes.io/docs/concepts/policy/limit-range/>
- Assigning Pods to nodes: <https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/>
- Topology spread constraints: <https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/>
- Kubernetes events: <https://kubernetes.io/docs/reference/kubernetes-api/cluster-resources/event-v1/>
- Kustomize: <https://kubectl.docs.kubernetes.io/guides/introduction/kustomize/>

## 35. Next phase

After this phase gate passes, continue to
`docs/05-networking-and-gateway-api.md`.

Phase 5 will replace temporary port-forwards with Envoy Gateway and Gateway API,
then teach DNS, EndpointSlice selection, default-deny network policy, allowed
flows, and connectivity diagnosis.
