# Phase 6 — GitOps with Argo CD

> Status: Draft
>
> Last validated: Not yet validated
>
> Version baseline selected: 2026-10-10 for Argo CD 3.5.4, Kubernetes 1.37.0, kind 0.33.0, Helm 4.3.0, and Kustomize 5.8.1
>
> Exercise mode: Challenge-first for bootstrap boundaries, AppProjects, Applications, reconciliation, drift, pruning, and Git-based rollback

## 1. Why this phase matters

Phases 4 and 5 stored desired Kubernetes state in Git, but a human still ran
`kubectl apply` and Helm lifecycle commands. Git contained the intended state,
yet nothing continuously compared that intent with the live cluster.

Phase 6 introduces a reconciliation loop:

```text
Git main branch
    |
    | Argo CD polls and renders
    v
desired Kubernetes objects
    |
    | compare desired with live
    v
Argo CD sync status
    |
    | automated sync, prune, and self-heal
    v
live kind cluster
```

After the transition, normal application and platform changes follow this
path:

```text
edit -> review -> merge -> Argo CD detects -> sync -> verify
```

CI still tests and publishes artifacts. CI does not receive cluster-admin
credentials and does not deploy with `kubectl`. Argo CD pulls declared state
from Git and reconciles it inside the cluster.

The phase also makes ownership explicit. Some components must exist before a
GitOps controller can run:

```text
Bootstrap-managed:
  kind cluster -> Calico CNI -> Argo CD installation -> root Application

Argo CD-managed after bootstrap:
  AppProject -> Envoy Gateway CRDs/controller -> reliability workload
```

Calico remains bootstrap-managed because Argo CD cannot communicate before Pod
networking exists. Argo CD itself and its first root Application are the second
unavoidable bootstrap boundary. Everything above that boundary is reconciled
from Git.

## 2. Learning objectives

By the end of this phase, you can:

- distinguish Git desired state, live state, sync status, and health status;
- explain the Argo CD bootstrap chicken-and-egg boundary;
- describe the roles of repository server, application controller, API server,
  Application, AppProject, and root Application;
- install Argo CD from an immutable upstream revision;
- constrain sources, destinations, and cluster-scoped resources with an
  AppProject;
- manage Kustomize and OCI Helm sources declaratively;
- interpret `Synced`, `OutOfSync`, `Healthy`, `Progressing`, `Degraded`, and
  sync-operation results;
- deliver a Kubernetes change through a Git merge rather than direct apply;
- observe live drift and prove automatic self-healing;
- prove that deleting desired state causes an intentional prune;
- distinguish sync failure, health failure, source failure, and authorization
  failure;
- recover by reverting Git and explain why durable rollback changes desired
  state;
- identify which resources remain bootstrap-owned and why.

## 3. Exercise mode

This phase uses **challenge-first** mode because GitOps artifacts express
platform ownership and security decisions.

Each build step provides:

1. an operational contract;
2. safety constraints;
3. evidence to collect;
4. progressive hints;
5. a reference shape only after an attempt.

Do not copy a finished Application without being able to identify its source,
revision, render path, destination, project, sync policy, and deletion effect.

## 4. Prerequisites and safety boundary

- Phase 5 is complete on `main`.
- The local worktree starts clean.
- Current context is `kind-k8slab`.
- All three kind nodes are Ready.
- Calico reports Available and is not managed by Argo CD.
- Envoy Gateway and the reliability application are healthy before ownership
  transfer.
- The GitHub repository is public, so this phase needs no repository token in
  the cluster.
- Application images remain pinned by digest.
- No port-forward from an earlier exercise is left running.

Run:

```bash
git switch main
git pull --ff-only origin main
git status --short

bash scripts/require-lab-context.sh
kubectl get nodes -L reliability.dev/workload
kubectl get tigerastatus
kubectl get gatewayclass
kubectl get gateways,httproutes -n reliability
curl --fail-with-body http://reliability.localhost:8080/health/ready

gh repo view MyoMyatMin/k8slab --json visibility,url
```

Stop if:

- the worktree is dirty for unrelated reasons;
- the current context is not `kind-k8slab`;
- the repository is private and no deliberate credential design exists;
- Phase 5 is not healthy before transfer.

The only disposable cluster authorized by this guide is:

```text
name:     k8slab
context:  kind-k8slab
```

## 5. Pinned Phase 6 baseline

`versions.env` is authoritative:

| Purpose | Pin |
|---|---|
| Kubernetes | `v1.37.0` |
| kind | `v0.33.0` |
| Helm | `v4.3.0` |
| Kustomize | `v5.8.1` |
| Argo CD | `v3.5.4` |
| Argo CD install commit | `d6d5b248ce00e1a2c512068002a93d3319767087` |
| Envoy Gateway | `v1.9.2` |
| Git repository | `https://github.com/MyoMyatMin/k8slab.git` |
| Tracked revision | `main` |
| In-cluster API | `https://kubernetes.default.svc` |
| Argo CD namespace | `argocd` |

The Argo CD release is pinned to an immutable release commit. Do not use the
mutable `stable` branch in executable configuration.

The official Argo CD tested-version table for the 3.5 line currently lists
Kubernetes through 1.36, while this lab already uses Kubernetes 1.37.0. This
lab must therefore prove compatibility through CRD installation, controller
readiness, reconciliation, drift, and recovery. Do not treat this lab result as
a production support statement.

## 6. Files created or changed

```text
cluster/
└── bootstrap/
    └── argocd/
        ├── kustomization.yaml
        └── namespace.yaml
gitops/
├── bootstrap/
│   ├── kustomization.yaml
│   └── root-application.yaml
└── control-plane/
    ├── kustomization.yaml
    ├── project.yaml
    ├── envoy-gateway-crds.yaml
    ├── envoy-gateway.yaml
    └── reliability.yaml
docs/
├── 06-gitops-with-argocd.md
└── 06-gitops-with-argocd-evidence.md
kubernetes/base/kustomization.yaml
scripts/verify-prerequisites.sh
versions.env
```

Ownership rules:

- `cluster/bootstrap/argocd/` owns the minimum pinned installation required to
  start Argo CD. It is applied explicitly because no controller exists yet.
- `gitops/bootstrap/` owns the single root Application applied explicitly
  after Argo CD starts.
- `gitops/control-plane/` owns the AppProject and child Applications that Argo
  CD continuously reconciles.
- `kubernetes/` remains the desired application and networking state rendered
  by the reliability Application.
- `cluster/bootstrap/calico-values.yaml` remains outside Argo CD ownership.
- No generated Argo CD install bundle, admin password, token, kubeconfig, or
  repository credential is committed.

## 7. Concepts and vocabulary

### Desired state and live state

**Desired state** is the rendered configuration at the Application's Git or
OCI source revision. **Live state** is what the Kubernetes API currently
stores.

```text
desired == live  -> Synced
desired != live  -> OutOfSync
```

Sync status is not health status. A Deployment can match Git exactly and still
be `Degraded` because its Pods cannot become Ready. A healthy live Deployment
can be `OutOfSync` because someone changed its replica count manually.

### Reconciliation

A controller repeatedly observes desired and live state and acts to reduce the
difference. This is a loop, not a one-time command.

```text
observe -> compare -> act -> observe again
```

### Application

An Argo CD `Application` connects:

- a source repository or OCI artifact;
- an exact revision or tracked branch;
- a path or Helm chart;
- a destination cluster and namespace;
- a project and sync policy.

The Application is not the workload. It is the reconciliation contract for
the workload.

### AppProject

An `AppProject` is an authorization and grouping boundary. It restricts:

- permitted source repositories;
- permitted destination clusters and namespaces;
- permitted cluster-scoped resource kinds;
- optionally, roles and sync windows.

The built-in `default` project is intentionally permissive. This lab creates a
dedicated project instead of relying on it for child Applications.

### Root Application

The root Application watches a directory containing the AppProject and child
Application objects. This is commonly called an app-of-apps pattern:

```text
manually bootstrapped root Application
  -> AppProject
  -> Envoy Gateway CRD Application
  -> Envoy Gateway controller Application
  -> reliability Application
```

The root is not magic. It is an ordinary Application whose rendered resources
happen to include other Applications.

### Sync, automated sync, pruning, and self-healing

- **Sync** applies desired manifests to the live cluster.
- **Automated sync** starts a sync when a new tracked revision differs from
  live state.
- **Prune** removes an object that Argo CD previously managed when it disappears
  from desired state.
- **Self-heal** restores a managed object changed directly in the cluster.

Pruning and self-healing are powerful deletion and overwrite capabilities.
They are enabled only after sources, destinations, and ownership are explicit.

### Health

Argo CD evaluates health from Kubernetes status. Common states include:

- `Healthy`: resource reached its expected operating condition;
- `Progressing`: rollout or reconciliation is still underway;
- `Degraded`: Kubernetes reports failure or unavailable desired replicas;
- `Missing`: desired object does not exist live;
- `Unknown`: Argo CD cannot determine health.

### Helm under Argo CD

Argo CD uses Helm to render templates. Argo CD, not Helm, owns the ongoing
apply/prune lifecycle. A Helm chart source does not imply that `helm upgrade`
should continue managing the same release.

### Bootstrap boundary

GitOps cannot create the cluster network or the first GitOps controller from
inside a cluster where neither exists. Bootstrap must be small, explicit,
pinned, repeatable, and documented. It should not silently expand into a
second deployment system.

## 8. Step 1 — Start the implementation branch

**Mode: challenge-first**

Create an isolated implementation branch:

```bash
git switch main
git pull --ff-only origin main
git status --short
git switch -c phase-6-gitops
```

Gate:

```bash
git branch --show-current
git status --short
```

Expected: branch `phase-6-gitops`, with no changes yet.

## 9. Step 2 — Add and verify the Argo CD CLI prerequisite

**Mode: challenge-first**

Install the CLI through Homebrew if it is absent:

```bash
brew install argocd
```

Verify:

```bash
command -v argocd
argocd version --client --short
grep '^ARGOCD_' versions.env
```

Update `scripts/verify-prerequisites.sh` so it:

- requires the `argocd` executable;
- compares the detected client version with `ARGOCD_VERSION`;
- does not require a running Argo CD server merely to verify the client.

Predict why client validation and server validation are separate gates.

<details>
<summary>Explanation after your attempt</summary>

The CLI is a workstation dependency. The server is a set of Kubernetes
workloads that does not exist until later in this phase. Coupling prerequisite
verification to server reachability would make the bootstrap sequence circular.

</details>

## 10. Step 3 — Design the immutable Argo CD bootstrap

**Mode: challenge-first**

Create `cluster/bootstrap/argocd/namespace.yaml` and `kustomization.yaml`.

Contract:

- namespace is exactly `argocd`;
- installation source is the official `manifests/install.yaml`;
- the URL contains immutable commit
  `d6d5b248ce00e1a2c512068002a93d3319767087`;
- do not commit the generated upstream manifest;
- do not use `stable`, `master`, `main`, or `latest`;
- use the standard non-HA install because this is a single-laptop lab;
- do not place repository credentials or admin passwords in Kustomize.

Reference resource URL:

```text
https://raw.githubusercontent.com/argoproj/argo-cd/d6d5b248ce00e1a2c512068002a93d3319767087/manifests/install.yaml
```

Hints:

1. `namespace.yaml` is an ordinary `v1/Namespace`.
2. The Kustomization sets `namespace: argocd`.
3. Both the namespace file and immutable remote manifest belong under
   `resources`.

Render before applying:

```bash
mkdir -p /tmp/k8slab-phase6
kubectl kustomize cluster/bootstrap/argocd \
  > /tmp/k8slab-phase6/argocd-install.yaml

grep -nE '^kind: (CustomResourceDefinition|Deployment|StatefulSet|Service)$' \
  /tmp/k8slab-phase6/argocd-install.yaml | head -30

grep -nE 'stable|latest|master' \
  cluster/bootstrap/argocd/kustomization.yaml || true
```

Expected: Argo CD CRDs and workloads render; no mutable source reference.

## 11. Step 4 — Install the bootstrap layer

**Mode: challenge-first**

The install contains cluster-scoped CRDs and RBAC. Reconfirm the context:

```bash
bash scripts/require-lab-context.sh
kubectl config current-context
```

Create the namespace first, then use server-side apply. Some Argo CD CRDs are
too large for client-side apply's last-applied annotation:

```bash
kubectl apply -f cluster/bootstrap/argocd/namespace.yaml

kubectl kustomize cluster/bootstrap/argocd \
  | kubectl apply --server-side --force-conflicts -f -
```

`--force-conflicts` is restricted to the pinned Argo CD bootstrap bundle. Do
not copy it into ordinary application syncs without understanding field
ownership.

Wait for the non-HA control plane:

```bash
kubectl wait --for=condition=Established \
  crd/applications.argoproj.io \
  crd/appprojects.argoproj.io \
  --timeout=3m

kubectl rollout status deployment/argocd-server \
  -n argocd --timeout=5m
kubectl rollout status deployment/argocd-repo-server \
  -n argocd --timeout=5m
kubectl rollout status statefulset/argocd-application-controller \
  -n argocd --timeout=5m

kubectl get deployments,statefulsets,pods,services -n argocd -o wide
```

Inspect actual images and confirm they use the selected release:

```bash
kubectl get pods -n argocd \
  -o jsonpath='{range .items[*].spec.containers[*]}{.image}{"\n"}{end}' \
  | sort -u
```

## 12. Step 5 — Inspect Argo CD before creating Applications

**Mode: challenge-first**

Before using the UI, inspect the Kubernetes-native API:

```bash
kubectl api-resources --api-group=argoproj.io
kubectl get applications,appprojects -n argocd
kubectl get configmaps,secrets -n argocd
```

Predict why the cluster can contain Argo CD Pods while containing no useful
Application objects yet.

Optional local UI access uses port 8443 because the application already owns
host port 8080:

```bash
kubectl port-forward service/argocd-server \
  -n argocd 8443:443
```

Open `https://127.0.0.1:8443`. The local certificate is not publicly trusted.
Retrieve the initial password only when needed and never paste it into evidence
or Git:

```bash
ARGOCD_ADMIN_PASSWORD="$(kubectl get secret argocd-initial-admin-secret \
  -n argocd -o jsonpath='{.data.password}' | base64 --decode)"

argocd login 127.0.0.1:8443 \
  --username admin \
  --password "$ARGOCD_ADMIN_PASSWORD" \
  --insecure

unset ARGOCD_ADMIN_PASSWORD
```

The CLI can also inspect Applications through Kubernetes without an API-server
login by using `--core`.

## 13. Step 6 — Design the AppProject boundary

**Mode: challenge-first**

Create `gitops/control-plane/project.yaml`.

Contract:

- kind: `AppProject`, API `argoproj.io/v1alpha1`;
- name: `k8slab`, namespace: `argocd`;
- only the public k8slab Git repository and the two pinned Envoy OCI chart
  repositories are allowed sources;
- only the in-cluster API is allowed as destination;
- destination namespaces are `reliability` and `envoy-gateway-system`;
- cluster-scoped permission is limited to the kinds required by the rendered
  applications: Namespace, CustomResourceDefinition, ClusterRole,
  ClusterRoleBinding, GatewayClass, MutatingWebhookConfiguration,
  ValidatingAdmissionPolicy, and ValidatingAdmissionPolicyBinding;
- do not use `'*'` for sources, destinations, or cluster resources.

Required source identities:

```text
https://github.com/MyoMyatMin/k8slab.git
oci://docker.io/envoyproxy/gateway-crds-helm
oci://docker.io/envoyproxy/gateway-helm
```

Required destination server:

```text
https://kubernetes.default.svc
```

Explain which child Application would be rejected if GatewayClass were absent
from the cluster-resource whitelist.

The admission-registration kinds above are not guesses. Confirm them from the
pinned charts before writing the whitelist:

```bash
helm template eg-crds \
  oci://docker.io/envoyproxy/gateway-crds-helm \
  --version v1.9.2 \
  --namespace envoy-gateway-system \
  --set crds.gatewayAPI.enabled=true \
  --set crds.gatewayAPI.channel=standard \
  --set crds.envoyGateway.enabled=true \
  | yq eval 'select(.metadata.namespace == null) | .kind' - \
  | sort -u

helm template eg \
  oci://docker.io/envoyproxy/gateway-helm \
  --version v1.9.2 \
  --namespace envoy-gateway-system \
  --set crds.enabled=false \
  | yq eval 'select(.metadata.namespace == null) | .kind' - \
  | sort -u
```

This is a reusable policy-design method: render the exact pinned package,
inventory its cluster-scoped kinds, then allow only those kinds.

## 14. Step 7 — Define the reliability Application

**Mode: challenge-first**

Create `gitops/control-plane/reliability.yaml`.

Contract:

- name: `reliability`, namespace: `argocd`;
- project: `k8slab`;
- public repository URL is exact;
- tracked revision: `main`;
- path: `kubernetes/overlays/local`;
- destination: in-cluster API and namespace `reliability`;
- automated sync is explicitly enabled;
- pruning and self-healing are enabled;
- empty desired state is not allowed;
- namespace creation is enabled;
- pruning happens last;
- add the Argo CD resources finalizer and explain its deletion impact.

The Application should not contain rendered Deployments, image overrides, or
copied Kustomize YAML. It points Argo CD at the existing desired-state path.

Predict:

1. What status should appear if live resources already match the overlay?
2. What would happen if this Application were deleted with its finalizer?

## 15. Step 8 — Define Envoy Gateway as OCI Helm Applications

**Mode: challenge-first**

Create two Applications:

1. `envoy-gateway-crds` for
   `oci://docker.io/envoyproxy/gateway-crds-helm:v1.9.2`;
2. `envoy-gateway` for
   `oci://docker.io/envoyproxy/gateway-helm:v1.9.2`.

Both belong to project `k8slab`, destination namespace
`envoy-gateway-system`, and use exact revision `v1.9.2` with OCI path `.`.

CRD Application values contract:

- Gateway API CRDs enabled;
- standard channel;
- Envoy Gateway extension CRDs enabled;
- `ServerSideApply=true`.

Controller Application values contract:

- chart-managed CRDs disabled because the CRD Application owns them;
- release name `eg`;
- one controller replica;
- resource requests and limits match
  `cluster/bootstrap/envoy-gateway-values.yaml`;
- automated prune and self-heal enabled;
- namespace creation enabled.

Use sync-wave annotations on the child Application objects:

```text
AppProject              wave -2
Envoy CRD Application   wave -1
Envoy controller        wave  0
reliability workload    wave  1
```

Waves order object creation by the root Application. They do not remove the
need to inspect each child Application's own sync and health.

## 16. Step 9 — Define the root Application

**Mode: challenge-first**

Create:

- `gitops/control-plane/kustomization.yaml`, which includes the AppProject and
  three child Applications;
- `gitops/bootstrap/root-application.yaml`;
- `gitops/bootstrap/kustomization.yaml`.

Root Application contract:

- name: `k8slab-root`, namespace: `argocd`;
- project: `default`, because the root creates the dedicated project;
- source repository: this public Git repository;
- tracked revision: `main`;
- source path: `gitops/control-plane`;
- destination: in-cluster API, namespace `argocd`;
- automated prune and self-heal enabled;
- empty desired state prohibited;
- resource finalizer present.

The bootstrap Kustomization contains only the root Application. Applying it is
the final routine manual creation step.

Draw the ownership graph before continuing:

```text
kubectl bootstrap
  -> Argo CD installation
  -> root Application
       -> AppProject
       -> child Applications
            -> platform and reliability resources
```

## 17. Step 10 — Render and validate the complete GitOps graph

**Mode: challenge-first verification**

```bash
mkdir -p /tmp/k8slab-phase6

kubectl kustomize gitops/control-plane \
  > /tmp/k8slab-phase6/control-plane.yaml

kubectl kustomize gitops/bootstrap \
  > /tmp/k8slab-phase6/bootstrap.yaml

grep -nE '^kind: (AppProject|Application)$' \
  /tmp/k8slab-phase6/control-plane.yaml \
  /tmp/k8slab-phase6/bootstrap.yaml

grep -nE 'targetRevision: (HEAD|stable|latest|master)' \
  gitops cluster/bootstrap/argocd || true

grep -R -nE 'password|token|privateKey|sshPrivateKey' \
  gitops cluster/bootstrap/argocd || true

git diff --check
```

Expected:

- one AppProject;
- three child Applications;
- one root Application;
- no mutable source revision;
- no credential material.

After Argo CD CRDs exist, validate against the server without persisting:

```bash
bash scripts/require-lab-context.sh
kubectl apply --dry-run=server -k gitops/control-plane
kubectl apply --dry-run=server -k gitops/bootstrap
```

## 18. Step 11 — Merge the declarative control plane before bootstrapping it

**Mode: challenge-first**

Argo CD will track `main`. The GitOps files must therefore exist on `main`
before the root Application references them.

```bash
git status --short
git diff --check
git add cluster/bootstrap/argocd gitops \
  scripts/verify-prerequisites.sh
git commit -m "feat: add phase 6 GitOps control plane"
git push --set-upstream origin phase-6-gitops
```

Open a pull request, wait for CI, review the rendered changes, and merge. Then:

```bash
git switch main
git pull --ff-only origin main
git status --short
```

Do not point the root Application at an unmerged personal branch as the final
configuration.

## 19. Step 12 — Bootstrap the root and wait for reconciliation

**Mode: challenge-first**

```bash
bash scripts/require-lab-context.sh
kubectl apply -k gitops/bootstrap

kubectl get applications,appprojects -n argocd
argocd app list --core

argocd app wait k8slab-root --core \
  --sync --health --timeout 300
argocd app wait envoy-gateway-crds --core \
  --sync --timeout 600
argocd app wait envoy-gateway --core \
  --sync --health --timeout 600
argocd app wait reliability --core \
  --sync --health --timeout 600
```

Gate:

```text
k8slab-root          Synced  Healthy
envoy-gateway-crds   Synced  inspect resource health
envoy-gateway        Synced  Healthy
reliability          Synced  Healthy
```

If a CRD-only Application reports a health state other than `Healthy` while
sync is successful, inspect its resource tree before assuming failure; some
cluster-scoped resources do not expose workload-style health.

## 20. Step 13 — Transfer Envoy lifecycle ownership

**Mode: challenge-first**

Phase 5 installed the Envoy controller with the Helm CLI. Phase 6 now renders
the same pinned chart through Argo CD. Helm does not continuously reconcile,
but its release metadata should not remain as an invitation to use two
lifecycle paths.

First prove Argo CD owns and has synchronized the generated resources:

```bash
argocd app get envoy-gateway --core
kubectl get deployment envoy-gateway \
  -n envoy-gateway-system -o yaml \
  | grep -n 'argocd.argoproj.io/tracking-id'

helm list -n envoy-gateway-system
kubectl get secrets -n envoy-gateway-system \
  -l owner=helm,name=eg
```

Abort if the Argo CD Application is not Synced and Healthy. Never run
`helm uninstall eg` after adoption: uninstall would delete resources that Argo
CD is now expected to own.

After the gate passes, remove only the stale Helm release metadata Secret:

```bash
kubectl get secrets -n envoy-gateway-system \
  -l owner=helm,name=eg -o name

kubectl delete secrets -n envoy-gateway-system \
  -l owner=helm,name=eg
```

This intentionally removes Helm rollback history, not the Deployment or
Service. Git plus Argo CD now owns future lifecycle.

Verify no traffic interruption:

```bash
kubectl rollout status deployment/envoy-gateway \
  -n envoy-gateway-system --timeout=3m
curl --fail-with-body http://reliability.localhost:8080/health/ready
argocd app get envoy-gateway --core
```

## 21. Step 14 — Deliver a real change through Git

**Mode: challenge-first**

Change the API configuration marker in `kubernetes/base/kustomization.yaml`:

```text
APP_VERSION=phase-4
```

becomes:

```text
APP_VERSION=phase-6-gitops
```

Do not run `kubectl apply` afterward.

Use a small branch and pull request:

```bash
git switch -c phase-6-release-marker
git diff --check
git add kubernetes/base/kustomization.yaml
git commit -m "chore: mark phase 6 GitOps release"
git push --set-upstream origin phase-6-release-marker
```

Merge after CI, switch back to updated `main`, then force only a refresh, not a
sync:

```bash
argocd app get reliability --core --refresh
argocd app wait reliability --core \
  --sync --health --timeout 300

curl --fail-with-body \
  http://reliability.localhost:8080/health/live
```

Expected: the version becomes `phase-6-gitops`, API Pods roll safely, and no CI
job called the Kubernetes API.

Record the Git revision from Application status:

```bash
kubectl get application reliability -n argocd \
  -o jsonpath='{.status.sync.revision}{"\n"}'
```

## 22. Step 15 — Controlled failure: create live drift

**Mode: challenge-first failure exercise**

### Hypothesis

Changing a managed Deployment directly alters live state but not Git. Argo CD
should detect `OutOfSync`, record a self-heal operation, and restore the
Git-declared replica count.

### Safety and abort conditions

- Scope: only `deployment/frontend` in namespace `reliability`.
- Desired replicas in Git: 2.
- Temporary live value: 1.
- Do not change image, Service, policies, Gateway, Redis, or Argo CD resources.
- Abort and inspect if frontend reaches zero available replicas or the Gateway
  health path fails.
- Recovery source is `main`; do not edit Git to preserve the drift.

### Observe in one terminal

```bash
kubectl get application reliability -n argocd -w
```

In a second terminal:

```bash
bash scripts/require-lab-context.sh
kubectl patch deployment frontend -n reliability \
  --type=merge -p '{"spec":{"replicas":1}}'

kubectl annotate application reliability -n argocd \
  argocd.argoproj.io/refresh=hard --overwrite

argocd app get reliability --core --refresh
kubectl get deployment frontend -n reliability -w
```

The normal self-heal delay is short, so `OutOfSync` may be transient. Evidence
may come from the watch, Application operation state, controller events, and
history:

```bash
argocd app history reliability --core
kubectl get application reliability -n argocd -o yaml
```

### Recover and verify

Self-heal is the recovery action. Do not manually scale back to two.

```bash
kubectl wait deployment/frontend -n reliability \
  --for=condition=Available --timeout=3m

kubectl get deployment frontend -n reliability \
  -o jsonpath='desired={.spec.replicas} available={.status.availableReplicas}{"\n"}'

argocd app wait reliability --core \
  --sync --health --timeout 300

curl --fail-with-body http://reliability.localhost:8080/
```

Expected: desired and available replicas return to 2 without a Git change or
manual corrective apply.

<details>
<summary>Diagnosis and explanation</summary>

The patch changed only live state. Argo CD compared it with the Kustomize
output from `main`, marked the Application OutOfSync, and used self-heal to
restore the declared replica count. Kubernetes then reconciled the restored
Deployment spec into two available Pods.

</details>

## 23. Step 16 — Prove pruning safely

**Mode: challenge-first**

Pruning should be proven with a harmless object created through Git, never with
an application Deployment.

On a short branch:

1. create `kubernetes/overlays/local/gitops-prune-marker.yaml` as a ConfigMap
   named `gitops-prune-marker` in namespace `reliability`;
2. add it to the local Kustomization;
3. commit, push, review, and merge;
4. wait for `reliability` to become Synced and confirm the ConfigMap exists.

Then use a second short branch to remove the file and its Kustomization entry.
Merge after review and observe:

```bash
argocd app get reliability --core --refresh
argocd app wait reliability --core \
  --sync --health --timeout 300

kubectl get configmap gitops-prune-marker \
  -n reliability
```

Expected final result: `NotFound`. Argo CD deleted the previously managed
object because it disappeared from desired state and pruning is enabled.

Record both Git commit IDs and the prune operation. Do not leave the marker in
the final tree.

## 24. Step 17 — Practice durable rollback through Git

**Mode: challenge-first**

Argo CD can expose deployment history, but an imperative rollback does not
change the branch that automated sync tracks. With automated sync enabled, Git
must express the durable recovery.

Create and merge a harmless temporary change to `APP_VERSION`, for example
`phase-6-rollback-demo`. Record its merge commit and observe Argo CD deploy it.

Then revert that Git commit through the normal review path:

```bash
git switch main
git pull --ff-only origin main
git switch -c phase-6-revert-demo
git revert <MERGE_OR_CHANGE_COMMIT>
git push --set-upstream origin phase-6-revert-demo
```

After the revert PR merges:

```bash
argocd app get reliability --core --refresh
argocd app wait reliability --core \
  --sync --health --timeout 300

curl --fail-with-body \
  http://reliability.localhost:8080/health/live

argocd app history reliability --core
```

Expected: the API returns `phase-6-gitops`, and both forward and revert
revisions appear in history.

Explain why `git revert` is safer than rewriting published history and why an
imperative Argo rollback would fight automated reconciliation unless desired
state also changed.

## 25. Step 18 — Final validation

```bash
bash scripts/require-lab-context.sh

kubectl get nodes -L reliability.dev/workload
kubectl get tigerastatus
kubectl get deployments,statefulsets,pods -n argocd
kubectl get applications,appprojects -n argocd
argocd app list --core

argocd app wait k8slab-root --core \
  --sync --health --timeout 300
argocd app wait envoy-gateway --core \
  --sync --health --timeout 300
argocd app wait reliability --core \
  --sync --health --timeout 300

kubectl get gatewayclass
kubectl get gateways,httproutes -n reliability
kubectl get networkpolicies -n reliability
kubectl get deployments,pods,services,endpointslices -A

curl --fail-with-body http://reliability.localhost:8080/ >/dev/null
curl --fail-with-body http://reliability.localhost:8080/health/live
curl --fail-with-body http://reliability.localhost:8080/health/ready
curl --fail-with-body http://reliability.localhost:8080/api/v1/visits

kubectl kustomize cluster/bootstrap/argocd >/dev/null
kubectl kustomize gitops/control-plane >/dev/null
kubectl kustomize gitops/bootstrap >/dev/null
kubectl kustomize kubernetes/overlays/local >/dev/null

trivy --config .trivy.yaml config --exit-code 1 .
git diff --check
git status --short
```

Final gates:

- every Application is Synced;
- workload Applications are Healthy;
- root and child Applications report revisions reachable from `main`;
- Argo CD, Envoy, application, and Calico workloads are ready;
- Gateway traffic and NetworkPolicy behavior from Phase 5 remain correct;
- the prune marker is absent from Git and the cluster;
- `APP_VERSION` is `phase-6-gitops`;
- no manual Helm release named `eg` remains;
- no credential, generated install bundle, admin password, or token is tracked;
- repository validation passes.

Repeat the Phase 5 denied frontend-Pod-to-API test. GitOps success must not
weaken network isolation.

## 26. Evidence record

Create `docs/06-gitops-with-argocd-evidence.md` containing:

- date, branch, base commit, merge commits, and pinned versions;
- bootstrap boundary and why Calico stays outside Argo CD;
- Argo CD component readiness and actual images;
- AppProject source, destination, and resource restrictions;
- root and child Application sync/health/revision summaries;
- proof that Envoy ownership moved from Helm CLI metadata to Argo CD;
- Git-delivered `APP_VERSION` change and rollout result;
- live-drift timeline, transient `OutOfSync` evidence, and self-heal result;
- prune-marker creation and deletion commits plus final `NotFound` result;
- Git revert timeline and final application version;
- final Gateway and NetworkPolicy verification;
- answers to every review question;
- production limitations.

Do not include:

- admin password or token;
- repository credentials;
- kubeconfig content;
- full generated Argo CD CRDs or installation bundle;
- raw logs unrelated to a specific finding.

## 27. Troubleshooting

| Symptom | Evidence to collect | Likely causes | Next falsifiable test |
|---|---|---|---|
| Argo Pods Pending | Pod events, node capacity | insufficient resources, selectors, pull failure | Describe the first Pending Pod |
| CRD apply too large | apply error and method | client-side annotation limit | Use pinned server-side bootstrap command |
| Repository unavailable | repo-server logs, Application conditions | URL, network, private repository credentials | Fetch exact public URL from repo-server context |
| Application forbidden by project | Application conditions, AppProject YAML | source, destination, or kind not allowed | Compare exact identity with project rules |
| Root Synced but child failed | child Application status | child source/render/apply/health failure | Inspect the child, not only root status |
| `ComparisonError` | Application condition, repo-server logs | render error, unavailable OCI artifact, invalid Kustomize | Render the same source locally |
| `OutOfSync` after sync | resource diff | defaulted fields, mutating controller, competing owner | Inspect Argo resource diff and field manager |
| Synced but Degraded | Kubernetes resource health/events | rollout or dependency failure | Describe the first unhealthy child resource |
| New Git commit not detected | revision, refresh, repo-server | poll delay, wrong branch/path, cache | Hard refresh and compare reported revision |
| Drift does not self-heal | sync policy, history | selfHeal disabled, ignored field, unmanaged resource | Inspect Application sync policy and tracking ID |
| Resource not pruned | sync policy, tracking annotation | prune disabled or object not owned | Inspect resource tracking and sync result |
| Envoy resources flap | Helm metadata, tracking ID, controller logs | competing lifecycle commands or bad chart values | Confirm Argo ownership and stop Helm CLI changes |
| Gateway returns 503 after sync | route, Service, EndpointSlice, policy | backend or policy failure, not necessarily GitOps | Follow Phase 5 diagnostic order |
| Rollback immediately reverses | desired Git revision | live rollback conflicts with automated Git state | Revert the desired commit in Git |

Use this diagnostic order:

```text
Application source URL/revision/path
  -> repository fetch
  -> render result
  -> AppProject authorization
  -> apply/sync operation
  -> Kubernetes resource health
  -> application runtime path
```

## 28. Production considerations

- Use a supported Kubernetes/Argo CD version combination verified by the target
  platform, not merely a working lab combination.
- Run Argo CD in HA mode across real failure domains.
- Integrate SSO and least-privilege RBAC; disable routine local-admin use.
- Use signed commits/artifacts and protected branches with mandatory reviews.
- Configure repository webhooks for faster refresh while retaining polling as
  a fallback.
- Back up and test recovery of Argo CD configuration and repository access.
- Use dedicated projects with narrow source, destination, and resource rules.
- Separate platform and application ownership when teams require different
  privileges.
- Treat Application deletion finalizers and automated pruning as destructive
  controls requiring review.
- Use sync windows and manual promotion for environments where immediate
  automated deployment is inappropriate.
- Keep CNI and foundational bootstrap recovery independent of the controller
  that depends on them.
- Plan secret delivery with SOPS and age in a later security phase; never store
  plaintext credentials in Application manifests.
- Consider a separate GitOps repository when organizational boundaries or
  access controls require it. This lab intentionally keeps one repository.

## 29. Cleanup, rollback, and reset

Routine phase completion does not require cleanup. Leave Argo CD reconciling
the cluster for later phases.

### Pause application automation without deleting workloads

Change the Application manifest in Git so automated sync is explicitly
disabled, merge it, and let the root Application reconcile the change. A live
patch is temporary and will itself be repaired by the root.

### Remove Argo CD while retaining managed resources

This is an advanced ownership transfer. Do not merely delete the `argocd`
namespace: child Application finalizers can cascade deletion to workloads.

For each child Application, intentionally remove its resources finalizer,
delete the Application object, then delete the root Application without its
finalizer. Confirm workloads remain before removing the bootstrap installation.
Perform this only when the user explicitly chooses to abandon GitOps.

### Full disposable reset

The safest lab reset is the whole named cluster:

```bash
kubectl config current-context
bash scripts/require-lab-context.sh
kind get clusters
kind delete cluster --name k8slab
```

This deletes the live cluster, including Redis data and Argo CD history. Git,
container images, and reviewed evidence remain.

Recovery order:

```text
kind
  -> Calico bootstrap
  -> Argo CD bootstrap
  -> root Application
  -> child platform/workload reconciliation
  -> verification
```

## 30. Definition of done

- [ ] Implementation began from clean `main` on `phase-6-gitops`.
- [ ] Argo CD CLI and server use the pinned `v3.5.4` release.
- [ ] Bootstrap uses the immutable upstream commit, not `stable` or `latest`.
- [ ] Calico and Argo CD bootstrap ownership are documented explicitly.
- [ ] Root Application, dedicated AppProject, and three child Applications are
      stored in Git.
- [ ] AppProject restricts exact sources, destinations, and cluster resource
      kinds.
- [ ] Envoy Gateway CRDs/controller and reliability workload are Argo-managed.
- [ ] Stale Helm CLI release metadata is removed only after Argo ownership is
      proven.
- [ ] Root and child Applications reach required sync and health gates.
- [ ] A merged Git change rolls out without `kubectl apply`.
- [ ] Direct live drift is observed and automatically self-healed.
- [ ] A harmless Git-managed object is pruned after removal from desired state.
- [ ] Durable rollback is performed with a Git revert.
- [ ] Gateway routing and default-deny policy still work.
- [ ] Trivy, render checks, CI, and `git diff --check` pass.
- [ ] No mutable source reference, plaintext secret, generated CRD bundle,
      admin password, token, or kubeconfig is committed.
- [ ] Evidence and all review answers are recorded.

## 31. Review questions

1. What is the difference between desired state, live state, sync status, and
   health status?
2. Why can an Application be Synced but Degraded?
3. Why can an Application be OutOfSync while the application still serves
   traffic?
4. What is the Argo CD bootstrap chicken-and-egg problem?
5. Why does Calico remain outside Argo CD ownership in this design?
6. What does the root Application own, and why does it use the default project?
7. What security boundaries does the `k8slab` AppProject enforce?
8. Why are Envoy Gateway CRDs and the controller separate Applications?
9. What does Argo CD do with a Helm chart, and why should Helm CLI stop owning
   the same lifecycle afterward?
10. Distinguish automated sync, pruning, and self-healing.
11. Why is `allowEmpty: false` useful with automated pruning?
12. What does the resources finalizer change when an Application is deleted?
13. Why must the GitOps files be merged to `main` before a main-tracking root
    Application can render them?
14. Which evidence proves a Git commit, rather than a manual apply, caused a
    rollout?
15. How do tracking annotations and Application history help diagnose drift?
16. Why can `ResolvedRefs=True` at the Gateway layer coexist with a Degraded
    Argo CD Application?
17. Why is Git revert the durable rollback mechanism with automated sync?
18. How do you distinguish repository fetch, render, authorization, sync, and
    workload-health failures?
19. What could make Argo CD report persistent OutOfSync immediately after a
    successful sync?
20. What changes for production availability, authentication, repository
    security, promotion, and bootstrap recovery?

## 32. Official references

- Argo CD installation:
  <https://argo-cd.readthedocs.io/en/stable/operator-manual/installation/>
- Argo CD declarative setup:
  <https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/>
- Argo CD Application specification:
  <https://argo-cd.readthedocs.io/en/stable/user-guide/application-specification/>
- Argo CD automated sync:
  <https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/>
- Argo CD projects:
  <https://argo-cd.readthedocs.io/en/stable/user-guide/projects/>
- Argo CD OCI sources:
  <https://argo-cd.readthedocs.io/en/latest/user-guide/oci/>
- Argo CD Helm sources:
  <https://argo-cd.readthedocs.io/en/latest/user-guide/helm/>
- Argo CD cluster bootstrapping:
  <https://argo-cd.readthedocs.io/en/stable/operator-manual/cluster-bootstrapping/>
- Argo CD v3.5.4 release:
  <https://github.com/argoproj/argo-cd/releases/tag/v3.5.4>
- Kustomize:
  <https://kubectl.docs.kubernetes.io/references/kustomize/>

## 33. Next phase

Phase 7 installs the Prometheus Operator stack through the GitOps control plane.
It adds application scraping, PromQL, Grafana dashboards, and evidence for
request rate, errors, latency, saturation, and Kubernetes health. Phase 6 must
be stable first because the observability platform will rely on the same
Application, project, sync, and recovery model.
