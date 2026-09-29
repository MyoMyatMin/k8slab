# Phase 0 — Project Orientation and Learning Workflow

> Status: Complete  
> Completed by learner: 2026-09-29  
> Last validated: 2026-09-29  
> Validated versions: Not applicable; this phase installs no software

## 1. Why this phase matters

This project contains many tools, but installing tools is not the main objective. The objective is to understand how a Kubernetes platform behaves, how to prove that it is healthy, and how to reason about it when it fails.

This phase establishes the working method used throughout the project. You will learn how to navigate the documentation, read the architecture, keep Git as the source of truth, collect evidence, investigate failures, and decide when a phase is genuinely complete.

Do not install Kubernetes components during this phase. Phase 1 owns workstation setup and version selection.

## 2. Learning objectives

By the end of this phase, you can:

- explain the platform's delivery, runtime, telemetry, and recovery paths;
- identify which repository directory owns each kind of artifact;
- distinguish desired state, live state, observed state, and learning evidence;
- use the project's predict-build-verify-break-recover-explain learning loop;
- distinguish a symptom from a cause and a hypothesis from evidence;
- describe the safety checks required before a destructive experiment;
- determine whether a phase has passed its gate;
- explain when the canonical specification or an ADR must change.

## 3. Read the project contract

Before continuing, read [the canonical project specification](../kubernetes-reliability-platform.md) once from beginning to end.

Do not try to memorize every tool. Concentrate on these questions:

1. What is the final operational story?
2. Which system owns desired state?
3. How does a source-code change reach Kubernetes?
4. Which signals help diagnose a failure?
5. What proves that recovery is complete?
6. Which rules must remain true across every phase?

If this guide and the canonical specification disagree, stop and use the canonical specification. Correct this guide before proceeding.

## 4. Core mental models

### 4.1 Four kinds of state

You will work with four related kinds of state:

| State | Meaning | Example |
|---|---|---|
| Desired state | What Git says should exist | A Deployment declares three replicas |
| Live state | What the Kubernetes API currently stores | The Deployment currently requests three replicas |
| Observed state | What controllers and telemetry report is actually happening | Only two Pods are ready and error rate is rising |
| Learning evidence | What you preserve to demonstrate and explain the behavior | Events, queries, test output, timeline, and conclusion |

These states can disagree. That disagreement is often the beginning of an investigation.

For example, Git and the Kubernetes API may both request three replicas while only two Pods are ready. GitOps has succeeded in reconciling configuration, but the service is not healthy. Argo CD alone cannot answer why; you must inspect Kubernetes state and telemetry.

### 4.2 Reconciliation instead of one-time execution

Kubernetes and Argo CD are controller-based systems. A controller repeatedly compares desired state with observed state and takes action to reduce the difference.

Think in this form:

```text
desired state - observed state = work for a controller
```

When something changes unexpectedly, ask:

1. Which controller owns this resource?
2. What desired state is that controller reading?
3. What does it currently observe?
4. What action is it attempting?
5. What condition prevents convergence?

### 4.3 Signals have different strengths

The platform uses several evidence sources:

| Signal | Best at answering | Important limitation |
|---|---|---|
| Metrics | How much, how often, and when did behavior change? | Usually lack per-request detail |
| Logs | What did a component report about a particular event? | Can be incomplete, noisy, or misleading |
| Traces | Where did one request spend time or fail? | Sampling may omit requests |
| Kubernetes status | What state do API objects and controllers report? | Status alone may not show user impact |
| Events | What recent actions or failures did Kubernetes report? | Retention is short and repetition may be aggregated |
| Tests/probes | Does one explicit expectation pass now? | Covers only what the check was designed to test |

Strong diagnoses combine signals instead of trusting one screen or message.

### 4.4 Symptoms, causes, hypotheses, and evidence

- A **symptom** is observable behavior: requests return HTTP 503.
- A **cause** is the mechanism producing the symptom: the Service has no ready endpoints.
- A **hypothesis** is a testable explanation: the readiness probe path is incorrect.
- **Evidence** is an observation that supports or weakens a hypothesis: every Pod readiness probe returns HTTP 404.
- A **fix** changes the system so the cause no longer produces the symptom.
- **Recovery verification** proves the system and user experience returned to the expected state.

Do not call the first plausible explanation the root cause. Gather enough evidence to distinguish it from alternatives.

## 5. Understand the four platform paths

### 5.1 Delivery path

```text
source change
    -> automated tests
    -> container build and scan
    -> immutable registry image
    -> reviewed GitOps change
    -> Argo CD reconciliation
    -> Kubernetes rollout
```

Key rule: CI creates and publishes artifacts, but it does not directly deploy them to the cluster.

### 5.2 Runtime path

```text
client or k6
    -> Envoy Gateway
    -> frontend
    -> API
    -> Redis
```

Each boundary creates distinct failure possibilities. A successful Pod does not prove that the Gateway route, Service selection, API dependency, or user request works.

### 5.3 Telemetry path

```text
application and cluster
    -> Prometheus metrics
    -> Loki logs through Grafana Alloy
    -> Tempo traces through OpenTelemetry
    -> Grafana exploration and dashboards
    -> Alertmanager notifications
```

Telemetry is part of the platform, not an afterthought. A component is not operationally complete until its important behavior can be observed.

### 5.4 Recovery path

```text
detect
    -> triage
    -> collect evidence
    -> form and test hypotheses
    -> mitigate if necessary
    -> correct desired state in Git
    -> let Argo CD reconcile
    -> verify recovery
    -> record learning
```

Recovery is not complete when a Pod becomes `Running`. You must verify the user-facing check, relevant telemetry, alert resolution, and later the applicable SLO.

## 6. Repository ownership exercise

Without looking at the answer table first, decide where each artifact belongs:

1. FastAPI source code
2. kind cluster configuration
3. Argo CD `Application`
4. Grafana dashboard JSON
5. HTTP load-test script
6. CrashLoopBackOff injection manifest
7. High-error-rate response procedure
8. Explanation for changing from one gateway implementation to another
9. API Deployment base manifest
10. Phase 7 teaching instructions

<details>
<summary>Check your answers</summary>

| Artifact | Owner |
|---|---|
| FastAPI source code | `app/api/` |
| kind cluster configuration | `cluster/kind/` |
| Argo CD `Application` | `gitops/applications/` |
| Grafana dashboard JSON | `observability/dashboards/` |
| HTTP load-test script | `load-tests/` |
| CrashLoopBackOff injection manifest | `incidents/scenarios/` |
| High-error-rate response procedure | `runbooks/` |
| Gateway implementation decision | `decisions/` |
| API Deployment base manifest | `kubernetes/base/` |
| Phase 7 teaching instructions | `docs/07-metrics-and-dashboards.md` |

</details>

If an artifact appears to belong in two places, choose one authoritative owner and generate or reference it elsewhere. Avoid maintaining two independent copies.

## 7. The learning loop

Use this procedure in every technical phase.

### Step 1 — Learn

Read the concepts and primary documentation. Write down unfamiliar terms. Do not begin with commands whose effects you cannot describe.

### Step 2 — Predict

Before running an action, state what you expect to change and what should remain unchanged.

Example:

```text
Action: delete one Pod owned by a three-replica Deployment.
Prediction: the Deployment controller creates a replacement; desired replicas remain three;
one Pod name changes; brief availability impact should be absent if readiness works.
```

### Step 3 — Build

Make the smallest meaningful change. Keep unrelated changes separate so cause and effect remain understandable.

### Step 4 — Verify

Use an explicit check. Prefer machine-verifiable evidence such as a test, condition, query, or request over visual confidence.

### Step 5 — Break safely

Introduce one controlled failure with a known scope, hypothesis, abort condition, and recovery method.

### Step 6 — Diagnose and recover

Investigate before reading the solution. Recover through the intended control path—normally Git after the GitOps phase.

### Step 7 — Explain

Describe what happened in your own words. If you cannot explain why the system behaved that way, the exercise is not finished.

## 8. Evidence workflow

For each phase, keep a short learning record. It may initially be outside Git while it contains raw output, but sanitized, durable learning should be committed with the relevant documentation or incident evidence.

Use this structure:

```markdown
# Phase NN learning record

## Prediction

## Changes made

## Verification performed

## Failure tested

## Evidence and observations

## Explanation in my own words

## Questions or gaps

## Gate result

Not attempted / Passed / Needs more work
```

Evidence rules:

- Never record tokens, passwords, private keys, unredacted credentials, or sensitive environment values.
- Record the command or query that produced an observation.
- Preserve timestamps for incident evidence.
- Prefer relevant excerpts over entire noisy outputs.
- State what an observation proves and what it does not prove.
- Record failed attempts when they teach something useful.

## 9. Investigation workflow

When a failure is not immediately understood, use the following loop:

1. State the user-visible or platform-visible symptom precisely.
2. Establish the time window and recent changes.
3. Check scope: one request, one Pod, one service, one node, or the cluster.
4. Gather current Kubernetes state and events.
5. Check relevant metrics, logs, and traces.
6. List multiple plausible hypotheses.
7. For each hypothesis, identify an observation that would support or contradict it.
8. Run the least invasive test first.
9. Mitigate urgent impact without destroying evidence.
10. Correct the authoritative desired state.
11. Verify recovery through every affected layer.
12. Record the timeline and learning.

Avoid random changes. Changing several variables at once makes it difficult to know which hypothesis was correct.

## 10. Safety protocol for experiments

Before an experiment that deletes, stresses, blocks, or corrupts a lab resource, write down:

```text
Target:
Expected blast radius:
Steady-state check:
Hypothesis:
Signals to watch:
Abort conditions:
Recovery action:
Recovery verification:
```

Always confirm the active Kubernetes context and namespace immediately before a destructive command. Commands in this project must target named resources or the named lab cluster. Do not use broad deletion commands or unresolved shell variables.

Do not run chaos experiments against systems outside this project's lab environment.

## 11. Controlled reasoning exercise

This is a paper exercise; do not run any commands.

### Scenario

After a release:

- Argo CD reports `Synced`.
- The Deployment requests three replicas.
- All three Pods show `Running`.
- The Gateway returns HTTP 503.
- The Service has zero ready endpoints.
- Pod readiness probes are returning HTTP 404.

### Your task

Before opening the answer, write:

1. the user-visible symptom;
2. the strongest current evidence;
3. two plausible hypotheses;
4. the next least-invasive check;
5. why `Synced` and `Running` do not prove service health;
6. what you would verify after correcting the problem.

<details>
<summary>Suggested reasoning</summary>

The symptom is HTTP 503 at the Gateway. The strongest evidence is that the Service has no ready endpoints while readiness probes return 404. One likely hypothesis is that the configured readiness path does not exist in the new image. Another is that routing or middleware inside the application changed the probe path. Inspect the Deployment's readiness configuration and query that exact path directly on a Pod before changing anything.

Argo CD's `Synced` status means live configuration matches Git; it does not mean the desired configuration is correct. `Running` describes the container process state, not readiness to receive traffic. After correcting Git and allowing reconciliation, verify ready endpoints, a successful external request, normal error metrics, resolved alerts, and stable rollout health.

</details>

## 12. Troubleshooting this learning process

| Symptom | Likely problem | Corrective action |
|---|---|---|
| You can run commands but cannot explain them | Moving too quickly through implementation | Return to concepts; annotate each command's input, effect, and verification |
| Everything appears healthy but the gate is unclear | Verification criteria were not made explicit | Rewrite the gate as observable pass/fail checks before continuing |
| Troubleshooting becomes random | No ranked hypotheses or controlled tests | Stop changing the system; write three hypotheses and one falsifying test for each |
| Notes contain huge command dumps | Evidence was collected without a question | Keep only relevant excerpts and explain what each supports |
| Git and the cluster disagree after a manual fix | Desired state was not corrected | Put the correction in Git and let Argo CD reconcile it |
| A guide contradicts the working platform | Documentation drift | Check the canonical specification and pinned versions, then correct the guide |
| A tool choice no longer fits the architecture | A consequential decision changed | Write an ADR and update the specification plus every affected guide |

## 13. Lab choices versus production choices

This project intentionally runs a complex platform on a local cluster. That makes experiments affordable and repeatable, but it changes the meaning of several results:

- Multiple kind workers are containers on one physical machine, not independent failure domains.
- Local persistence does not prove disaster recovery or durable cloud storage.
- A single monitoring stack cannot demonstrate production high availability.
- Local hostnames and certificates do not represent public DNS and production PKI.
- Resource measurements on a laptop are affected by other host workloads.
- Local notification receivers do not prove organizational on-call readiness.

The lab still teaches the mechanisms. Each later guide must explain which conclusions transfer to production and which do not.

## 14. Cleanup or rollback

This phase creates no cluster, application, or external resource, so there is nothing operational to remove.

If you created a learning record containing sensitive information, remove the sensitive values before committing it. Deleting the visible text after it has entered Git history is not sufficient; prevention is the rule.

## 15. Phase gate

Complete this checklist yourself:

- [ ] I read the canonical specification from beginning to end.
- [ ] I can explain the delivery path without looking at its diagram.
- [ ] I can explain the runtime and telemetry paths.
- [ ] I can explain why `Synced`, `Running`, and `Healthy` answer different questions.
- [ ] I can place each repository-ownership exercise artifact correctly.
- [ ] I can distinguish symptoms, hypotheses, evidence, causes, fixes, and recovery checks.
- [ ] I completed the controlled reasoning exercise before reading its answer.
- [ ] I can state the safety information required before a destructive experiment.
- [ ] I understand that a phase is complete only when its gate passes.
- [ ] I have recorded any unanswered questions for Phase 1.

When every item is true, change this guide's status from `Draft` to `Complete` and change Phase 0 in the canonical documentation map from `Draft` to `Complete`.

## 16. Review questions

Answer these without copying sentences from this guide:

1. Why can Argo CD report `Synced` while users still receive errors?
2. What is the difference between desired, live, and observed state?
3. Which evidence would you use to distinguish an application error from a Service-routing error?
4. Why should you predict an experiment's result before performing it?
5. What makes a failure experiment safe and useful?
6. When should an architecture decision be recorded in an ADR?
7. What must be checked before declaring an incident recovered?
8. Which limitations prevent this local lab from proving production-grade availability?

## 17. Further study

These references are optional during Phase 0. Use them when you want deeper background:

- Kubernetes concepts: <https://kubernetes.io/docs/concepts/>
- Kubernetes controllers: <https://kubernetes.io/docs/concepts/architecture/controller/>
- Argo CD core concepts: <https://argo-cd.readthedocs.io/en/stable/core_concepts/>
- Google SRE incident response: <https://sre.google/workbook/incident-response/>
- Architecture Decision Records: <https://adr.github.io/>

## 18. Next phase

After passing the gate, continue to `docs/01-prerequisites-and-tooling.md`.

Phase 1 will inspect the workstation, select and pin compatible versions, establish Kubernetes context-safety conventions, and install or verify the required command-line tools. Do not improvise installation commands before that guide is written and reviewed.
