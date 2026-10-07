# ADR 0001 — Use Calico for local NetworkPolicy enforcement

> Status: Accepted
> Date: 2026-10-07

## Context

Phase 5 requires a default-deny network posture with explicit application
flows. Kubernetes defines the `NetworkPolicy` API, but enforcement belongs to
the cluster network plugin. The default kind networking implementation,
kindnet, provides Pod networking but does not enforce Kubernetes
`NetworkPolicy` resources.

Applying policies to the Phase 4 cluster without changing its CNI would create
misleading YAML: the API would accept the resources while disallowed traffic
would continue to pass.

## Decision

The local `k8slab` kind cluster will use Calico Open Source as both its CNI and
NetworkPolicy engine.

- kind's default CNI is disabled in the versioned cluster configuration.
- The Pod CIDR is explicitly set to `192.168.0.0/16`.
- Calico is installed at the pinned version in `versions.env` before application
  workloads are restored.
- Application policy remains portable Kubernetes
  `networking.k8s.io/v1` `NetworkPolicy`, not Calico-specific policy.
- Calico installation is a cluster bootstrap concern. Phase 6 may manage its
  lifecycle declaratively, but the CNI must exist before ordinary workloads
  and GitOps controllers can communicate.

## Alternatives considered

### Keep kindnet

Rejected because it would not enforce the phase gate. Accepted policy objects
without changed traffic are not evidence of network isolation.

### Cilium

Cilium is capable and would also satisfy the requirement. It adds a broader
eBPF, observability, and policy surface than this phase needs, which would
distract from learning the portable Kubernetes policy model.

### Calico policy-only mode beside kindnet

Rejected for this lab because two networking components make packet ownership
and troubleshooting less clear. Replacing kindnet gives one explicit CNI and
one policy engine.

## Consequences

- Moving from Phase 4 to Phase 5 requires recreating the disposable kind
  cluster.
- Nodes remain `NotReady` until Calico is installed and healthy.
- NetworkPolicy exercises produce real allow/deny behavior.
- CNI installation adds bootstrap time and resource use.
- Production clusters may use another conformant policy-capable CNI; the
  application policies should remain portable.

## Verification

The decision is working only when:

1. Calico reports Available and all kind nodes are Ready.
2. application traffic explicitly allowed by policy succeeds;
3. an unapproved Pod-to-Service connection times out or is rejected; and
4. deleting the policies restores the default-allow Kubernetes behavior.

## Rollback

Delete only the disposable `k8slab` cluster, remove the Calico-specific kind
networking fields, and recreate the Phase 4 cluster. Do not attempt to replace
the CNI in place on a cluster containing state that must be preserved.
