# Kubernetes Reliability Platform

> Canonical project specification and learning roadmap

## Document status

| Field | Value |
|---|---|
| Role | Single source of truth for the project |
| Status | Active |
| Audience | A learner building the platform hands-on |
| Scope | Local Kubernetes, GitOps, observability, incident response, SRE, security, and chaos engineering |
| Detailed instructions | Stored in the phase guides listed in this document |

This file defines the project's purpose, architecture, required capabilities, technical defaults, learning sequence, and completion criteria. If a phase guide conflicts with this file, this file wins. A deliberate architecture change must update this file and be recorded in an Architecture Decision Record (ADR).

This file is not a command-by-command tutorial. Detailed explanations, exercises, commands, expected results, troubleshooting advice, and review questions belong in the corresponding guide under `docs/`.

---

## 1. Project mission

Build a reproducible Kubernetes reliability platform and use it to learn by doing.

The learner will deploy a small application through GitOps, observe it through metrics, logs, and traces, deliberately introduce failures, respond to alerts, recover through Git, and verify recovery against defined service-level objectives.

The primary deliverable is the operational platform and the learner's demonstrated understanding of it. The demo application exists to produce realistic behavior and telemetry; application feature development is not the focus.

### Learning method

Every phase follows the same loop:

```text
Learn the concept
      |
      v
Predict the behavior
      |
      v
Build it yourself
      |
      v
Verify the result
      |
      v
Break it safely
      |
      v
Diagnose and recover
      |
      v
Explain what happened
```

Copying commands without understanding their purpose does not complete a phase. A phase is complete only after its verification gate passes and the learner can answer its review questions in their own words.

---

## 2. Project outcomes

After completing the project, the learner should be able to:

- explain how Kubernetes schedules, runs, exposes, scales, and replaces workloads;
- package an application as a container and publish immutable images;
- use Git as the source of truth for cluster state;
- operate Argo CD and diagnose synchronization or health failures;
- collect and query Kubernetes and application metrics;
- centralize and query structured container logs;
- trace a request across application dependencies;
- create actionable dashboards and alerts;
- configure probes, resource policies, disruption protection, and autoscaling;
- define SLIs, SLOs, and error budgets from real telemetry;
- investigate incidents using symptoms, evidence, hypotheses, and tests;
- recover from failed releases through Git rather than untracked live changes;
- run controlled load and chaos experiments safely;
- document decisions, incidents, and repeatable operational procedures;
- distinguish lab-friendly decisions from production-ready designs.

---

## 3. Scope

The full learning scope is intentionally broad. Complexity is controlled through sequencing and phase gates, not by removing major topics.

### Required capabilities

1. Local multi-node Kubernetes cluster
2. Containerized demo application
3. Kubernetes workload and network configuration
4. Continuous integration and immutable container images
5. GitOps delivery with Argo CD
6. Metrics with Prometheus
7. Dashboards with Grafana
8. Logs with Loki and Grafana Alloy
9. Alerts with Alertmanager
10. Resource management and Horizontal Pod Autoscaling
11. Reliability controls and controlled failure scenarios
12. Incident runbooks and post-incident reviews
13. SLIs, SLOs, and error budgets
14. Distributed tracing with OpenTelemetry and Tempo
15. Git-safe secret management
16. Network policy and RBAC exercises
17. Load testing with k6
18. Chaos engineering
19. A reproducible final demonstration

### Non-goals

- Building a feature-rich product
- Operating a production cloud environment
- Achieving production-grade high availability on one laptop
- Hiding complexity behind a single installation script
- Treating dashboard screenshots as proof without reproducible verification
- Committing plaintext credentials or private keys

Cloud deployment, multi-cluster operation, service mesh, policy engines, progressive delivery, and long-term telemetry storage may be later extensions. They are not required for the first complete learning path.

---

## 4. Canonical technical decisions

These are the default project choices. A phase guide may explain alternatives, but it must implement these choices unless an accepted ADR changes them.

| Area | Canonical choice | Reason for this project |
|---|---|---|
| Local cluster | `kind`, with multiple worker nodes | Reproducible, disposable, scriptable, and suitable for scheduling/failure exercises |
| Local container environment | OrbStack using its Docker-compatible engine | Selected workstation runtime; kind uses this engine to run Kubernetes node containers |
| Application | Static frontend, Python FastAPI API, and Redis | Small system with HTTP, dependency, state, metrics, logs, and useful failure modes |
| External traffic | Kubernetes Gateway API with Envoy Gateway | Teaches the current Kubernetes routing model without tying manifests to legacy Ingress APIs |
| App manifests | Kustomize bases and overlays | Keeps Kubernetes YAML visible while teaching reusable environment configuration |
| Platform packages | Helm, declared through GitOps | Uses upstream packaging while retaining declarative desired state |
| CI | GitHub Actions | Builds, tests, scans, and publishes images |
| Registry | GitHub Container Registry (GHCR) | Integrates with the selected CI and supports immutable digests |
| Continuous delivery | Argo CD | Reconciliation, drift detection, health reporting, and Git-based recovery |
| Metrics | Prometheus Operator through `kube-prometheus-stack` | Kubernetes-native monitoring resources and a complete local monitoring baseline |
| Visualization | Grafana | Dashboards and exploration for metrics, logs, and traces |
| Log storage | Loki in a lab-sized deployment mode | Central log querying with manageable local requirements |
| Telemetry collector | Grafana Alloy | Collects Kubernetes logs and can participate in OpenTelemetry pipelines; Promtail is not used |
| Tracing | OpenTelemetry instrumentation and Tempo | Vendor-neutral instrumentation with Grafana correlation |
| Alerting | Prometheus rules and Alertmanager | Declarative alert evaluation, routing, grouping, and inhibition |
| Load generation | k6 | Scriptable HTTP load and threshold checks |
| Secret management | SOPS with `age`; decryption integrated with GitOps | Encrypted values may live in Git while private key material does not |
| Chaos | Native Kubernetes experiments first, then Chaos Mesh | Builds understanding before introducing a chaos framework |
| Source control layout | One learning repository with strict directory boundaries | Keeps the course reproducible; the GitOps subtree can later be split into a dedicated repository |

### Version policy

- Exact tool, chart, image, and Kubernetes versions must be pinned in executable configuration, not described only as `latest` in prose.
- `docs/01-prerequisites-and-tooling.md` owns the human-readable compatibility matrix.
- Dependency update commits must be isolated and must rerun the affected verification gates.
- Major-version upgrades require an ADR when they alter architecture, APIs, or learning instructions.
- Phase guides must state the versions on which their commands were last verified.

---

## 5. System architecture

### Delivery path

```text
Developer
    |
    v
Application source in Git
    |
    v
GitHub Actions: test -> build -> scan -> publish
    |
    v
Immutable image in GHCR
    |
    v
GitOps image reference updated by pull request
    |
    v
Argo CD detects desired-state change
    |
    v
Kubernetes rollout
```

CI does not deploy directly with `kubectl`, and it does not require administrative access to the cluster. Argo CD performs deployment by reconciling Git with the cluster.

### Runtime and telemetry path

```text
                         k6 / Browser
                              |
                              v
                    Gateway API / Envoy
                              |
                              v
                         Frontend
                              |
                              v
                         FastAPI API
                              |
                              v
                            Redis

  Application and cluster
       |        |        |
       |        |        +------ traces ------+
       |        +--------------- logs -------+|
       +------------------------ metrics ----+||
                                               ||
       Prometheus <--- ServiceMonitor          ||
       Loki       <--- Grafana Alloy <---------+|
       Tempo      <--- OpenTelemetry / Alloy <--+
              \          |          /
               \         |         /
                        Grafana
                           |
                    dashboards/explore
                           |
             alert rules -> Alertmanager
```

### Recovery path

```text
Alert or failed health check
           |
           v
Triage dashboards and Kubernetes state
           |
           v
Correlate metrics, logs, traces, and events
           |
           v
Form and test a root-cause hypothesis
           |
           v
Change reviewed in Git
           |
           v
Argo CD reconciles the fix
           |
           v
Verify health, alert resolution, and SLO recovery
```

Emergency live changes may be demonstrated during an incident exercise, but they must be documented and reconciled back into Git. An unexplained live-only fix is configuration drift, not task completion.

---

## 6. Project invariants

The following rules apply throughout the project:

1. Git is the authoritative desired state after the GitOps phase begins.
2. No plaintext secret, private key, access token, or real credential is committed.
3. Deployed application images use immutable versions or digests, never `latest`.
4. Kubernetes resources use consistent labels and explicit namespaces.
5. Workloads define resource requests and limits unless a guide explicitly demonstrates their absence.
6. Application logs are structured and written to standard output/error.
7. Dashboards, alert rules, data sources, and important queries are stored as code.
8. Every alert links to, or clearly names, a matching runbook.
9. Every incident exercise has an injection method, expected signal, recovery method, and success check.
10. Destructive experiments run only in the lab environment and include a rollback or reset procedure.
11. A green UI is not sufficient evidence; verification includes commands, queries, or automated checks.
12. Manual installation steps are documented, and repeated actions become scripts or declarative configuration.
13. Each guide distinguishes a learning shortcut from a production recommendation.

---

## 7. Repository contract

The target repository layout is:

```text
k8slab/
├── kubernetes-reliability-platform.md   # this canonical specification
├── README.md                            # short entry point linking here
├── versions.env                         # pinned workstation and cluster tool baseline
├── app/
│   ├── frontend/
│   └── api/
├── cluster/
│   ├── kind/
│   └── bootstrap/
├── kubernetes/
│   ├── base/
│   ├── overlays/
│   │   └── local/
│   └── policies/
├── gitops/
│   ├── bootstrap/
│   ├── applications/
│   └── platform/
├── observability/
│   ├── dashboards/
│   ├── alerts/
│   ├── alloy/
│   ├── loki/
│   └── tempo/
├── load-tests/
├── incidents/
│   ├── scenarios/
│   └── evidence/
├── runbooks/
├── docs/
│   ├── guide-template.md
│   └── 01-... through 16-...
├── decisions/
├── scripts/
└── Makefile
```

Directory ownership is intentional:

- `app/` owns application source and application-level tests.
- `cluster/` owns local cluster creation and the minimum bootstrap required before GitOps can take control.
- `kubernetes/` owns application Kubernetes resources.
- `gitops/` owns Argo CD applications and platform desired state.
- `observability/` owns dashboards, alerts, and telemetry configuration.
- `incidents/` owns failure injection and captured learning evidence.
- `runbooks/` owns operational response procedures.
- `docs/` owns the guided curriculum.
- `decisions/` owns ADRs explaining consequential architecture changes.
- `scripts/` and the `Makefile` provide repeatable helpers; they must not conceal the concepts taught by the guides.

---

## 8. Learning roadmap and phase gates

Phases are completed in order. A guide is not considered validated until its gate can be reproduced from a clean-enough starting state.

### Phase dependency map

```text
0 Orientation
    |
1 Tooling
    |
2 Application -> 3 Containers and CI -> 4 Kubernetes -> 5 Networking -> 6 GitOps
                                                               |
                              +--------------------------------+------------------+
                              |                                |                  |
                              v                                v                  v
                        7 Metrics                         8 Logging          10 Resilience
                              |                                |                  |
                              +---------------+----------------+------------------+
                                              |
                                              v
                                         9 Alerting
                                              |
                                              v
                                      11 Incident lab
                                        /      |      \
                                       v       v       v
                                  12 SLOs  13 Tracing  14 Security
                                        \      |      /
                                         \     |     /
                                          v    v    v
                                           15 Chaos
                                              |
                                              v
                                        16 Final demo
```

The numbered order is the teaching order. The branches show conceptual dependencies, not permission to skip earlier phase gates.

### Phase 0 — Orientation and learning workflow

**Guide:** `docs/00-project-guide.md`

**Learn:** architecture, repository conventions, evidence collection, safe experimentation, and how to use the guides.

**Gate:** Explain the delivery, telemetry, and recovery paths without reading the diagrams; identify where every planned artifact belongs.

### Phase 1 — Prerequisites and tooling

**Guide:** `docs/01-prerequisites-and-tooling.md`

**Learn:** containers, Kubernetes control-plane basics, local resource planning, CLI context safety, and version pinning.

**Deliver:** verified Docker, `kubectl`, kind, Helm, Kustomize, Git, SOPS, `age`, and k6 installations.

**Gate:** Run the environment verification script successfully and prove that commands target only the lab context.

### Phase 2 — Demo application and instrumentation

**Guide:** `docs/02-demo-application.md`

**Learn:** service boundaries, health endpoints, structured logging, RED metrics, graceful shutdown, and basic OpenTelemetry instrumentation.

**Deliver:** frontend, API, Redis dependency, unit tests, health/readiness endpoints, `/metrics`, structured logs, and trace propagation.

**Gate:** Run locally, exercise success and failure paths, and demonstrate metrics, logs, and traces produced by a request.

### Phase 3 — Containers and continuous integration

**Guide:** `docs/03-containers-and-ci.md`

**Learn:** image layers, multi-stage builds, non-root execution, tags versus digests, CI permissions, caching, and vulnerability scanning.

**Deliver:** Dockerfiles, local image tests, GitHub Actions workflow, image scan, Software Bill of Materials where supported, and GHCR publication.

**Gate:** A clean commit produces a tested image, the container runs as non-root, and the published digest is recorded.

### Phase 4 — Kubernetes foundation

**Guide:** `docs/04-kubernetes-foundation.md`

**Learn:** kind topology, nodes, namespaces, Deployments, Services, ConfigMaps, Secrets, probes, resources, scheduling, and events.

**Deliver:** reproducible multi-node cluster plus Kustomize base and local overlay for the application.

**Gate:** Recreate the cluster, deploy the application, reach it from the host, delete a Pod, and explain its replacement.

### Phase 5 — Networking and traffic management

**Guide:** `docs/05-networking-and-gateway-api.md`

**Learn:** cluster DNS, Services, endpoint selection, GatewayClass, Gateway, HTTPRoute, network policies, and common connectivity failures.

**Deliver:** Envoy Gateway, HTTP routing, local hostname, and default-deny policies with explicit required flows.

**Gate:** Reach the application through the Gateway, prove an unauthorized path is blocked, and diagnose a broken Service selector.

### Phase 6 — GitOps with Argo CD

**Guide:** `docs/06-gitops-with-argocd.md`

**Learn:** desired versus live state, reconciliation, bootstrap boundaries, sync policies, pruning, self-healing, health, history, and rollback through Git.

**Deliver:** declarative Argo CD installation/bootstrap, projects/applications, automated sync, and documented recovery workflow.

**Gate:** Deploy a Git change, create safe manual drift, observe `OutOfSync`, and demonstrate automatic restoration from Git.

### Phase 7 — Metrics and dashboards

**Guide:** `docs/07-metrics-and-dashboards.md`

**Learn:** time series, labels, cardinality, exporters, ServiceMonitor, PromQL, golden signals, and dashboard design.

**Deliver:** kube-prometheus-stack, application scraping, cluster/application dashboards, and queries stored as code.

**Gate:** Use PromQL and dashboards to explain request rate, error rate, latency, saturation, Pod health, and replica count under load.

### Phase 8 — Centralized logging

**Guide:** `docs/08-logging-with-loki.md`

**Learn:** structured logs, Kubernetes metadata, collection pipelines, Loki labels, cardinality, LogQL, retention, and metric/log correlation.

**Deliver:** Loki, Grafana Alloy log collection, Grafana data source, saved queries, and an application log dashboard.

**Gate:** Find one generated request across replicas using a request ID and diagnose an injected application error from centralized logs.

### Phase 9 — Alerting and notification flow

**Guide:** `docs/09-alerting-with-alertmanager.md`

**Learn:** symptoms versus causes, alert states, `for` duration, routing, grouping, inhibition, severity, labels, annotations, and alert fatigue.

**Deliver:** alerts for availability, high error rate, latency, CPU pressure, memory risk, crash loops, and replica mismatch; each alert maps to a runbook.

**Gate:** Trigger and resolve representative warning and critical alerts, then verify correct labels, annotations, routing, and runbook references.

### Phase 10 — Autoscaling and workload resilience

**Guide:** `docs/10-autoscaling-and-resilience.md`

**Learn:** requests versus limits, CPU throttling, OOM behavior, HPA calculations, stabilization, PodDisruptionBudgets, topology spread, and graceful termination.

**Deliver:** HPA, multiple replicas, disruption budget, topology rules, and tuned resource/probe configuration.

**Gate:** Generate repeatable load, observe scale-up and scale-down, and maintain availability during voluntary disruption within the lab's limits.

### Phase 11 — Incident-response laboratory

**Guide:** `docs/11-incident-response-lab.md`

**Learn:** detection, triage, evidence collection, timelines, hypotheses, mitigation, root cause, recovery verification, and blameless review.

**Deliver:** reproducible scenarios and runbooks for at least:

- CrashLoopBackOff;
- ImagePullBackOff or invalid image;
- failed readiness or liveness probe;
- bad ConfigMap or secret reference;
- CPU saturation;
- memory exhaustion and OOMKilled;
- unschedulable Pod;
- broken Service selector or port;
- denied network flow;
- failed rollout;
- HTTP 5xx spike;
- dependency latency or failure.

**Gate:** Diagnose three scenarios without using their answer sections, recover through Git, and write a short incident review supported by evidence.

### Phase 12 — SLIs, SLOs, and error budgets

**Guide:** `docs/12-slos-and-error-budgets.md`

**Learn:** user journeys, indicators, objectives, windows, error budgets, burn rates, multi-window alerting, and the limits of averages.

**Initial objectives:**

- Availability: 99.9% of eligible requests succeed over the selected window.
- Latency: 95% of eligible requests complete in less than 300 ms.
- Server error rate: fewer than 1% of eligible requests return HTTP 5xx responses.

The guide must define the exact eligible request population, query expressions, measurement windows, and exclusions before these objectives are treated as valid.

**Deliver:** recording rules, SLO dashboard, error-budget visualization, and burn-rate alerts.

**Gate:** Use generated good and bad traffic to show budget consumption and explain when an alert should fire.

### Phase 13 — Distributed tracing

**Guide:** `docs/13-tracing-with-opentelemetry.md`

**Learn:** traces, spans, context propagation, sampling, semantic conventions, baggage risks, instrumentation, and exemplars/correlation.

**Deliver:** OpenTelemetry instrumentation, trace collection, Tempo, Grafana trace exploration, and correlation between trace IDs and logs.

**Gate:** Follow a slow or failed request through the application and dependency, then identify where time or failure originated.

### Phase 14 — Security and hardening

**Guide:** `docs/14-security-and-hardening.md`

**Learn:** least privilege, service accounts, RBAC, Pod security, secret encryption workflow, image scanning, supply-chain risk, and network segmentation.

**Deliver:** SOPS/age workflow, restricted security contexts, namespace-scoped RBAC, network policies, and documented threat assumptions.

**Gate:** Confirm encrypted secrets reconcile correctly, plaintext is absent from Git, the application runs without root privileges, and prohibited permissions/flows fail.

### Phase 15 — Chaos engineering

**Guide:** `docs/15-chaos-engineering.md`

**Learn:** steady state, hypotheses, blast radius, abort conditions, controlled experiments, and the difference between random breakage and chaos engineering.

**Deliver:** native failure experiments followed by Chaos Mesh experiments for Pod loss, CPU stress, memory pressure, network delay, and network loss.

**Gate:** Run an approved experiment, observe expected telemetry and alerts, honor abort conditions, and verify complete recovery.

### Phase 16 — Final demonstration and assessment

**Guide:** `docs/16-final-demonstration.md`

**Learn:** communicating architecture, presenting evidence, operating under failure, and evaluating platform limitations.

**Gate:** Complete the end-to-end demonstration in Section 13 and satisfy the project definition of done.

---

## 9. Guide contract

Every phase guide must use `docs/guide-template.md` and include:

1. Purpose and connection to the overall architecture
2. Learning objectives written as observable abilities
3. Concepts and vocabulary
4. Prerequisites and dependency checks
5. Version and environment assumptions
6. Files that will be created or changed
7. A pre-exercise prediction or design question
8. An explicit exercise mode for each implementation section
9. Guided implementation in small, explained steps
10. Expected results after meaningful steps
11. Verification commands or queries
12. At least one controlled failure or troubleshooting exercise
13. Common failure symptoms and diagnostic reasoning
14. Production considerations and lab-specific shortcuts
15. Cleanup, rollback, or reset procedure
16. Definition-of-done checklist
17. Review questions and further study

Guides should reveal explanations progressively. Exercises should ask the learner to investigate before showing a solution. Commands must be safe to rerun where practical, and destructive commands must name their exact scope.

### Exercise modes

The teaching style depends on whether an artifact is supporting software or a core platform artifact.

**Guided completion — supporting application code**

- Provide enough compilable or nearly compilable structure that Python, JavaScript, or framework syntax is not the main obstacle.
- Leave decision-bearing lines as clearly named `TODO` items for the learner.
- Explain what each `TODO` must achieve without immediately giving its exact answer.
- Follow each small group of `TODO`s with a command, expected result, and common failure note.
- Put progressive hints and an optional reference answer after the attempt, preferably in collapsed sections.
- Require at least one learner-owned change or experiment after the baseline works.

**Challenge-first — DevOps and reliability artifacts**

- State the objective, operational contract, constraints, safety boundaries, and verification evidence.
- Ask the learner to design and implement the artifact before revealing a finished solution.
- Provide progressive hints and diagnostic questions when needed.
- Do not front-load complete Dockerfiles, CI workflows, Kubernetes manifests, GitOps definitions, dashboards, alerts, SLOs, security policy, or chaos experiments unless the phase explicitly treats that artifact as prerequisite boilerplate.
- A reference implementation may be revealed after a genuine attempt or used to compare completed work.

This distinction keeps the demo application approachable without turning the project into an application-development course, while preserving hands-on ownership of the reliability platform.

---

## 10. Documentation map and status

Status values are `Planned`, `Draft`, `Validated`, and `Complete`.

| Phase | Authoritative guide | Status |
|---|---|---|
| 0 | `docs/00-project-guide.md` | Complete |
| 1 | `docs/01-prerequisites-and-tooling.md` | Complete |
| 2 | `docs/02-demo-application.md` | Complete |
| 3 | `docs/03-containers-and-ci.md` | Planned |
| 4 | `docs/04-kubernetes-foundation.md` | Planned |
| 5 | `docs/05-networking-and-gateway-api.md` | Planned |
| 6 | `docs/06-gitops-with-argocd.md` | Planned |
| 7 | `docs/07-metrics-and-dashboards.md` | Planned |
| 8 | `docs/08-logging-with-loki.md` | Planned |
| 9 | `docs/09-alerting-with-alertmanager.md` | Planned |
| 10 | `docs/10-autoscaling-and-resilience.md` | Planned |
| 11 | `docs/11-incident-response-lab.md` | Planned |
| 12 | `docs/12-slos-and-error-budgets.md` | Planned |
| 13 | `docs/13-tracing-with-opentelemetry.md` | Planned |
| 14 | `docs/14-security-and-hardening.md` | Planned |
| 15 | `docs/15-chaos-engineering.md` | Planned |
| 16 | `docs/16-final-demonstration.md` | Planned |

A guide moves to `Validated` only after its instructions succeed against the pinned environment. It moves to `Complete` only after its gate, troubleshooting section, reset path, and review material are present.

---

## 11. Evidence and assessment

Learning evidence should be reproducible and small enough to keep in Git when it contains no secrets or excessive generated data.

Acceptable evidence includes:

- test and verification script output;
- PromQL, LogQL, and trace queries;
- sanitized incident timelines;
- alert state transitions;
- relevant Kubernetes events;
- before/after configuration diffs;
- load-test summaries;
- written answers to review questions;
- short post-incident reviews.

Screenshots may supplement evidence but should not replace the underlying query, command, or configuration.

For each incident, record:

```text
Scenario and hypothesis
Start and end time
User-visible symptom
Detection signal
Timeline
Evidence collected
Root cause
Mitigation
Git-based corrective action
Recovery verification
What would prevent or shorten recurrence
```

---

## 12. Operational success criteria

The completed platform must demonstrate all of the following:

### Deployment

- CI tests and publishes an immutable application image.
- A reviewed Git change updates desired state.
- Argo CD reconciles the change without CI directly deploying to the cluster.
- Drift is detected and safely corrected.
- A failed release can be recovered through a Git change or revert.

### Runtime reliability

- Readiness prevents unready instances from receiving traffic.
- Liveness handles a deliberately unrecoverable process state without masking dependency failure.
- Requests and limits are justified by observations.
- Multiple replicas and a disruption budget reduce voluntary-disruption impact.
- HPA behavior is visible and reproducible under load.

### Observability

- Metrics answer rate, errors, duration, and saturation questions.
- Logs can be searched across replicas with useful Kubernetes context.
- Traces identify a slow or failing request path.
- Grafana correlates telemetry signals where practical.
- Dashboards and alert rules are provisioned from Git.

### Incident response

- Alerts are actionable and map to runbooks.
- Incidents can be reproduced safely.
- Diagnosis uses evidence rather than random configuration changes.
- Recovery is verified at the workload, service, telemetry, alert, and SLO levels.
- Significant exercises produce a short post-incident review.

### Security and reproducibility

- No plaintext secrets or private key material exist in Git history created by the project.
- Workloads run with restricted privileges appropriate to the application.
- Network and RBAC access follow least-privilege exercises.
- A new learner can recreate the documented environment using pinned dependencies and the guides.

---

## 13. Final demonstration

The final demonstration must show one continuous operational story:

1. Explain the architecture and identify Git's authoritative configuration.
2. Push an application change.
3. Show CI test, scan, build, and publish an immutable image.
4. Review and merge the GitOps image update.
5. Show Argo CD reconcile and complete a healthy rollout.
6. Generate controlled traffic with k6.
7. Show request rate, latency, errors, saturation, and replica behavior.
8. Show HPA scaling the application and later stabilizing.
9. Select and announce an incident hypothesis and abort conditions.
10. Introduce the intentional failure.
11. Observe the alert and begin the matching runbook.
12. Correlate Kubernetes state, metrics, logs, events, and traces.
13. State the root cause and supporting evidence.
14. Apply the corrective change through Git.
15. Show Argo CD reconcile the fix.
16. Verify application health and alert resolution.
17. Verify the relevant SLI/SLO view and explain error-budget impact.
18. Summarize the incident timeline, limitations, and next improvement.

The demo is successful only when another person can follow the evidence from change to failure to verified recovery.

---

## 14. Overall definition of done

The project is complete when:

- all required phase guides are marked `Complete`;
- all phase gates pass on the documented environment;
- the repository matches the repository contract or contains an ADR explaining deviations;
- platform configuration, dashboards, alerts, experiments, and runbooks are stored in Git;
- at least three incidents have been completed without consulting their solution sections;
- at least one incident includes metrics, logs, traces, events, an alert, and SLO impact;
- cluster recreation and GitOps recovery have been demonstrated;
- the final demonstration succeeds end to end;
- known limitations and future improvements are documented honestly.

---

## 15. Change control

Use an ADR for a change that affects architecture, core tools, repository boundaries, security posture, or multiple phase guides.

An ADR must record:

- context and problem;
- chosen decision;
- alternatives considered;
- consequences and trade-offs;
- guides and configuration affected;
- migration or rollback plan.

When changing this specification:

1. Update the affected canonical section.
2. Add or update the ADR when required.
3. Update every affected phase guide.
4. Re-run affected phase gates.
5. Update guide status and compatibility information.

This prevents the source of truth from becoming an aspirational document that no longer matches the working platform.

---

## 16. Official reference starting points

Phase guides should link to primary documentation for the versions they use. Starting points include:

- Kubernetes: <https://kubernetes.io/docs/>
- kind: <https://kind.sigs.k8s.io/docs/>
- Gateway API: <https://gateway-api.sigs.k8s.io/>
- Envoy Gateway: <https://gateway.envoyproxy.io/docs/>
- Kustomize: <https://kubectl.docs.kubernetes.io/guides/>
- Helm: <https://helm.sh/docs/>
- Argo CD: <https://argo-cd.readthedocs.io/>
- Prometheus: <https://prometheus.io/docs/>
- Prometheus Operator: <https://prometheus-operator.dev/docs/>
- Grafana: <https://grafana.com/docs/grafana/latest/>
- Loki: <https://grafana.com/docs/loki/latest/>
- Grafana Alloy: <https://grafana.com/docs/alloy/latest/>
- Tempo: <https://grafana.com/docs/tempo/latest/>
- OpenTelemetry: <https://opentelemetry.io/docs/>
- SOPS: <https://getsops.io/>
- k6: <https://grafana.com/docs/k6/latest/>
- Chaos Mesh: <https://chaos-mesh.org/docs/>

Secondary tutorials may provide useful perspectives, but project instructions should be verified against upstream documentation and the pinned lab environment.

---

## 17. Guiding principle

The project is successful when the learner can explain and operate the system—not merely when all components are installed.

The source-of-truth file defines the destination, architecture, sequence, rules, and proof of success. The phase guides teach how to reach that destination through understanding, implementation, experimentation, failure, and recovery.
