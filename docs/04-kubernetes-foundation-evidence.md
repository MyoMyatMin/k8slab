# Phase 4 — Kubernetes Foundation Evidence

> Status: Complete
> Recorded on: 2026-10-07 (Asia/Bangkok)
> Baseline commit: `9941a0c211855314d1a1115edf2a4edcc6e5a829`
> Learning branch: `phase-4-kubernetes-foundation`
> Application image source commit: `9fbb259cd8b6e5fd3d09742b669289182655243c`

## 1. Environment and configuration

- kind: `v0.33.0`
- Kubernetes: `v1.37.0`
- kubectl: `v1.37.1`
- Kustomize: `v5.8.1`
- Container environment: OrbStack `2.2.3`
- Cluster: `k8slab`
- kubectl context: `kind-k8slab`
- Application namespace: `reliability`

The context guard returned:

```text
SAFE: current Kubernetes context is kind-k8slab.
```

The versioned kind configuration created one control-plane node and two workers.
Both workers have `reliability.dev/workload=true`; the control-plane node does
not.

```text
NAME                   STATUS   ROLES           VERSION   WORKLOAD
k8slab-control-plane   Ready    control-plane   v1.37.0
k8slab-worker          Ready    <none>          v1.37.0   true
k8slab-worker2         Ready    <none>          v1.37.0   true
```

## 2. Kustomize and image identity

The Kustomize base owns the reusable Deployments, Services, probes, resources,
security settings, and generated API ConfigMap. The local overlay owns the
namespace, resource policies, kind worker selector, common managed-by label,
and exact application image digests.

The final render contains three Deployments, three Services, one Namespace, one
ResourceQuota, one LimitRange, and one generated ConfigMap. It contains no
`latest`, `NodePort`, `hostPort`, or `replace-in-overlay` value.

The first Phase 4 CI run detected newly disclosed, fixable critical Debian
findings in the earlier API image. The dependency refresh was isolated in PR
`#6`, updated the pinned base to Python `3.14.8-slim-bookworm`, passed both CI
runs, and published the following replacement images from main commit
`9fbb259cd8b6e5fd3d09742b669289182655243c`. The API replacement reported zero
fixable CRITICAL findings in the blocking Trivy scan.

Deployed images:

```text
ghcr.io/myomyatmin/k8slab-api@sha256:80b24677fbb67cbaacb2334d584a7f98cbc8e9b6f8dab25cb582869ae13a77e5
ghcr.io/myomyatmin/k8slab-frontend@sha256:e0f89ae8c39963d2c10b3821152da43b7503b9f767e63b2d28b355937593178f
redis:8.10.2-alpine3.23@sha256:3811787313eba226a2ef38658c6ccb91cd5e110edc89c37767de373120a0e5a0
```

`kubectl apply --dry-run=server -k kubernetes/overlays/local` accepted every
resource. A final `kubectl diff -k kubernetes/overlays/local` produced no
output, proving that live desired state matched the repository render.

Trivy `v0.74.0` detected eleven Dockerfile/Kubernetes configuration files and
reported zero HIGH or CRITICAL misconfigurations. The local scan used embedded
checks after its optional policy-update credential lookup failed; the checks
still executed and the blocking scan exited successfully.

## 3. Workload and Service verification

Final workload state after cluster recreation:

```text
api        2/2 available
frontend   2/2 available
redis      1/1 available
```

All five Pods were Ready with zero restarts. API and frontend each placed one
replica on each worker. Redis ran on one labeled worker. No application Pod ran
on the control-plane node.

During the image rolling update, both new replicas of each workload briefly
ended up co-located even though the manifest uses `DoNotSchedule`. Each new Pod
was valid against the Pods that existed at its own scheduling instant; later
termination of old replicas changed the final skew. Kubernetes does not
automatically rebalance already scheduled Pods. Deleting one API Pod and one
frontend Pod let their controllers replace them, and the scheduler restored
one replica per worker. A hard scheduling-time constraint is therefore not a
continuous rebalancing mechanism.

Ready Service endpoints matched the current Pod addresses:

```text
SERVICE    ENDPOINTS               READY
api        10.244.1.5,10.244.2.7   true,true
frontend   10.244.1.6,10.244.2.6   true,true
redis      10.244.2.4              true
```

Namespace resource usage matched the declared Pod resources:

```text
pods=5
requests.cpu=300m
requests.memory=384Mi
limits.cpu=1400m
limits.memory=768Mi
```

Runtime identity and root-filesystem checks passed:

```text
api:      uid=10001(app) gid=10001(app)
frontend: uid=101(nginx) gid=101(nginx)
redis:    uid=999(redis) gid=1000(redis)

api-root-filesystem-read-only
frontend-root-filesystem-read-only
redis-root-filesystem-read-only
```

Two host port-forwards provided temporary Phase 4 access. The frontend,
`/health/live`, `/health/ready`, and `/api/v1/visits` all returned HTTP 200. The
API reported `version=phase-4`, Redis `up`, and a correlated request ID.

## 4. Pod replacement experiment

The selected API Pod was:

```text
api-848856c4c8-cw24s  10.244.3.3
```

After deletion, the existing ReplicaSet emitted `SuccessfulCreate` and created:

```text
api-848856c4c8-9xs7w  10.244.3.4
```

The replacement was scheduled, created, started, and became Ready with zero
restarts. Deployment desired replicas remained two. The API EndpointSlice
replaced the old address with the new address while the Service name and
ClusterIP remained stable.

Ownership was:

```text
Deployment/api
  -> ReplicaSet/api-848856c4c8
     -> API Pods
```

## 5. Dependency-readiness failure and recovery

Redis was scaled to zero as a bounded live-state failure. During the failure:

- the Redis EndpointSlice had no endpoint;
- both API containers remained `Running` with zero restarts;
- both API Pods became `0/1` because readiness returned HTTP 503;
- API liveness remained HTTP 200;
- the API EndpointSlice retained the selected Pod addresses with
  `ready=false`;
- frontend Pods remained Ready.

Restarting API Pods would not repair a missing Redis backend. Reapplying the
versioned overlay restored Redis to one replica. Redis became Ready, both API
Pods returned to `1/1`, and the API Service endpoints became ready again. No
image was rebuilt.

## 6. Secret representation exercise

An explicitly non-sensitive temporary Secret was created. Its value appeared
under `data` as base64 and decoded immediately to the original fake marker.
This proved that base64 is representation, not encryption. The Secret was
deleted after the exercise; no real credential or Secret manifest was added to
Git.

## 7. Cluster recreation result

The context and exact cluster name were verified before deletion. The command
`kind delete cluster --name k8slab` removed the control plane, both workers,
cluster API objects, events, and ephemeral Redis data.

The cluster was recreated with the pinned node digest and versioned kind
configuration. The context guard passed, the local overlay was reapplied, and
all Deployments reached `Available`. The four host checks returned HTTP 200.
The visit counter returned to one, demonstrating that Redis's Pod-scoped
`emptyDir` data was intentionally not persistent.

Git-tracked manifests and immutable registry images remained available and
were sufficient to restore the declared platform state.

## 8. Review answers

1. The scheduler selects a node for an unassigned Pod using requests,
   selectors, taints, and topology rules. The kubelet on that node asks the
   container runtime to run the containers, executes probes, and reports
   status.
2. The ownership chain is Deployment -> ReplicaSet -> Pod -> container. The
   kubelet runs the container but is not its declarative controller.
3. Deleting a Pod changes observed state, not the Deployment's desired replica
   count. The ReplicaSet observes the shortage and creates a replacement.
4. A Service selects Pods by stable labels. EndpointSlices record selected
   addresses and their readiness conditions, including temporarily unready
   endpoints. Service DNS and ClusterIP remain stable while Pod addresses
   change.
5. With a selector mismatch, Pods may be Ready while the Service has no
   selected endpoints. With failed readiness, selectors match but Pod
   conditions and probe events show `Ready=false`; EndpointSlices mark those
   endpoints not ready.
6. Redis dependency health belongs in readiness because it determines whether
   an API Pod can serve useful traffic. Liveness should not restart a healthy
   API process for an external dependency failure that restarting cannot fix.
7. ConfigMaps hold non-sensitive configuration. Secrets have distinct API and
   RBAC treatment, but base64 is not encryption; Git protection and etcd
   encryption at rest require separate controls.
8. Requests guide scheduling and reserved capacity. Limits constrain runtime:
   CPU is throttled and exceeding a memory limit can cause an OOM kill.
9. Image pulling happens after scheduling. A valid image cannot make a Pod
   schedulable when requests do not fit, selectors match no node, taints lack
   tolerations, or a hard spread rule cannot be satisfied.
10. Topology spreading reduces the chance that all replicas land on one node.
    kind nodes still share one laptop, kernel, storage, and power source, so
    they are not independent production failure domains. `ScheduleAnyway`
    would make the rule a preference rather than a hard constraint.
11. The base remains portable. The local overlay owns the kind-specific worker
    selector and the exact images selected for this environment; another
    overlay can choose different placement and releases.
12. Pod IPs change on replacement. A Service name and ClusterIP remain stable
    while Kubernetes updates the selected backend endpoints.
13. Cluster API state and Redis's ephemeral `emptyDir` data were lost. Git kept
    declarative manifests, and the registry kept immutable images, so the
    intended state could be recreated.
14. Three Ready nodes with the expected worker labels, no `kubectl diff`, five
    Ready Pods spread across workers, exact deployed image references, ready
    EndpointSlices, and successful host health checks prove recreation.
15. Production would require real failure domains and control-plane HA,
    durable and protected Redis, Gateway/TLS, managed secrets, measured
    resources, disruption budgets, network policies, monitoring, alerting,
    backups, and an appropriate private-registry/signing policy where needed.

## 9. Gate result

Phase 4 passed. The cluster can be recreated from versioned configuration, the
application is reachable from the host, controller-owned Pods self-heal, and
readiness correctly removes dependency-impaired API Pods from eligible Service
traffic without restarting live processes.

The recreated cluster remains running as the starting state for Phase 5.
