# Phase NN — Title

> Status: Draft  
> Last validated: Not yet validated  
> Validated versions: Add versions here

## 1. Why this phase matters

Explain the operational problem this phase solves and how it connects to the platform architecture.

## 2. Learning objectives

By the end of this phase, the learner can:

- describe an observable ability;
- implement an observable ability;
- diagnose an observable failure.

## 3. Concepts and vocabulary

Explain the minimum theory needed before implementation. Link to primary documentation.

## 4. Prerequisites

- Required completed phases
- Required tools and versions
- Required local resources
- Context and safety checks

## 5. Files created or changed

| Path | Purpose |
|---|---|
| `path/to/file` | Explain ownership and effect |

## 6. Before you build: predict

Ask the learner to predict behavior or make a small design decision before seeing the implementation.

## 7. Guided implementation

Break the work into small sections. For each meaningful step include:

1. the goal;
2. the command or file change;
3. why it works;
4. the expected result;
5. a verification check.

Do not hide essential learning behind an unexplained script.

## 8. Verification

Provide commands, queries, automated tests, and expected observations that prove the phase works.

## 9. Controlled failure exercise

### Hypothesis

State what should happen and which signals should change.

### Safety and abort conditions

State the scope, risks, exact abort conditions, and recovery path.

### Introduce the failure

Give the scoped procedure.

### Investigate

Prompt the learner to inspect evidence before revealing the diagnosis.

<details>
<summary>Diagnosis and explanation</summary>

Place the guided solution here.

</details>

### Recover and verify

Restore desired state and prove recovery through workload state and telemetry.

## 10. Troubleshooting

| Symptom | Evidence to collect | Likely causes | Next test |
|---|---|---|---|
| Example symptom | Example command/query | Avoid assuming one cause | Falsifiable check |

## 11. Production considerations

Explain which choices are lab simplifications and what would change in a production environment.

## 12. Cleanup, rollback, or reset

Provide exact, scoped, and recoverable steps. State what data or state is removed.

## 13. Definition of done

- [ ] Implementation is stored in the correct repository location.
- [ ] Verification checks pass.
- [ ] The controlled failure was diagnosed and recovered.
- [ ] No plaintext secrets or generated sensitive data were committed.
- [ ] Review questions can be answered without copying the guide.

Add phase-specific completion checks.

## 14. Review questions

1. Ask why the mechanism works.
2. Ask how to distinguish two similar failure modes.
3. Ask what evidence proves the system is healthy.
4. Ask what would change in production.

## 15. Further study

Link to primary documentation and clearly label optional extensions.
