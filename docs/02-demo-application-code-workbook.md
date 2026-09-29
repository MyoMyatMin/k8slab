# Phase 2 Coding Workbook — Guided Completion

> Companion to: `docs/02-demo-application.md`  
> Exercise mode: Guided completion  
> Scope: Supporting application code only

## How this workbook works

The demo application produces realistic health, dependency, log, metric, and trace signals for the reliability platform. It is not the project's main product.

For each lesson:

1. read the behavior contract;
2. compare the scaffold with your existing file;
3. complete the numbered `TODO`s yourself;
4. run the checkpoint;
5. open progressive hints only if needed;
6. open the reference answers only after an attempt;
7. complete the learner-owned experiment.

Boilerplate is provided. The missing lines express the concept being learned. Do not overwrite working code blindly; compare first with:

```bash
git diff -- app/api app/frontend
```

## Ordered lessons

1. [Application foundations](02a-application-foundations-code-lab.md)
   - Lesson 1: validated configuration
   - Lesson 2: asynchronous Redis boundary
   - Lesson 3: liveness and readiness
2. [Application observability and API assembly](02b-application-observability-code-lab.md)
   - Lesson 4: request IDs and JSON logs
   - Lesson 5: Prometheus metrics
   - Lesson 6: local OpenTelemetry traces
   - Lesson 7: remaining API endpoints
3. [Frontend and tests](02c-frontend-and-tests-code-lab.md)
   - Lesson 8: static frontend
   - Lesson 9: tests with a fake dependency

Finish these lessons before returning to Section 18 of the main Phase 2 guide. The three-terminal verification and Redis failure exercise are the final evidence—not the amount of Python written.
