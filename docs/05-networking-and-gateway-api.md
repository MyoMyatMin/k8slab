# Phase 5 — Networking and Traffic Management

> Status: Complete
>
> Last validated: 2026-10-10 on kind with Calico 3.33.0 and Envoy Gateway 1.9.2
>
> Version baseline selected: 2026-10-07 for Calico 3.33.0, Gateway API 1.6.1, Envoy Gateway 1.9.2, Kubernetes 1.37.0, kind 0.33.0, Helm 4.3.0, and Kustomize 5.8.1
>
> Exercise modes: Guided completion for the small frontend change; challenge-first for cluster networking, Gateway API, and NetworkPolicy

For a concept-first explanation of every networking boundary in this phase,
use [`05-networking-theory-review.md`](05-networking-theory-review.md).

## 1. Why this phase matters

Phase 4 proved that Pods, Services, readiness, and controllers work inside the
cluster. Host access still depended on temporary `kubectl port-forward`
processes, and every Pod could communicate with every other Pod by default.
That is useful for initial learning but incomplete as a platform boundary.

This phase builds the real request path:

```text
Browser or curl
    |
    | http://reliability.localhost:8080
    v
kind host-port mapping
    |
    v
Envoy NodePort Service
    |
    v
Envoy proxy managed by Envoy Gateway
    |
    v
Gateway listener + HTTPRoute matching
    |                         |
    | /, /app.js, ...         | /api/* and /health/*
    v                         v
frontend Service             API Service
                                  |
                                  v
                             Redis Service
```

The namespace also changes from default-allow networking to an explicit flow
model:

```text
Envoy proxy -> frontend:8080
Envoy proxy -> API:8000
API         -> Redis:6379
Pods        -> cluster DNS:53
everything else -> denied
```

The phase separates three questions:

1. **Can a name resolve?** — DNS.
2. **Does a Service select ready endpoints?** — Service and EndpointSlice.
3. **Is the connection authorized and routed?** — NetworkPolicy and Gateway
   API.

A request can fail at any boundary while every Pod still shows `Running`.

## 2. Learning objectives

By the end of this phase, you can:

- explain Pod IPs, Service virtual IPs, EndpointSlices, and cluster DNS;
- distinguish GatewayClass, Gateway, listener, and HTTPRoute ownership;
- interpret `Accepted`, `Programmed`, and `ResolvedRefs` conditions;
- route one hostname to frontend and API backends by path;
- explain same-origin browser requests and why they avoid a CORS dependency;
- expose the local Gateway through a deliberate NodePort and kind host mapping;
- explain why NetworkPolicy requires an enforcing CNI;
- design default-deny ingress and egress with only required flows restored;
- prove an unauthorized connection is blocked;
- distinguish DNS failure, policy denial, an empty EndpointSlice, and a
  rejected HTTPRoute;
- diagnose a broken Service selector from Gateway symptoms back to labels;
- recover the networking stack from versioned configuration.

## 3. Exercise mode

The frontend has two small supporting-code changes, so that section uses
**guided completion**. You fill decision-bearing TODOs and compare with a
collapsed answer only after trying.

Calico, kind networking, Gateway API, routing, and NetworkPolicy use
**challenge-first** mode. Each section gives an operational contract,
constraints, evidence, progressive hints, and a reference after an attempt.

Do not apply a complete manifest bundle without being able to draw its packet
path.

## 4. Prerequisites and safety boundary

- Phases 0–4 are complete on `main`.
- The worktree is clean before the implementation branch is created.
- The Phase 4 `k8slab` cluster is disposable.
- OrbStack and its Docker-compatible engine are running.
- The application images are public and pullable by digest.
- `bash scripts/verify-prerequisites.sh` passes.
- No real credential or private key is used.

The only authorized destructive target is:

```text
cluster:  k8slab
context:  kind-k8slab
```

Before deleting it:

```bash
kubectl config current-context
bash scripts/require-lab-context.sh
kind get clusters
```

The context guard protects Kubernetes API operations. The explicit
`--name k8slab` protects the kind deletion target. Stop if either is
unexpected.

## 5. Pinned Phase 5 baseline

`versions.env` is authoritative:

| Purpose | Pin |
|---|---|
| Kubernetes | `v1.37.0` |
| kind | `v0.33.0` |
| Helm | `v4.3.0` |
| Kustomize | `v5.8.1` |
| Calico Open Source | `v3.33.0` |
| Gateway API | `v1.6.1`, standard channel |
| Envoy Gateway | `v1.9.2` |
| Local hostname | `reliability.localhost` |
| Host HTTP port | `8080` |
| Envoy NodePort | `30080` |
| Application namespace | `reliability` |
| Envoy controller namespace | `envoy-gateway-system` |

Names beneath `.localhost` resolve to loopback without changing `/etc/hosts`.
Do not add a machine-wide hosts-file entry for this exercise.

Phase 5 uses Calico because kindnet does not enforce NetworkPolicy. Read
`decisions/0001-calico-for-kind-network-policy.md` before rebuilding the
cluster.

## 6. Files created or changed

```text
app/frontend/
├── app.js
└── nginx.conf
cluster/
├── bootstrap/
│   ├── calico-values.yaml
│   └── envoy-gateway-values.yaml
└── kind/
    └── kind.yaml
kubernetes/
├── policies/
│   ├── kustomization.yaml
│   ├── default-deny.yaml
│   ├── allow-dns.yaml
│   ├── allow-gateway-to-api.yaml
│   ├── allow-gateway-to-frontend.yaml
│   ├── allow-api-to-redis.yaml
│   └── allow-redis-from-api.yaml
└── overlays/local/
    ├── envoy-proxy.yaml
    ├── gateway-class.yaml
    ├── gateway.yaml
    ├── http-route.yaml
    └── kustomization.yaml
docs/
├── 05-networking-and-gateway-api.md
├── 05-networking-theory-review.md
└── 05-networking-and-gateway-api-evidence.md
versions.env
```

Ownership rules:

- `cluster/kind/` owns host-to-node wiring and CNI assumptions.
- `cluster/bootstrap/` owns software required before ordinary workloads or
  GitOps can communicate.
- `kubernetes/policies/` owns portable application NetworkPolicies.
- the local overlay owns the local hostname, NodePort exposure, Gateway
  objects, and published application image digests.
- Phase 6 will replace transitional manual Helm lifecycle with GitOps.

## 7. Concepts and vocabulary

### DNS, Service, and EndpointSlice

A Service name such as `redis.reliability.svc.cluster.local` resolves to a
stable ClusterIP. The Service selector finds Pods, while EndpointSlice records
selected backend addresses and readiness. DNS can succeed while the Service
has no endpoints.

### Gateway API roles

- **GatewayClass** names the controller responsible for a family of Gateways.
- **Gateway** requests an entry point and defines listeners.
- **listener** defines protocol, port, hostname, and allowed Routes.
- **HTTPRoute** matches HTTP traffic and forwards it to backend Services.
- **EnvoyProxy** is an Envoy Gateway extension used here to customize the local
  proxy Service as a fixed NodePort.

### Route status is evidence

Object creation is not proof of routing:

- Gateway `Accepted=True` means its configuration is accepted.
- Gateway `Programmed=True` means data-plane configuration was produced.
- HTTPRoute `Accepted=True` means the listener accepted the attachment.
- HTTPRoute `ResolvedRefs=True` means referenced backends and ports resolve.

### NetworkPolicy is additive

Policies are not ordered firewall commands. Once a Pod is isolated for ingress
or egress, its allowed traffic is the union of matching allow rules. A
default-deny policy has no allow rules; later policies restore required flows.

NetworkPolicy is primarily layer 3/4. It can authorize identities expressed as
namespaces, Pod labels, protocols, and ports. It cannot authorize HTTP paths;
HTTPRoute owns that layer.

### Ingress and egress viewpoints

`frontend -> API` is egress from frontend and ingress to API. A connection must
be allowed in both directions when both Pods are isolated for those policy
types. Return traffic for an allowed connection is automatically permitted.

## 8. Step 1 — Create the application release branch

**Mode: challenge-first**

The guide lives on `main`. First isolate the frontend compatibility change so
CI can publish immutable images before the Kubernetes networking work begins:

```bash
git status --short
git switch -c phase-5-frontend-same-origin
git branch --show-current
```

Do not continue with unrelated changes in the worktree.

## 9. Step 2 — Verify and predict

```bash
bash scripts/verify-prerequisites.sh
bash scripts/require-lab-context.sh
kubectl get nodes -L reliability.dev/workload
kubectl get deployments,pods,services,endpointslices -n reliability
```

Record predictions:

1. Will merely creating a `NetworkPolicy` make kindnet enforce it?
2. If Service DNS resolves but its selector matches no Pod, what does its
   EndpointSlice contain?
3. If `/api` and `/` both match, which route rule wins?
4. Why can a Gateway be healthy while one backend path returns 503?
5. Which flows must survive default deny for the application to remain Ready?

Keep these answers for the evidence file.

## 10. Step 3 — Make browser calls same-origin

**Mode: guided completion**

Phase 4's frontend calls a separate host API port. Replace it with the current
browser origin.

In `app/frontend/app.js`:

```javascript
// TODO(1): prefix API paths with the current browser origin.
const API = "TODO";
```

TODO(1): `${API}/health/live` must use the same scheme, hostname, and port that
served the page, with no environment hostname compiled into JavaScript.

In `app/frontend/nginx.conf`, change only the CSP connection source:

```nginx
# TODO(2): permit fetch to the page's own origin only.
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'; connect-src TODO; object-src 'none'; base-uri 'none'; frame-ancestors 'none'" always;
```

Verify:

```bash
grep -nE 'const API|connect-src' app/frontend/app.js app/frontend/nginx.conf
grep -R -n '127.0.0.1:8000\|localhost:8000' app/frontend || true
```

The second command should have no output.

<details>
<summary>Reference answer after your attempt</summary>

```javascript
const API = "";
```

```nginx
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'" always;
```

</details>
## 11. Step 4 — Publish and record the application release

**Mode: challenge-first supply-chain checkpoint**

The frontend changed, so the old immutable digest cannot contain the new
behavior. Run checks, commit the application change separately, push it, and
require CI to pass. Keep this pull request limited to the two frontend files.

```bash
cd app/api
source .venv/bin/activate
pytest -q
deactivate
cd ../..

docker build --tag k8slab-frontend:phase5 app/frontend
docker run --rm k8slab-frontend:phase5 nginx -t
git diff --check
```

Commit those two files, open the small application pull request, merge it after
CI passes, and wait for the `Publish Images` workflow on `main`. Then begin the
platform implementation from the published source revision:

```bash
git switch main
git pull --ff-only origin main
git switch -c phase-5-networking-gateway
```

After the change reaches `main`, the publish workflow builds both images
because build metadata includes the source revision. Record both new top-level
multi-platform digests and verify them:

```bash
docker buildx imagetools inspect \
  ghcr.io/myomyatmin/k8slab-api@sha256:REPLACE

docker buildx imagetools inspect \
  ghcr.io/myomyatmin/k8slab-frontend@sha256:REPLACE
```

Update only the `images` entries in the local Kustomization. Never substitute
`main`, `latest`, or a local image ID.

## 12. Step 5 — Design the policy-capable kind cluster

**Mode: challenge-first**

Update `cluster/kind/kind.yaml` with this contract:

- preserve one control-plane and two labeled workers;
- disable kind's default CNI;
- set Pod subnet `10.244.0.0/16`, which must not overlap the host or
  container-node network;
- map host TCP 8080 to control-plane container TCP 30080;
- expose neither the Kubernetes API nor application Pods directly.

The mapping targets NodePort rather than a Pod because Pod identity and
placement change. NodePort remains stable and kube-proxy forwards to current
Envoy endpoints.

Hints:

1. `networking` is a top-level sibling of `nodes`.
2. `extraPortMappings` belongs on the control-plane entry.
3. The mapping needs `containerPort`, `hostPort`, and `protocol`.

Validate without deletion:

```bash
yq eval '.' cluster/kind/kind.yaml >/dev/null
git diff --check
```

<details>
<summary>Reference shape after your attempt</summary>

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: k8slab
networking:
  disableDefaultCNI: true
  podSubnet: 10.244.0.0/16
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: 30080
        hostPort: 8080
        protocol: TCP
  - role: worker
    labels:
      reliability.dev/workload: "true"
  - role: worker
    labels:
      reliability.dev/workload: "true"
```

</details>

## 13. Step 6 — Recreate the cluster and install Calico

**Mode: challenge-first**

This deletes only `k8slab`. Redis data and live API objects disappear; Git and
registry images remain.

```bash
kubectl config current-context
bash scripts/require-lab-context.sh
kind get clusters
kind delete cluster --name k8slab

kind create cluster \
  --name k8slab \
  --config cluster/kind/kind.yaml \
  --image "$(grep '^KIND_NODE_IMAGE=' versions.env | cut -d= -f2-)"
```

Nodes will remain `NotReady`: you deliberately created them without a CNI.
Do not make `kind create cluster` wait for Ready nodes, because that condition
cannot become true until the next Calico installation step.

Create `cluster/bootstrap/calico-values.yaml` with the same non-overlapping Pod
CIDR as kind. Disable the optional API server and UI components because this
phase needs Calico networking and portable Kubernetes policy, not Calico UI or
layer-7 features:

```yaml
installation:
  kubernetesProvider: Kind
  calicoNetwork:
    ipPools:
      - name: default-ipv4-ippool
        cidr: 10.244.0.0/16
        blockSize: 26
        encapsulation: IPIP
        natOutgoing: Enabled
        nodeSelector: all()

apiServer:
  enabled: false

goldmane:
  enabled: false

whisker:
  enabled: false
```

Before cluster creation, compare this CIDR with the Docker or OrbStack network.
Overlapping ranges can let Pod-to-Pod traffic work while preventing Pods such
as CoreDNS from reaching the Kubernetes API on a node address.

```bash
helm repo add projectcalico https://docs.tigera.io/calico/charts
helm repo update projectcalico
kubectl create namespace tigera-operator \
  --dry-run=client -o yaml | kubectl apply -f -

helm template calico-crds projectcalico/projectcalico.org.v3 \
  --version v3.33.0 \
  --api-versions admissionregistration.k8s.io/v1/MutatingAdmissionPolicy \
  | kubectl apply --server-side -f -

helm upgrade --install calico projectcalico/tigera-operator \
  --version v3.33.0 \
  --namespace tigera-operator \
  --values cluster/bootstrap/calico-values.yaml \
  --wait \
  --timeout 10m
```

Verify:

```bash
kubectl get tigerastatus
kubectl get pods -n calico-system -o wide
kubectl wait --for=condition=Ready nodes --all --timeout=5m
kubectl get nodes -L reliability.dev/workload
```

Restore the Phase 4 application only after Calico is healthy:

```bash
bash scripts/require-lab-context.sh
kubectl apply -k kubernetes/overlays/local
kubectl rollout status deployment/api -n reliability --timeout=3m
kubectl rollout status deployment/frontend -n reliability --timeout=3m
kubectl rollout status deployment/redis -n reliability --timeout=3m
```

## 14. Step 7 — Investigate DNS, Services, and endpoints

**Mode: challenge-first**

Prove internal layers independently:

```bash
kubectl get services,endpointslices -n reliability -o wide
kubectl get pods -n reliability -o wide --show-labels
kubectl describe service api -n reliability

API_POD="$(kubectl get pod -n reliability \
  -l app.kubernetes.io/name=reliability-api \
  -o jsonpath='{.items[0].metadata.name}')"

kubectl exec -n reliability "$API_POD" -- \
  python -c 'import socket; print(socket.getaddrinfo("redis", 6379))'
```

Compare `redis`, `redis.reliability`, `redis.reliability.svc`, and the full
`redis.reliability.svc.cluster.local`. Record which name another namespace
should use.

## 15. Step 8 — Install Envoy Gateway with pinned CRDs

**Mode: challenge-first**

Create `cluster/bootstrap/envoy-gateway-values.yaml` with one lab controller
replica and modest resource requests/limits. Routes do not belong in Helm
values; Gateway API resources own them.

Install the standard Gateway API CRDs plus Envoy extension CRDs:

```bash
helm template eg-crds oci://docker.io/envoyproxy/gateway-crds-helm \
  --version v1.9.2 \
  --set crds.gatewayAPI.enabled=true \
  --set crds.gatewayAPI.channel=standard \
  --set crds.envoyGateway.enabled=true \
  | kubectl apply --server-side -f -
```

Install the controller without re-owning those CRDs:

```bash
helm upgrade --install eg oci://docker.io/envoyproxy/gateway-helm \
  --version v1.9.2 \
  --namespace envoy-gateway-system \
  --create-namespace \
  --set crds.enabled=false \
  --values cluster/bootstrap/envoy-gateway-values.yaml \
  --wait \
  --timeout 10m
```

Verify:

```bash
kubectl wait --timeout=5m -n envoy-gateway-system \
  deployment/envoy-gateway --for=condition=Available

kubectl get crd gateways.gateway.networking.k8s.io \
  -o go-template='version={{ index .metadata.annotations "gateway.networking.k8s.io/bundle-version" }} channel={{ index .metadata.annotations "gateway.networking.k8s.io/channel" }}{{ "\n" }}'

kubectl api-resources --api-group=gateway.networking.k8s.io
kubectl api-resources --api-group=gateway.envoyproxy.io
```

## 16. Step 9 — Design local Envoy infrastructure

**Mode: challenge-first**

Create `envoy-proxy.yaml` and `gateway-class.yaml` in the local overlay.

Contract:

- controller name: `gateway.envoyproxy.io/gatewayclass-controller`;
- `EnvoyProxy` namespace: `reliability`;
- Envoy Service type: `NodePort`;
- external traffic policy: `Cluster` because the mapped control-plane node may
  not host an Envoy Pod;
- Service port 80 uses fixed NodePort 30080;
- StrategicMerge patch uses generated port name `http-80` and includes
  `port: 80`, the required Service port-list merge key;
- GatewayClass parametersRef includes group, kind, name, and namespace.

Hints:

1. `EnvoyProxy` is `gateway.envoyproxy.io/v1alpha1`.
2. Provider type is `Kubernetes`.
3. Service customization is under
   `spec.provider.kubernetes.envoyService`.
4. Fixed `nodePort` needs a Service `StrategicMerge` patch.
5. `GatewayClass` is `gateway.networking.k8s.io/v1`.

Do not apply yet; render through Kustomize first.

## 17. Step 10 — Define the Gateway listener

**Mode: challenge-first**

Create `gateway.yaml` with:

- name `reliability-gateway`, namespace `reliability`;
- the GatewayClass from Step 9;
- listener name `http`, protocol HTTP, port 80;
- hostname `reliability.localhost`;
- Routes allowed only from the same namespace.

Predict which resources own ports 8080, 30080, and 80, and why all three are
allowed to differ.

## 18. Step 11 — Define path routing

**Mode: challenge-first**

Create `http-route.yaml`:

| PathPrefix | Backend | Service port |
|---|---|---:|
| `/api` | `api` | 8000 |
| `/health` | `api` | 8000 |
| `/` | `frontend` | 80 |

Constraints:

- attach to `reliability-gateway` listener `http`;
- hostname is `reliability.localhost`;
- do not expose `/metrics`;
- do not rewrite `/api`;
- use Service ports;
- rely on most-specific match precedence, not list order.

The frontend Service exposes port 80 and forwards to Pod port 8080. Therefore
the HTTPRoute uses 80, while the frontend NetworkPolicy later permits 8080.

Explain why `/api/v1/visits` does not fall through to nginx even though `/`
also matches.

## 19. Step 12 — Design default-deny and explicit flows

**Mode: challenge-first**

Create a Kustomization and six portable `networking.k8s.io/v1` policies in
`kubernetes/policies/`.

1. **default-deny** selects all reliability Pods for Ingress and Egress, with
   no allow rules.
2. **allow-dns** selects all Pods and allows UDP/TCP 53 only to CoreDNS Pods in
   `kube-system`.
3. **allow-gateway-to-api** permits the generated Envoy Pods to API TCP 8000.
4. **allow-gateway-to-frontend** permits the same source to frontend TCP 8080.
5. **allow-api-to-redis** permits API egress to Redis TCP 6379.
6. **allow-redis-from-api** permits Redis ingress from API TCP 6379.

Inspect real labels before finalizing selectors:

```bash
kubectl get namespaces --show-labels
kubectl get pods -n envoy-gateway-system --show-labels
kubectl get pods -n reliability --show-labels
kubectl get service kube-dns -n kube-system -o yaml
```

For Gateway sources, constrain both namespace and generated Gateway ownership
label. Put `namespaceSelector` and `podSelector` in the same peer item to mean
AND. Separate dash items mean OR and are too broad.

Do not allow frontend Pod egress to API. The browser enters through Envoy; the
nginx Pod itself does not call the API.

## 20. Step 13 — Wire and inspect the Kustomize graph

**Mode: challenge-first**

Update the local Kustomization to include existing resources, `../../policies`,
EnvoyProxy, GatewayClass, Gateway, HTTPRoute, and current immutable digests.

```bash
mkdir -p /tmp/k8slab-phase5
kubectl kustomize kubernetes/overlays/local \
  > /tmp/k8slab-phase5/rendered.yaml

grep -nE '^kind: (GatewayClass|Gateway|HTTPRoute|EnvoyProxy|NetworkPolicy)$' \
  /tmp/k8slab-phase5/rendered.yaml

grep -nE 'reliability.localhost|30080|default-deny|allow-' \
  /tmp/k8slab-phase5/rendered.yaml

grep -nE 'latest|replace-in-overlay|hostPort|type: LoadBalancer' \
  /tmp/k8slab-phase5/rendered.yaml || true

grep -n 'sha256:' /tmp/k8slab-phase5/rendered.yaml
```

Expected: one GatewayClass, Gateway, HTTPRoute, and EnvoyProxy; six policies;
exact application digests; no mutable images or placeholders.

```bash
kubectl apply --dry-run=client -k kubernetes/overlays/local
bash scripts/require-lab-context.sh
kubectl apply --dry-run=server -k kubernetes/overlays/local
```

## 21. Step 14 — Apply and inspect reconciliation

**Mode: challenge-first**

```bash
bash scripts/require-lab-context.sh
kubectl apply -k kubernetes/overlays/local

kubectl rollout status deployment/api -n reliability --timeout=3m
kubectl rollout status deployment/frontend -n reliability --timeout=3m
kubectl rollout status deployment/redis -n reliability --timeout=3m

kubectl get gatewayclass
kubectl get gateways,httproutes -n reliability
kubectl get deployments,pods,services -n envoy-gateway-system -o wide
kubectl describe gateway reliability-gateway -n reliability
kubectl describe httproute reliability-route -n reliability
```

Gate conditions:

```text
Gateway:   Accepted=True, Programmed=True
HTTPRoute: Accepted=True, ResolvedRefs=True
```

Confirm the generated Service is NodePort `80:30080/TCP`:

```bash
kubectl get service -n envoy-gateway-system \
  -l gateway.envoyproxy.io/owning-gateway-name=reliability-gateway \
  -o wide
```

## 22. Step 15 — Reach the application through the Gateway

**Mode: challenge-first verification**

No port-forward should be running.

```bash
curl -i http://reliability.localhost:8080/
curl -i http://reliability.localhost:8080/health/live
curl -i http://reliability.localhost:8080/health/ready
curl -i http://reliability.localhost:8080/api/v1/visits
curl -i http://reliability.localhost:8080/metrics
```

Expected: frontend and API paths return 200; `/metrics` returns 404; browser
buttons work at `http://reliability.localhost:8080`.

Prove hostname matching:

```bash
curl -i -H 'Host: wrong.localhost' http://127.0.0.1:8080/
```

Expected: the hostname-specific Route does not attach.

## 23. Step 16 — Prove allowed and denied flows

**Mode: challenge-first verification**

Required flows:

```bash
curl --fail-with-body http://reliability.localhost:8080/health/ready
curl --fail-with-body http://reliability.localhost:8080/api/v1/visits
kubectl get endpointslices -n reliability
```

Unauthorized frontend Pod to API flow:

```bash
FRONTEND_POD="$(kubectl get pod -n reliability \
  -l app.kubernetes.io/name=reliability-frontend \
  -o jsonpath='{.items[0].metadata.name}')"

kubectl exec -n reliability "$FRONTEND_POD" -- \
  wget -T 3 -qO- http://api:8000/health/live
echo $?
```

Expected: timeout/failure and nonzero exit. Prove DNS is not the cause:

```bash
kubectl exec -n reliability "$FRONTEND_POD" -- \
  getent hosts api.reliability.svc.cluster.local
```

DNS should resolve while TCP remains denied.

## 24. Step 17 — Controlled failure: break the API Service selector

**Mode: challenge-first failure exercise**

### Hypothesis

Changing the API Service selector to a label no Pod has leaves API Pods Ready
but removes Service endpoints. Frontend traffic through the Gateway remains
healthy, while API paths normally return HTTP 503.

### Safety and abort conditions

- Scope: only Service `api` in namespace `reliability`.
- Do not edit Deployments, policies, Gateway, or Redis.
- Abort if frontend `/` fails or a Pod restarts unexpectedly.
- Recovery is the versioned Kustomize overlay.

Capture the healthy baseline:

```bash
kubectl get pods -n reliability -l app.kubernetes.io/name=reliability-api
kubectl get endpointslices -n reliability \
  -l kubernetes.io/service-name=api -o wide
curl -i http://reliability.localhost:8080/health/live
```

Introduce the failure:

```bash
kubectl patch service api -n reliability --type=merge \
  -p '{"spec":{"selector":{"app.kubernetes.io/name":"selector-does-not-exist","app.kubernetes.io/component":"api"}}}'
```

Investigate before reading the diagnosis:

```bash
curl -i http://reliability.localhost:8080/
curl -i http://reliability.localhost:8080/health/live
kubectl get pods -n reliability \
  -l app.kubernetes.io/name=reliability-api --show-labels
kubectl get service api -n reliability -o yaml
kubectl get endpointslices -n reliability \
  -l kubernetes.io/service-name=api -o yaml
kubectl describe httproute reliability-route -n reliability
kubectl get events -n reliability --sort-by=.lastTimestamp
```

Write a one-sentence hypothesis naming the failed boundary and two pieces of
evidence.

<details>
<summary>Diagnosis and explanation</summary>

The Gateway and HTTPRoute remain valid, and API Pods remain Ready. The Service
selector no longer matches their labels, so its EndpointSlice has no serving
endpoints. Envoy matches the request but has no upstream backend. Restarting
API Pods cannot repair a selector stored in the Service.

</details>

Recover from Git:

```bash
bash scripts/require-lab-context.sh
kubectl apply -k kubernetes/overlays/local
kubectl get endpointslices -n reliability \
  -l kubernetes.io/service-name=api -o wide
curl --fail-with-body http://reliability.localhost:8080/health/live
kubectl diff -k kubernetes/overlays/local
```

The final command must produce no output.

## 25. Step 18 — Final validation

```bash
bash scripts/require-lab-context.sh

kubectl get nodes -L reliability.dev/workload
kubectl get tigerastatus
kubectl get gatewayclass
kubectl get gateways,httproutes -n reliability
kubectl get networkpolicies -n reliability
kubectl get deployments,pods,services,endpointslices -A

kubectl apply --dry-run=server -k kubernetes/overlays/local
kubectl diff -k kubernetes/overlays/local

curl --fail-with-body http://reliability.localhost:8080/ >/dev/null
curl --fail-with-body http://reliability.localhost:8080/health/live
curl --fail-with-body http://reliability.localhost:8080/health/ready
curl --fail-with-body http://reliability.localhost:8080/api/v1/visits

trivy --config .trivy.yaml config --exit-code 1 .
git diff --check
git status --short
```

Repeat the denied frontend-to-API test. A successful application path and a
successful denial are both required evidence.

## 26. Evidence record

Create `docs/05-networking-and-gateway-api-evidence.md` containing:

- date, branch, base commit, and pinned versions;
- Calico status and node readiness;
- GatewayClass, Gateway, and HTTPRoute conditions;
- generated Envoy Service type and fixed NodePort;
- final published application digests;
- external curl and browser results;
- NetworkPolicy inventory;
- one allowed-flow proof and one denied-flow proof;
- broken-selector timeline, diagnosis, recovery, and no-diff result;
- answers to every review question;
- production limitations.

Do not paste full controller logs, generated CRDs, tokens, or unrelated machine
information.

## 27. Troubleshooting

| Symptom | Evidence | Likely causes | Next test |
|---|---|---|---|
| Nodes stay `NotReady` | Calico Pods, `tigerastatus`, node conditions | CNI missing, wrong Pod CIDR, pull failure | Inspect first failing Calico Pod and `NetworkUnavailable` |
| GatewayClass not accepted | class status, controller logs | wrong controller or parametersRef | Compare exact controller and EnvoyProxy identity |
| Gateway not programmed | listener conditions, generated proxy resources | invalid listener or infrastructure patch | Inspect Gateway events before changing Routes |
| Route `ResolvedRefs=False` | route conditions | wrong Service name or port | Compare backendRef with live Service |
| Host connection refused | kind config and Envoy Service | missing mapping or wrong NodePort | Trace 8080 → 30080 → 80 |
| Root works, `/api` is nginx 404 | route conditions and browser Network tab | API rule rejected or stale frontend | Curl `/api` directly and inspect served `app.js` |
| Gateway returns 503 | Pods, Service selector, EndpointSlice, policies | no ready endpoint, selector mismatch, denial | Check each boundary in that order |
| DNS fails | Pod resolver, CoreDNS endpoints, DNS policy | DNS egress missing or selector wrong | Resolve full Service FQDN from same Pod |
| DNS works, TCP times out | policies selecting both Pods | NetworkPolicy denial | Inspect policy union and exact ports |
| Policy exists but traffic still passes | CNI status and policy selectors | non-enforcing CNI or selector miss | Confirm Calico and compare real labels |
| Browser CSP error | response header, console, `app.js` | stale image or missing `'self'` | Curl headers and JS through Gateway |

Use this diagnostic order:

```text
client name/port
  -> kind host mapping
  -> Envoy NodePort Service
  -> Gateway/HTTPRoute conditions
  -> backend Service selector
  -> EndpointSlice readiness
  -> NetworkPolicy both directions
  -> application/dependency state
```

## 28. Production considerations

- The kind NodePort plus host mapping stands in for a cloud or bare-metal load
  balancer.
- Local HTTP needs production DNS, HTTPS listeners, certificate lifecycle, and
  an explicit TLS standard.
- One controller and a lab proxy fleet are not high availability.
- `.localhost` is not production DNS.
- Calico is the lab choice; production CNI selection depends on the platform
  and operational requirements.
- NetworkPolicy is not application identity or layer-7 authorization.
- Policies require continuous tests because label changes alter their scope.
- Gateway telemetry arrives in later phases.
- Phase 6 moves manual package lifecycle into GitOps while keeping CNI
  bootstrap safety explicit.

## 29. Cleanup and reset

Remove only application networking resources while retaining Calico and the
controller:

```bash
bash scripts/require-lab-context.sh
kubectl delete -f kubernetes/overlays/local/http-route.yaml --ignore-not-found
kubectl delete -f kubernetes/overlays/local/gateway.yaml --ignore-not-found
kubectl delete -f kubernetes/overlays/local/gateway-class.yaml --ignore-not-found
kubectl delete -f kubernetes/overlays/local/envoy-proxy.yaml --ignore-not-found
kubectl delete -k kubernetes/policies --ignore-not-found
```

Reapply with `kubectl apply -k kubernetes/overlays/local`.

Remove the controller only for an intentional reset:

```bash
helm uninstall eg -n envoy-gateway-system
```

Do not casually delete CRDs: that deletes their custom resources.

Full disposable reset:

```bash
kubectl config current-context
bash scripts/require-lab-context.sh
kind delete cluster --name k8slab
```

Recovery order:

```text
kind -> Calico -> application -> Envoy Gateway CRDs/controller
-> Gateway resources/policies -> verification
```

## 30. Definition of done

- [ ] Implementation is isolated on `phase-5-networking-gateway`.
- [ ] Calico `v3.33.0` is the active CNI and policy engine.
- [ ] All three nodes are Ready after clean recreation.
- [ ] Frontend calls same-origin API paths and CSP permits self only.
- [ ] New application images are deployed by top-level digest.
- [ ] Envoy Gateway `v1.9.2` uses compatible standard Gateway API CRDs.
- [ ] GatewayClass is Accepted.
- [ ] Gateway is Accepted and Programmed.
- [ ] HTTPRoute is Accepted with ResolvedRefs true.
- [ ] `reliability.localhost:8080` works without port-forwarding.
- [ ] `/metrics` is not externally routed.
- [ ] Default-deny ingress and egress are active.
- [ ] DNS, Gateway backends, and API-to-Redis are explicitly allowed.
- [ ] Frontend-Pod-to-API is proven blocked.
- [ ] Broken Service selector is diagnosed and recovered.
- [ ] `kubectl diff` is empty after recovery.
- [ ] Trivy and `git diff --check` pass.
- [ ] No plaintext secret, generated CRD bundle, or mutable app tag is committed.
- [ ] Evidence and review answers are recorded.
- [ ] CI passes before merge.

## 31. Review questions

1. What work belongs to CoreDNS, Service, EndpointSlice, kube-proxy, Envoy,
   and HTTPRoute during one request?
2. Why can Service DNS resolve successfully while requests fail?
3. How do you distinguish selector mismatch from NetworkPolicy denial?
4. Why does creating NetworkPolicy not prove enforcement?
5. Why disable kindnet before Calico owns Pod networking?
6. Explain GatewayClass, Gateway, listener, and HTTPRoute ownership.
7. Distinguish `Accepted`, `Programmed`, and `ResolvedRefs`.
8. Why does `/api` win over `/` when both are PathPrefix matches?
9. Why use same-origin requests instead of a hard-coded API origin?
10. Trace ports 8080, 30080, 80, and 8000 to the API container.
11. Why use `externalTrafficPolicy: Cluster` in this kind design?
12. Why must namespaceSelector and podSelector share one policy peer for AND?
13. Which policies permit an API request that updates Redis?
14. Why is frontend-Pod-to-API denied while its browser page can call API?
15. Why can NetworkPolicy not protect individual HTTP paths?
16. Gateway returns 503 while API Pods are `1/1`: what do you inspect next?
17. Why does restarting API Pods not repair a broken Service selector?
18. What changes for production load balancing, DNS, TLS, CNI, and policy?

## 32. Official references

- Gateway API overview: <https://gateway-api.sigs.k8s.io/concepts/api-overview/>
- Gateway API HTTP routing: <https://gateway-api.sigs.k8s.io/guides/http-routing/>
- Envoy Gateway Helm: <https://gateway.envoyproxy.io/v1.9/install/install-helm/>
- Envoy Gateway routing: <https://gateway.envoyproxy.io/v1.9/tasks/traffic/http-routing/>
- EnvoyProxy customization: <https://gateway.envoyproxy.io/v1.9/tasks/operations/customize-envoyproxy/>
- Calico on kind: <https://docs.tigera.io/calico/latest/getting-started/kubernetes/kind>
- Calico Helm: <https://docs.tigera.io/calico/latest/getting-started/kubernetes/helm>
- Kubernetes Services: <https://kubernetes.io/docs/concepts/services-networking/service/>
- Kubernetes DNS: <https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/>
- Kubernetes NetworkPolicy: <https://kubernetes.io/docs/concepts/services-networking/network-policies/>
- kind configuration: <https://kind.sigs.k8s.io/docs/user/configuration/>

## 33. Next phase

Phase 6 moves cluster and platform reconciliation from manual Helm and
`kubectl apply` to Argo CD. The Gateway, routes, policies, and exact image
digests become GitOps-managed desired state, and deliberate live drift becomes
observable and self-healing.
