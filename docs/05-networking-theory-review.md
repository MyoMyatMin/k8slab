# Phase 5 — Kubernetes Networking Theory Review

This document is the conceptual companion to
[`05-networking-and-gateway-api.md`](05-networking-and-gateway-api.md).
Use the phase guide to perform the lab. Use this review when you want to
rebuild the mental model behind the commands.

The goal is not to memorize every object or command. The goal is to answer two
questions during an incident:

1. Which networking boundary should have handled this packet?
2. What evidence proves that boundary is healthy or broken?

## 1. The networking layers in this lab

Several systems cooperate to deliver one request. They solve different
problems:

| Layer | Main question | Phase 5 component |
|---|---|---|
| Name resolution | What IP belongs to this name? | host resolver or CoreDNS |
| Pod networking | Can packets move between Pod and node IPs? | Calico CNI |
| Stable service identity | Which stable virtual IP represents these Pods? | Service |
| Backend discovery | Which ready Pod IPs currently implement the Service? | EndpointSlice |
| Virtual-IP forwarding | How does traffic reach a Service backend? | kube-proxy |
| External entry | How does host traffic enter the cluster? | kind mapping and NodePort |
| HTTP routing | Which backend owns this hostname and path? | Envoy and HTTPRoute |
| Network authorization | Is this source allowed to reach that destination port? | NetworkPolicy |
| Application health | Can the process and its dependency serve the request? | probes and health endpoints |

A healthy Pod proves only that its containers are ready. It does not prove
that DNS, a Service selector, a route, a policy, or the external entry path is
correct.

## 2. The complete request path

Consider this request:

```text
http://reliability.localhost:8080/api/v1/visits
```

The end-to-end path is:

```text
Browser or curl
  |
  | host resolver: reliability.localhost -> loopback
  v
Mac TCP port 8080
  |
  | kind extraPortMappings
  v
control-plane container TCP port 30080
  |
  | kube-proxy NodePort handling
  v
Envoy NodePort Service, nodePort 30080 / service port 80
  |
  v
generated Envoy proxy Pod
  |
  | listener accepts hostname reliability.localhost on HTTP port 80
  | HTTPRoute chooses the /api prefix
  v
API Service port 8000
  |
  | EndpointSlice supplies ready API Pod IPs
  | NetworkPolicy permits Envoy -> API:8000
  v
API Pod port 8000
  |
  | CoreDNS resolves redis
  | kube-proxy handles the Redis ClusterIP
  | NetworkPolicy permits API -> Redis:6379
  v
Redis Pod port 6379
```

This path crosses host networking, node networking, the Kubernetes service
model, HTTP routing, and policy enforcement. A failure at any arrow can produce
a browser error while all application Pods remain `Running`.

## 3. The identities you must keep separate

Kubernetes networking uses several kinds of identity.

### Name

Examples:

```text
reliability.localhost
api
api.reliability
api.reliability.svc.cluster.local
```

A name is convenient for humans and applications. It must be resolved or
matched before it can direct traffic.

### IP address

The lab contains several IP categories:

- loopback on the Mac;
- kind node/container IPs;
- Pod IPs assigned by Calico;
- Service ClusterIPs allocated by Kubernetes;
- Gateway status addresses.

Do not treat all of them as equivalent. They exist at different boundaries.

### Port

A port identifies a network endpoint within one IP boundary. The same request
can legitimately use several different ports while it moves through the
system.

### Label

Labels are identity metadata used by controllers and policies:

```yaml
app.kubernetes.io/name: reliability-api
app.kubernetes.io/component: api
```

Services and NetworkPolicies usually select workloads by labels, not by Pod
name or Pod IP. This is what lets replacement Pods join automatically.

## 4. Pod networking and the CNI

### What the CNI does

CNI means Container Network Interface. Kubernetes delegates Pod network setup
to a CNI implementation. In this lab Calico:

- assigns Pod IP addresses;
- connects Pods to the node network;
- installs routes or encapsulation needed between nodes;
- enforces Kubernetes NetworkPolicy.

Kubernetes can store NetworkPolicy objects without enforcing them. Enforcement
exists only when the active network plugin implements it. That is why creating
a policy is not proof; a controlled denied connection is proof.

### Why kindnet was disabled

kind normally installs kindnet for basic Pod networking. Phase 5 disables it
before installing Calico so one component owns:

- Pod IP allocation;
- Pod routing;
- policy enforcement.

Running two CNIs as competing owners would make packet behavior ambiguous and
troubleshooting harder.

### Why the Pod CIDR matters

The lab uses:

```text
Pod CIDR: 10.244.0.0/16
```

The Pod CIDR must not overlap the host network or the network containing the
kind node containers. Overlap creates ambiguous routing: the operating system
cannot reliably decide whether an address is local to one network or reachable
through another.

The lab originally demonstrated a useful partial-failure pattern when a Pod
CIDR overlapped OrbStack's node network:

- Pods could appear Running;
- some Pod-to-Pod communication worked;
- CoreDNS could not reach the Kubernetes API on its node address;
- Service-name resolution consequently failed.

The lesson is that partial connectivity does not prove the CNI is correct.

## 5. CoreDNS and Kubernetes service names

CoreDNS answers DNS queries for Kubernetes names.

For Service `api` in namespace `reliability`, useful forms include:

```text
api
api.reliability
api.reliability.svc
api.reliability.svc.cluster.local
```

Inside the same namespace, `api` normally works because the Pod resolver adds
search domains. From another namespace, use at least `api.reliability`; the
fully qualified name is the least ambiguous.

### What DNS proves

If this succeeds:

```text
getent hosts api.reliability.svc.cluster.local
```

it proves that the name resolved to an IP. It does not prove:

- the Service selects a Pod;
- the selected Pod is Ready;
- the destination port is correct;
- NetworkPolicy allows the connection;
- the application responds.

This distinction is central:

```text
DNS success != connection success
```

CoreDNS normally returns the stable Service ClusterIP. That ClusterIP can
continue to exist even when the Service has zero endpoints.

## 6. Service: stable virtual identity

Pods are replaceable. Their names and IPs change. A Service provides a stable
name and virtual ClusterIP in front of a changing Pod set.

The API Service declares:

```yaml
selector:
  app.kubernetes.io/name: reliability-api
  app.kubernetes.io/component: api
ports:
  - port: 8000
    targetPort: http
```

The selector means:

> Find Pods in this namespace carrying both labels.

The Service does not own the Pods and does not create them. It discovers them.

### Service ports

Keep these fields distinct:

| Field | Meaning |
|---|---|
| `port` | Port clients use on the Service |
| `targetPort` | Port or named port on the selected Pod |
| `nodePort` | Port exposed on every node for a NodePort Service |

For the frontend:

```text
HTTPRoute backend port 80
  -> frontend Service port 80
  -> targetPort named http
  -> frontend Pod port 8080
```

An HTTPRoute references the Service port, so it uses 80. NetworkPolicy
controls traffic arriving at the Pod, so it permits 8080.

## 7. EndpointSlice: the live backend list

The EndpointSlice controller compares Service selectors with Pod labels and
readiness. It records the backend addresses currently eligible to receive
traffic.

Conceptually:

```text
Service selector
  + Pod labels
  + Pod readiness
  = EndpointSlice entries
```

If a Deployment replaces an API Pod, the new Pod receives a new IP. The
Service identity stays stable, while the EndpointSlice is updated.

### Why EndpointSlice is decisive evidence

If API Pods are `1/1 Ready` but the API EndpointSlice is empty, investigate:

- Service selector;
- Pod labels;
- namespace;
- readiness and serving conditions.

Do not restart the Pods first. A restart cannot repair an incorrect selector
stored on the Service.

## 8. kube-proxy and Service forwarding

kube-proxy watches Services and EndpointSlices and programs node networking
rules. Those rules implement virtual Service addresses and NodePorts.

Conceptually:

```text
ClusterIP:service-port
  -> one ready EndpointSlice address:target-port
```

and:

```text
node-IP:nodePort
  -> one ready Service endpoint
```

kube-proxy does not:

- resolve DNS names;
- decide HTTP paths;
- create Pods;
- determine whether an application response is logically correct.

It forwards network connections according to Kubernetes Service state.

## 9. Gateway API and Envoy

Gateway API separates infrastructure ownership from application routing.

### Control plane and data plane

The Envoy Gateway controller is the control plane. It watches Gateway API
objects, validates them, creates proxy infrastructure, and produces Envoy
configuration.

The generated Envoy proxy is the data plane. It receives actual client
connections and forwards requests.

```text
Gateway API objects
  -> Envoy Gateway controller
  -> generated Deployment, Service, and Envoy configuration
  -> Envoy proxy handles traffic
```

Installing the controller alone does not create an application entry point.
The generated proxy appears after a Gateway requests one.

### CRDs and custom resources

A Custom Resource Definition extends the Kubernetes API with a new object
type. Installing the Gateway CRD teaches Kubernetes what a `Gateway` object
looks like. Creating `reliability-gateway` creates one instance of that type.

```text
CRD: definition of the type
custom resource: one object of that type
```

### GatewayClass

GatewayClass is cluster-scoped and selects the responsible controller:

```text
reliability-gateway-class
  -> gateway.envoyproxy.io/gatewayclass-controller
```

Its `parametersRef` points to the EnvoyProxy customization used for generated
infrastructure.

### EnvoyProxy

EnvoyProxy is an Envoy Gateway extension. In this lab it says:

- create the proxy Service as `NodePort`;
- use `externalTrafficPolicy: Cluster`;
- assign NodePort 30080 to generated Service port 80.

It does not define application paths. Gateway API objects own routing.

### Gateway and listener

Gateway requests the entry point. Its listener defines:

- protocol: HTTP;
- port: 80;
- hostname: `reliability.localhost`;
- which namespaces may attach Routes.

The listener is comparable to a socket plus routing boundary, not to an
application backend.

### HTTPRoute

HTTPRoute attaches to a Gateway listener and defines HTTP matches and backend
Services:

```text
/api/*    -> API Service:8000
/health/* -> API Service:8000
/*        -> frontend Service:80
```

`/api/v1/visits` matches both `/api` and `/`. Gateway API chooses the longest,
most specific prefix, so `/api` wins. Rule list order is not the mechanism.

### Status conditions

| Condition | Meaning |
|---|---|
| `Accepted=True` | The controller accepts the object or listener configuration |
| `Programmed=True` | The controller produced usable data-plane infrastructure/configuration |
| `ResolvedRefs=True` | Referenced objects and ports exist and are valid |

`ResolvedRefs=True` does not guarantee ready backend endpoints. During the
broken-selector exercise, the Service reference still existed while its
EndpointSlice was empty.

## 10. Why the port numbers differ

The Phase 5 path contains several ports because each belongs to a different
boundary:

| Port | Owner | Purpose |
|---:|---|---|
| 8080 | Mac/kind mapping | User-facing local port |
| 30080 | Envoy NodePort and kind node mapping | Stable node entry port |
| 80 | Gateway listener and Envoy Service | HTTP entry inside Kubernetes |
| 10080 | Generated Envoy target port | Internal proxy listener implementation |
| 8000 | API Service and API container | API workload traffic |
| 8080 | Frontend container | nginx workload traffic |
| 6379 | Redis Service and container | Redis protocol |
| 53 | CoreDNS | DNS over UDP/TCP |

The translations are intentional:

```text
host:8080 -> node:30080 -> Envoy Service:80 -> Envoy Pod:10080
```

After HTTP routing:

```text
/api    -> API Service:8000 -> API Pod:8000
/        -> frontend Service:80 -> frontend Pod:8080
```

## 11. Why `externalTrafficPolicy: Cluster` is required locally

kind maps host port 8080 to port 30080 on the control-plane node container.
The generated Envoy Pod can run on either worker.

With `externalTrafficPolicy: Local`, a node accepts external traffic only when
it has a local Service endpoint. The control-plane may have no Envoy Pod, so
the host mapping could fail.

With `externalTrafficPolicy: Cluster`, the entry node can forward to a ready
Envoy endpoint on another node. The tradeoff is that this mode may not preserve
the original client source IP in the same way as `Local`.

## 12. Same-origin browser requests

The browser loads the page from:

```text
http://reliability.localhost:8080
```

Frontend JavaScript uses relative paths such as:

```text
/health/ready
/api/v1/visits
```

The browser therefore sends API requests to the same scheme, hostname, and
port as the page. Envoy selects the API backend by path.

Benefits:

- no environment-specific API hostname in JavaScript;
- no separate CORS dependency for normal application traffic;
- one Gateway owns the public routing boundary;
- the CSP can use `connect-src 'self'`.

The JavaScript runs in the browser. The frontend nginx Pod does not call the
API. That is why browser-to-API works while frontend-Pod-to-API is deliberately
denied.

## 13. NetworkPolicy theory

### Default behavior

Without selecting NetworkPolicies, Kubernetes Pod networking is normally
default-allow. Any Pod that can route to another Pod may attempt a connection.

### Isolation directions

A policy selects destination or source Pods with `podSelector` and declares
which directions it isolates:

- `Ingress`: connections entering selected Pods;
- `Egress`: connections leaving selected Pods.

This policy isolates every Pod in the namespace in both directions:

```yaml
podSelector: {}
policyTypes:
  - Ingress
  - Egress
```

With no allow rules, selected traffic is denied.

### Policies are additive

NetworkPolicies are not processed top to bottom. All allow rules from policies
selecting a Pod are combined.

```text
effective allowed traffic
  = union of every matching allow rule
```

There is no explicit ordered deny rule in standard Kubernetes NetworkPolicy.
Default-deny works because no rule allows the traffic until an exception is
added.

### Both isolated directions must allow a flow

For API to Redis:

```text
API egress -> Redis ingress
```

The lab therefore needs both:

- `allow-api-to-redis` for API egress;
- `allow-redis-from-api` for Redis ingress.

Return traffic for an established permitted connection is automatically
allowed by the policy model. A separate Redis-to-API initiation rule is not
required.

### AND versus OR in peers

This peer means namespace AND Pod must match:

```yaml
from:
  - namespaceSelector:
      matchLabels:
        kubernetes.io/metadata.name: envoy-gateway-system
    podSelector:
      matchLabels:
        gateway.envoyproxy.io/owning-gateway-name: reliability-gateway
```

Putting the selectors into separate dash items means OR and permits a broader
set of sources.

### Why DNS is an explicit flow

Default-deny egress also blocks DNS. Before API can connect to `redis`, it must
reach CoreDNS on UDP or TCP port 53. The `allow-dns` policy restores only that
required resolution path.

### Layer 3/4 boundary

Standard NetworkPolicy understands network identity, protocol, and port. It
does not understand HTTP paths such as `/api` or `/metrics`.

Use HTTPRoute and application authorization for layer-7 decisions. Use
NetworkPolicy to restrict which workloads may establish transport connections.

## 14. The final allowed communication graph

After default-deny and the five allow policies:

```text
All reliability Pods -> CoreDNS:53 UDP/TCP
Envoy proxy           -> frontend Pod:8080 TCP
Envoy proxy           -> API Pod:8000 TCP
API Pod               -> Redis Pod:6379 TCP
```

Examples intentionally not allowed:

```text
frontend Pod -> API Pod
frontend Pod -> Redis Pod
Redis Pod    -> initiate connection to API Pod
unrelated Pod -> API, frontend, or Redis
application Pod -> arbitrary internet destination
```

Least privilege means the application receives only the network paths it
needs, not every path that happens to be convenient.

## 15. A repeatable troubleshooting method

Do not start by restarting Pods. Follow the packet path in order and stop at
the first broken boundary:

```text
1. client name and port
2. host-to-kind mapping
3. Envoy NodePort Service
4. Gateway and listener status
5. HTTPRoute match and references
6. backend Service selector
7. EndpointSlice addresses/readiness
8. NetworkPolicy in both directions
9. application and dependency state
```

### Step 1: classify the symptom

| Symptom | First likely boundary |
|---|---|
| Connection refused at host | host mapping, NodePort, proxy readiness |
| Wrong-host request returns 404 | expected hostname routing behavior |
| Root works but API returns 404 from nginx | HTTPRoute path matching |
| Gateway returns 503 | backend endpoint or reachability |
| DNS name does not resolve | Pod resolver, CoreDNS, DNS egress policy |
| DNS resolves but TCP times out | NetworkPolicy or data path |
| Pod is Pending | scheduler constraints, not application networking |
| Pod is Running but `0/1` | readiness or dependency failure |

### Step 2: test the dependency at three layers

When debugging a Service, compare:

1. direct Pod IP and container port;
2. Service ClusterIP and Service port;
3. Service DNS name and Service port.

Interpretation:

| Pod IP | Service IP | DNS name | Likely boundary |
|---|---|---|---|
| works | works | fails | DNS |
| works | fails | fails | Service/kube-proxy/policy around Service path |
| fails | fails | fails | CNI, policy, destination process, or wrong port |

Direct Pod-IP tests are diagnostic only. Applications should normally use
stable Service names.

### Step 3: compare selectors with labels

Read:

```text
kubectl get service <name> -o yaml
kubectl get pods --show-labels
kubectl get endpointslices -l kubernetes.io/service-name=<name>
```

Ask:

- Do all selector key/value pairs exist on the intended Pods?
- Are the objects in the same namespace?
- Are the matching Pods Ready?
- Does the EndpointSlice contain their current IPs?

### Step 4: read status conditions as controller explanations

Inspect Gateway and HTTPRoute conditions before changing configuration.
Conditions often tell you whether the failure is acceptance, programming,
reference resolution, or backend availability.

### Step 5: inspect the policy union

For one connection, name:

- source Pod and namespace;
- destination Pod and namespace;
- destination protocol and Pod port;
- source egress isolation;
- destination ingress isolation;
- every allow policy selecting either side.

If DNS succeeds but TCP times out, policy selection and destination port are
high-value checks.

## 16. Worked failure examples

### Failure A: broken Service selector

Observed:

- API Pods `1/1 Running`;
- API Service exists;
- API EndpointSlice empty;
- Gateway API path returns 503;
- frontend route remains 200.

Diagnosis: the Service selector does not match API Pod labels. Envoy has no
upstream endpoints.

Why restart does not help: Deployment replacement Pods retain the same correct
labels, while the wrong desired selector remains stored on the Service.

### Failure B: NetworkPolicy denial

Observed:

- Service DNS resolves;
- EndpointSlice contains ready addresses;
- frontend Pod to API times out;
- browser to API through Envoy succeeds.

Diagnosis: the policy graph allows Envoy as the API source but intentionally
does not allow frontend Pods.

### Failure C: wrong HTTPRoute backend port

Observed:

- Service exists;
- HTTPRoute can report an invalid or unresolved backend reference;
- the Pod port may look correct in the Deployment.

Diagnosis: HTTPRoute must reference the Service port, not the container port.
For frontend that is Service port 80, not Pod port 8080.

### Failure D: invalid generated-Service patch

Observed:

- Envoy proxy Deployment may be generated;
- Gateway remains `Programmed=False` with no assigned address;
- generated NodePort Service is absent;
- controller log reports a strategic-merge error.

Diagnosis: Kubernetes strategically merges Service `ports` using `port` as
the list merge key. The patch entry must include `port: 80` as well as the
generated name and desired NodePort.

### Failure E: overlapping Pod and node networks

Observed:

- nodes or some Pods may become Ready;
- direct connectivity can partially work;
- CoreDNS cannot reach the Kubernetes API;
- Service DNS fails broadly.

Diagnosis: routing ambiguity caused by overlapping CIDRs. Choose a
non-overlapping Pod CIDR and recreate the disposable cluster.

## 17. What each common command proves

| Command | Evidence provided |
|---|---|
| `kubectl get nodes -o wide` | node readiness, node IPs, runtime |
| `kubectl get pods -o wide --show-labels` | Pod readiness, IP, node, labels |
| `kubectl get service -o yaml` | stable IP, selectors, ports |
| `kubectl get endpointslices` | selected ready backend addresses |
| `getent hosts <service>` | DNS resolution from that Pod |
| `wget` or `curl` from a Pod | application-layer connectivity from that identity |
| `kubectl get networkpolicies` | policy objects exist, not that they enforce |
| controlled denied request | active CNI enforcement and selector correctness |
| `kubectl describe gateway` | listener and programming conditions |
| `kubectl describe httproute` | attachment, references, backend conditions |
| `kubectl diff -k ...` | live declared resources match rendered Git state |

Evidence is viewpoint-specific. A successful request from your Mac does not
prove the same request is allowed from a frontend Pod.

## 18. What to memorize and what to derive

Memorize these small anchors:

- DNS answers names; it does not test health.
- Service is stable identity; EndpointSlice is the changing backend list.
- kube-proxy implements Service and NodePort forwarding.
- CNI provides Pod networking; policy enforcement depends on the CNI.
- Gateway API chooses HTTP destinations; NetworkPolicy allows transport flows.
- HTTPRoute uses Service ports; NetworkPolicy uses destination Pod ports.
- `namespaceSelector` plus `podSelector` in one peer means AND.
- `Running` is not evidence that every networking boundary works.

Derive everything else by drawing:

```text
source -> name -> entry port -> route -> Service -> endpoints -> policy -> Pod
```

For each arrow, ask which object owns it and which command proves it.

## 19. Review exercises

Try answering without reading the solutions.

1. DNS returns the API ClusterIP, but the request times out. Name three
   boundaries that can still be broken.
2. API Pods are Ready, but the EndpointSlice is empty. What should you compare?
3. Why does the HTTPRoute use frontend port 80 while NetworkPolicy uses 8080?
4. Why can the browser call API while the frontend Pod cannot?
5. What changes when `externalTrafficPolicy` changes from `Cluster` to `Local`?
6. Why is a stored NetworkPolicy object insufficient evidence?
7. Which condition proves a Gateway data plane is ready?
8. Why does `/api` beat `/` for `/api/v1/visits`?
9. Why can `ResolvedRefs=True` coexist with a 503?
10. Why does restarting API Pods not repair a broken Service selector?

### Short answers

1. Endpoint selection, NetworkPolicy, target port, kube-proxy, or application
   availability can still fail.
2. Compare the Service selector with Pod labels, namespace, and readiness.
3. Route references the Service-facing port; policy permits the translated Pod
   destination port.
4. JavaScript executes in the browser and enters through Envoy; nginx does not
   initiate the API call.
5. `Local` uses only endpoints on the receiving node; `Cluster` can forward to
   ready endpoints on other nodes.
6. The active CNI may not enforce it, or its selectors may match nothing.
7. `Programmed=True`, together with an available generated proxy.
8. Longest matching path prefix wins.
9. The Service reference can be valid while it has no ready endpoints.
10. The wrong selector belongs to the Service, not the Pods.

## 20. Production perspective

The theory remains useful in production, but several implementations change:

- kind host mapping becomes a managed or bare-metal load balancer;
- `.localhost` becomes real DNS;
- HTTP becomes HTTPS with certificate lifecycle and TLS policy;
- single replicas become highly available controllers and data planes;
- node placement spans real failure domains;
- CNI selection and upgrades follow platform ownership;
- NetworkPolicy gains continuous conformance tests and observability;
- sensitive east-west traffic may add workload identity and mTLS;
- Redis becomes authenticated, persistent, backed up, and highly available.

The same troubleshooting principle still applies: start at the client and
follow the packet through one owned boundary at a time.

## 21. References

- [Phase 5 implementation guide](05-networking-and-gateway-api.md)
- [Phase 5 evidence](05-networking-and-gateway-api-evidence.md)
- [Calico decision record](../decisions/0001-calico-for-kind-network-policy.md)
- [Kubernetes Services](https://kubernetes.io/docs/concepts/services-networking/service/)
- [Kubernetes DNS](https://kubernetes.io/docs/concepts/services-networking/dns-pod-service/)
- [Kubernetes NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [Gateway API overview](https://gateway-api.sigs.k8s.io/concepts/api-overview/)
- [Envoy Gateway documentation](https://gateway.envoyproxy.io/v1.9/)
