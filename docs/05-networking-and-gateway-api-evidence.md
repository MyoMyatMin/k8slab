# Phase 5 — Networking and Gateway API evidence

## Record

- Date: 2026-10-10 (Asia/Bangkok)
- Branch: `phase-5-networking-gateway`
- Base commit: `43446e77d161111c26ea54afd09629fb7401d715`
- Kubernetes: `v1.37.0`
- kind: `v0.33.0`
- Calico Open Source: `v3.33.0`
- Gateway API CRDs: `v1.6.1`, standard channel
- Envoy Gateway: `v1.9.2`
- Kustomize: `v5.8.1`
- Local hostname: `reliability.localhost`
- Host port: `8080`
- Envoy NodePort: `30080`

The cluster uses one kind control-plane and two worker nodes. The workers carry
`reliability.dev/workload=true`. All three nodes reported `Ready`. Calico,
IP pools, and tiers reported `Available=True`, `Progressing=False`, and
`Degraded=False`.

## Gateway and data plane

- `reliability-gateway-class`: `Accepted=True`; controller
  `gateway.envoyproxy.io/gatewayclass-controller`.
- `reliability-gateway`: `Accepted=True`, `Programmed=True`; one attached
  HTTPRoute on listener `http` for `reliability.localhost:80`.
- `reliability-route`: `Accepted=True`, `ResolvedRefs=True` after recovery.
- Generated Envoy Deployment: `1/1` available; generated Pod `2/2` Ready with
  zero restarts at final validation.
- Generated Service: `NodePort`, `externalTrafficPolicy: Cluster`, Service port
  80, NodePort 30080, generated target port 10080.

The reachable path is:

```text
client reliability.localhost:8080
  -> kind host mapping to control-plane container:30080
  -> Envoy NodePort Service:30080 / Service port:80
  -> generated Envoy proxy
  -> HTTPRoute backend Service
  -> ready application Pod
```

## Published application images

- API:
  `ghcr.io/myomyatmin/k8slab-api@sha256:89c3cfefddbca7bb6ae513418d6f830ae55941e7d036a6e438fa2216bb268863`
- Frontend:
  `ghcr.io/myomyatmin/k8slab-frontend@sha256:d2643e31dec5e1f781a23aab7ae63ad33cdceef9b346693ccf587eeef90ee161`
- Redis:
  `redis:8.10.2-alpine3.23@sha256:3811787313eba226a2ef38658c6ccb91cd5e110edc89c37767de373120a0e5a0`

The running Pod image references and image IDs matched these immutable
digests.

## External and browser verification

The following results were observed without a port-forward:

| Request | Result |
|---|---|
| `GET http://reliability.localhost:8080/` | `200`, frontend served by nginx |
| `GET /health/live` | `200`, API live |
| `GET /health/ready` | `200`, Redis dependency up |
| `GET /api/v1/visits` | `200`, visit counter updated |
| `GET /metrics` | `404` from nginx; API metrics not exposed |
| `Host: wrong.localhost` | `404`; hostname-specific route not selected |

The browser loaded the frontend through the Gateway and its same-origin
buttons reached the routed API paths. The response CSP used
`connect-src 'self'`.

## NetworkPolicy evidence

Six policies were active in namespace `reliability`:

1. `default-deny`
2. `allow-dns`
3. `allow-gateway-to-api`
4. `allow-gateway-to-frontend`
5. `allow-api-to-redis`
6. `allow-redis-from-api`

Allowed-flow proof:

- Gateway requests to `/health/ready` and `/api/v1/visits` returned `200`.
- Readiness reported Redis `up`, proving DNS plus API-to-Redis traffic worked.
- API, frontend, and Redis EndpointSlices all contained ready Pod endpoints.

Denied-flow proof:

- From a frontend Pod, `api.reliability.svc.cluster.local` resolved to Service
  IP `10.96.184.5`.
- From the same Pod, an HTTP connection to `api:8000/health/live` timed out and
  exited `1`.
- DNS therefore remained allowed while unauthorized frontend-to-API TCP was
  denied by the enforced policy set.

## Controlled Service-selector failure

The API Service selector was temporarily changed to
`app.kubernetes.io/name=selector-does-not-exist`.

Observed timeline:

1. The frontend route continued to return `200`.
2. API health through the Gateway returned `503`.
3. Both API Pods remained `1/1 Running` with zero restarts.
4. The API Service retained its ClusterIP, but its EndpointSlice contained no
   endpoints.
5. The HTTPRoute remained `Accepted=True` and `ResolvedRefs=True`, while its
   transient `BackendsAvailable=False` condition reported
   `EndpointsNotFound`.

Diagnosis: the failed boundary was Service discovery. The Service selector no
longer matched healthy API Pod labels, so Envoy had no upstream endpoints.
Restarting Pods could not repair a selector stored on the Service.

Recovery used the versioned desired state:

```text
kubectl apply -k kubernetes/overlays/local
```

The two API endpoints returned, `/health/live` returned `200`, the route
returned to healthy conditions, and
`kubectl diff -k kubernetes/overlays/local` produced no output.

## Final validation

- Server-side dry-run of the complete local overlay passed.
- `kubectl diff -k kubernetes/overlays/local` was empty.
- All required external requests succeeded.
- The required denied request failed while DNS succeeded.
- Trivy detected 21 configuration files and reported zero
  misconfigurations. It could not refresh remote checks because of the local
  credential helper, fell back to embedded checks, and exited successfully.
- `git diff --check` passed.

## Review answers

1. **Request responsibilities.** For a visit request, the host resolver maps
   `.localhost` to loopback; kind forwards host port 8080 to NodePort 30080;
   kube-proxy forwards that NodePort to an Envoy endpoint; Envoy applies the
   listener and HTTPRoute and uses Service/EndpointSlice data to reach an API
   Pod. The API uses CoreDNS to resolve Redis, the Redis Service provides a
   stable ClusterIP, its EndpointSlice records the ready Redis Pod, and
   kube-proxy forwards the ClusterIP connection.
2. **DNS without connectivity.** CoreDNS can return a Service ClusterIP even
   when its EndpointSlice is empty, its Pods are unready, or NetworkPolicy
   blocks the subsequent TCP connection.
3. **Selector mismatch versus policy denial.** A selector mismatch leaves
   healthy Pods but an empty Service EndpointSlice. A policy denial leaves the
   correct endpoints present; DNS succeeds but the connection times out or is
   rejected. Inspect Pod labels, the Service selector, EndpointSlice, and the
   policies selecting both peers.
4. **Policy object versus enforcement.** The Kubernetes API stores
   NetworkPolicy regardless of whether the active CNI enforces it. A
   policy-capable CNI and a controlled denied-flow test are required evidence.
5. **Why disable kindnet.** Calico must exclusively own Pod IP allocation,
   routing, and policy enforcement. Running kindnet beside it would create
   ambiguous or conflicting network ownership.
6. **Gateway API ownership.** GatewayClass selects the controller.
   Gateway requests data-plane infrastructure. A listener defines hostname,
   protocol, port, and allowed Routes. HTTPRoute attaches to a listener,
   matches requests, and names backend Services.
7. **Status conditions.** `Accepted` means the controller accepts the object
   or listener. `Programmed` means usable data-plane configuration and
   infrastructure were produced. `ResolvedRefs` means referenced objects and
   ports are valid; it does not guarantee that the Service has ready
   endpoints.
8. **Path precedence.** Both `/api` and `/` are prefix matches for an API
   request, but Gateway API chooses the longest, most specific matching prefix;
   YAML list order is not the routing mechanism.
9. **Same-origin frontend.** Relative API paths avoid environment-specific
   hostnames and CORS policy, and let one Gateway hostname own both UI and API
   routing.
10. **Port trace.** The client reaches host port 8080; kind maps it to control-
    plane container port 30080; that is the Envoy Service NodePort; Service
    port 80 represents the HTTP listener; Envoy routes API traffic to Service
    and container port 8000. The generated Envoy target port 10080 is an
    internal implementation detail.
11. **External traffic policy.** The host mapping always enters through the
    control-plane node, while the Envoy Pod may run on a worker. `Cluster`
    permits forwarding to an Envoy endpoint on another node; `Local` could
    reject traffic when the entry node has no local Envoy Pod.
12. **Selector AND semantics.** A `namespaceSelector` and `podSelector` in the
    same peer item must both match. Putting them in separate list items creates
    an OR and permits a broader source set.
13. **API-to-Redis policy path.** `allow-gateway-to-api` permits Envoy ingress
    to the API, `allow-dns` permits Redis name resolution,
    `allow-api-to-redis` permits API egress on TCP 6379, and
    `allow-redis-from-api` permits Redis ingress from API Pods. Reply traffic
    for established connections is automatically allowed.
14. **Browser versus frontend Pod.** JavaScript executes in the user's browser
    and calls the API through Envoy. The nginx Pod only serves static files, so
    it neither needs nor receives direct API egress permission.
15. **HTTP paths and policy.** Kubernetes NetworkPolicy is primarily layer 3/4
    and can select identities, protocols, and ports, not HTTP paths. HTTPRoute
    and application authorization own layer-7 path decisions.
16. **503 with Ready Pods.** Inspect the Service selector, Pod labels,
    EndpointSlice readiness, HTTPRoute backend conditions, and then policies.
    Pod readiness alone does not prove Service selection or reachability.
17. **Why restarts do not fix selectors.** The incorrect desired selector is
    stored on the Service. Replacement Pods retain the Deployment's correct
    labels, so restarting them does not change the mismatching Service.
18. **Production changes.** Replace kind's host mapping with a supported load
    balancer or production Gateway implementation; use real DNS; terminate TLS
    with automated certificate lifecycle; run controllers and proxies highly
    available across real failure domains; select and operate the platform CNI
    deliberately; test policies continuously; and add identity-aware,
    layer-7 controls where required.

## Production limitations

- One laptop, one control-plane, and one Envoy replica do not provide real
  failure-domain or control-plane availability.
- NodePort plus a kind host mapping is a local substitute for a managed or
  bare-metal load balancer.
- `.localhost` and plain HTTP must become production DNS and HTTPS with managed
  certificates and an explicit TLS policy.
- CNI installation remains a bootstrap dependency; production ownership and
  upgrades must match the target platform.
- Kubernetes NetworkPolicy is not user identity, mTLS, or HTTP authorization.
- Redis is still an unauthenticated, ephemeral single replica.
- Requests, limits, policy selectors, and availability settings require
  measurement and continuous validation under production workloads.
