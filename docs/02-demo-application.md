# Phase 2 — Demo Application and Instrumentation

> Status: Draft  
> Last validated: Not yet validated by the learner  
> Version baseline selected: 2026-09-29 for Python 3.14 and Redis 8.10

## 1. Why this phase matters

Kubernetes, GitOps, dashboards, alerts, and incident exercises all need a workload with behavior worth operating. A static “hello world” can prove that a Pod starts, but it cannot teach dependency health, latency, errors, request correlation, autoscaling signals, or distributed tracing.

In this phase you will build a deliberately small system:

```text
Browser
   |
   v
Static frontend
   |
   v
FastAPI service
   |
   v
Redis
```

The application will expose useful health semantics, structured logs, Prometheus metrics, trace spans, and guarded failure controls. It remains intentionally small because the operational platform—not product features—is the project.

You will run everything locally. Do not create Dockerfiles, Kubernetes resources, or CI workflows yet.

## 2. Learning objectives

By the end of this phase, you can:

- explain the difference between liveness and readiness;
- design an API whose dependency failures are observable;
- use configuration instead of hard-coded environment assumptions;
- produce structured logs with request and trace correlation fields;
- instrument HTTP behavior using request rate, errors, and duration;
- avoid unbounded metric-label cardinality;
- generate and inspect local OpenTelemetry spans;
- test success, validation, and dependency-failure paths;
- explain why a process can be live while its service is not ready;
- recover the application after a controlled Redis failure.

## 3. Prerequisites

- Phase 1 is complete.
- Conda `base` is deactivated in the project terminal.
- `python3 --version` reports Python 3.14.0.
- `redis-server --version` reports Redis 8.10.0.
- The project Git repository is initialized.
- Ports 6379, 8000, and 8080 are available.

Check without starting anything:

```bash
python3 --version
redis-server --version
lsof -nP -iTCP:6379 -sTCP:LISTEN
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:8080 -sTCP:LISTEN
```

No output from an `lsof` command means the corresponding port is currently unused.

## 4. Files you will create

```text
app/
├── api/
│   ├── reliability_api/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── logging_config.py
│   │   ├── main.py
│   │   ├── metrics.py
│   │   ├── redis_client.py
│   │   └── telemetry.py
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_health.py
│   │   ├── test_requests.py
│   │   └── test_telemetry.py
│   ├── requirements.txt
│   └── requirements-dev.txt
└── frontend/
    ├── index.html
    ├── app.js
    └── styles.css
```

Module ownership:

| Module | Responsibility |
|---|---|
| `config.py` | Validated environment-driven settings |
| `logging_config.py` | JSON log format and request-context fields |
| `redis_client.py` | Redis lifecycle and dependency abstraction |
| `metrics.py` | Prometheus metric definitions and HTTP middleware |
| `telemetry.py` | OpenTelemetry provider and instrumentation setup |
| `main.py` | Application lifecycle, middleware, routes, and error mapping |
| `tests/` | Behavior and observability verification |
| `frontend/` | Small user interface that calls the API |

Do not place all behavior in `main.py`. Clear boundaries will make later failures easier to isolate and test.

## 5. Before you build: predict

Write your answers before implementation:

1. If Redis stops, should `/health/live` fail? Why?
2. If Redis stops, should `/health/ready` fail? Why?
3. Which metric labels could accidentally create one time series per request?
4. Should a request ID be trusted when supplied by an unknown client?
5. What should the API return when failure injection is disabled?
6. Which evidence would distinguish slow application code from slow Redis access?

Keep the predictions and revisit them at the phase gate.

## 6. Application contract

Implement this contract. Names and response fields are authoritative for later guides.

### 6.1 Configuration

| Environment variable | Default | Meaning |
|---|---|---|
| `APP_NAME` | `reliability-api` | Service name used in responses and telemetry |
| `APP_VERSION` | `dev` | Build or release version |
| `APP_ENVIRONMENT` | `local` | Environment label |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Redis connection URL |
| `ENABLE_FAILURE_INJECTION` | `false` | Enables bounded lab-only failure controls |
| `LOG_LEVEL` | `INFO` | Application log threshold |
| `OTEL_CONSOLE_EXPORTER` | `true` | Prints spans locally until Tempo exists |

Use `pydantic-settings`. Read settings once through a cached factory rather than repeatedly parsing the environment during requests.

Do not commit a real `.env` file. `.env.example` may contain documented non-secret examples.

### 6.2 HTTP endpoints

| Method and path | Behavior | Success status |
|---|---|---|
| `GET /` | API identity and links to docs, health, and metrics | 200 |
| `GET /health/live` | Process is running; no Redis call | 200 |
| `GET /health/ready` | Redis ping succeeds within a short timeout | 200 |
| `GET /api/v1/visits` | Atomically increment and return a Redis counter | 200 |
| `POST /api/v1/visits/reset` | Reset the counter only when failure injection is enabled | 204 |
| `GET /api/v1/work` | Return normal, bounded slow, or intentional-error behavior | 200 or 500 |
| `GET /metrics` | Prometheus text exposition | 200 |
| `GET /docs` | FastAPI-generated interactive API documentation | 200 |

Required response examples:

```json
{
  "status": "live",
  "service": "reliability-api",
  "version": "dev"
}
```

```json
{
  "status": "ready",
  "dependencies": {
    "redis": "up"
  }
}
```

```json
{
  "visits": 1,
  "request_id": "generated-or-validated-id"
}
```

When Redis is unavailable:

- `/health/live` remains 200;
- `/health/ready` returns 503 with Redis reported as down;
- `/api/v1/visits` returns 503 with a stable error code such as `dependency_unavailable`;
- internal connection details and stack traces are not returned to the client.

### 6.3 Guarded work endpoint

`GET /api/v1/work` accepts:

- `delay_ms`: integer from 0 through 2000, default 0;
- `fail`: boolean, default false.

Normal behavior is always allowed. Delay or failure behavior is allowed only when `ENABLE_FAILURE_INJECTION=true`. When disabled, requests attempting either behavior must return 403 with a stable error code.

Bound the delay and validate it through FastAPI. Do not accept arbitrary shell commands, code, URLs, file paths, memory sizes, or CPU durations.

## 7. Create the isolated Python environment

From the repository root:

```bash
mkdir -p app/api/reliability_api app/api/tests app/frontend
touch app/api/reliability_api/__init__.py app/api/tests/__init__.py
python3 -m venv app/api/.venv
source app/api/.venv/bin/activate
python --version
python -m pip install --upgrade pip
```

Expected Python version:

```text
Python 3.14.0
```

Confirm isolation:

```bash
which python
which pip
```

Both paths should be under `/Users/m3/Desktop/k8slab/app/api/.venv/`.

Do not use global `pip`, Anaconda `pip`, or `sudo pip`.

## 8. Pin and install dependencies

Create `app/api/requirements.txt`:

```text
fastapi==0.141.1
uvicorn[standard]==0.54.0
pydantic-settings==2.15.0
redis==8.1.0
prometheus-client==0.26.0
opentelemetry-api==1.45.0
opentelemetry-sdk==1.45.0
opentelemetry-instrumentation-fastapi==0.66b0
opentelemetry-instrumentation-redis==0.66b0
```

Create `app/api/requirements-dev.txt`:

```text
-r requirements.txt
httpx==0.28.1
pytest==9.1.1
```

Install only inside the active virtual environment:

```bash
python -m pip install -r app/api/requirements-dev.txt
python -m pip check
```

Inspect the dependency graph:

```bash
python -m pip list
```

Direct dependencies are pinned here. In Phase 3, the container and CI workflow will introduce a reproducible resolved lock or hash strategy after the application behavior is established.

## 9. Implement configuration

In `config.py`:

1. Create a `Settings` class derived from `BaseSettings`.
2. Define every variable from Section 6.1 with a type and default.
3. Use an environment prefix only if it does not change the authoritative variable names.
4. Create a `get_settings()` function decorated with `functools.lru_cache`.
5. Do not read arbitrary configuration directly from `os.environ` elsewhere.

Verification checkpoint:

```bash
cd app/api
source .venv/bin/activate
python -c 'from reliability_api.config import get_settings; print(get_settings().model_dump())'
```

Inspect the output. It must contain no secret and must show the documented defaults.

Then override one value for one command:

```bash
APP_VERSION=phase-2 python -c 'from reliability_api.config import get_settings; print(get_settings().app_version)'
```

Expected output:

```text
phase-2
```

## 10. Implement Redis lifecycle and abstraction

In `redis_client.py`:

1. Use the asynchronous Redis client from `redis.asyncio`.
2. Create the client from `REDIS_URL` with decoded string responses.
3. Define an async `ping()` operation.
4. Define an async atomic `increment_visits()` operation using Redis `INCR`.
5. Define an async `reset_visits()` operation.
6. Close the client during application shutdown.
7. Set short socket-connect and socket-operation timeouts so readiness does not hang.

Expose the dependency to routes through a small function that tests can override. Avoid creating a new connection pool for every request.

Question to answer in your notes: why is `INCR` safer than reading the value, adding one in Python, and writing it back?

## 11. Implement health semantics

Implement liveness without checking Redis. Liveness answers whether the application process and event loop can serve a basic request.

Implement readiness by awaiting Redis `PING` with a bounded timeout. Catch the narrow Redis and timeout exceptions you expect; log unexpected exceptions separately.

Do not put application initialization, schema mutation, or recovery actions inside a health endpoint. Probes are called repeatedly and must be cheap.

Verification will later prove these three distinct states:

| API process | Redis | Liveness | Readiness |
|---|---|---|---|
| Down | Any | Connection failure | Connection failure |
| Up | Down | 200 | 503 |
| Up | Up | 200 | 200 |

## 12. Implement request correlation and structured logging

### 12.1 Request ID rules

Add HTTP middleware that:

1. reads `X-Request-ID` if present;
2. accepts it only when it matches a conservative length and character policy;
3. otherwise generates a UUID;
4. stores it in a `ContextVar` for the current request;
5. returns it in the `X-Request-ID` response header;
6. includes it in application request logs.

Never use request IDs as Prometheus labels. They are intentionally high-cardinality.

### 12.2 JSON log schema

Use Python's standard logging system and emit one JSON object per line with at least:

```text
timestamp
level
message
service
environment
version
request_id
trace_id
method
route
status_code
duration_ms
```

Fields that do not apply may be absent or null. Log to standard output/error, not to local files.

Do not log request bodies, credentials, Redis URLs containing passwords, or full exception tracebacks to clients. Internal exception logs may include stack traces when appropriate.

## 13. Implement Prometheus metrics

Define metrics once at module import, not per request:

```text
http_server_requests_total{method,route,status_code}
http_server_request_duration_seconds{method,route}
redis_operations_total{operation,outcome}
app_info{service,version,environment} = 1
```

Use a Counter for totals, a Histogram for duration, and a Gauge for build information.

For the `route` label, use the normalized route template such as `/api/v1/work`, never the raw requested path. Unmatched paths should use a fixed value such as `unmatched`.

Do not add these labels:

- request ID;
- client IP;
- user agent;
- exception message;
- arbitrary URL;
- visit-counter value.

They would create unbounded or unnecessarily large time-series sets.

Expose metrics using `prometheus_client.generate_latest()` and the official Prometheus content type.

## 14. Implement local tracing

In `telemetry.py`:

1. Create an OpenTelemetry `Resource` with service name, version, and environment.
2. Create one `TracerProvider`.
3. When `OTEL_CONSOLE_EXPORTER=true`, attach a console span exporter.
4. Instrument FastAPI.
5. Instrument the Redis client library.
6. Add the active trace ID to structured request logs.
7. Avoid instrumenting health and metrics endpoints if their volume makes the learning output noisy.

For local learning, a simple console span processor makes individual spans easy to see. Phase 13 will replace the console path with an OTLP pipeline and Tempo.

Record the relationship:

```text
one trace
  -> one server span for the HTTP request
  -> one or more child spans for Redis operations
```

## 15. Assemble the FastAPI application

In `main.py`:

1. Use FastAPI's lifespan mechanism for Redis creation and cleanup.
2. Configure logging before serving requests.
3. Configure telemetry once.
4. Add narrowly scoped CORS for `http://127.0.0.1:8080` and `http://localhost:8080` during local development.
5. Install request-ID, logging, and metrics middleware in a deliberate order.
6. Implement the endpoint contract from Section 6.
7. Map known Redis failures to 503 responses.
8. Keep unexpected internal failures as 500 responses with safe client messages.

Think about middleware order before testing. The outer middleware observes failures produced by inner middleware and routes; the order affects correlation fields, timing, and error metrics.

## 16. Build the static frontend

The frontend should remain small. It must:

- show API liveness and readiness;
- fetch and display the visit count;
- display the returned request ID;
- provide buttons for normal work, bounded slow work, and intentional failure;
- clearly show HTTP status and a safe error message;
- avoid embedding credentials or environment secrets.

For local development, `app.js` may call `http://127.0.0.1:8000`. Later, the frontend will use a same-origin `/api` route through the Kubernetes Gateway.

Serve it locally in a separate terminal:

```bash
python3 -m http.server 8080 --directory app/frontend
```

The frontend server is intentionally simple and is not the production container server selected in Phase 3.

## 17. Write tests before declaring success

Use FastAPI's `TestClient` and dependency overrides. Tests must not require a real Redis process unless explicitly marked as integration tests.

Create a small fake Redis dependency in `tests/conftest.py` with controllable healthy and failing behavior.

Required tests:

### Health

- liveness returns 200 when Redis is healthy;
- liveness still returns 200 when Redis is failing;
- readiness returns 200 and `redis: up` when healthy;
- readiness returns 503 and `redis: down` when failing.

### Requests

- visits increment atomically through the dependency contract;
- a valid incoming request ID is returned;
- a missing or invalid request ID is replaced;
- normal work succeeds;
- delay and failure controls return 403 when disabled;
- delay validation rejects negative values and values above 2000;
- intentional failure returns 500 only when enabled;
- dependency failure returns 503 without leaking internal connection details.

### Telemetry

- `/metrics` uses the Prometheus content type;
- a normal request increments the expected request counter;
- normalized route labels are used;
- no request ID appears as a metric label;
- structured request logs are valid JSON and contain correlation fields.

Run:

```bash
cd app/api
source .venv/bin/activate
pytest -q
```

Do not change an assertion merely to make a failing implementation pass. Decide whether the code or the documented contract is wrong.

## 18. Run the complete application locally

Use three terminals.

### Terminal 1 — Redis

```bash
redis-server --port 6379 --save '' --appendonly no
```

This starts an intentionally non-persistent local instance for the lab. In another shell, verify:

```bash
redis-cli -p 6379 ping
```

Expected:

```text
PONG
```

### Terminal 2 — API

```bash
cd /Users/m3/Desktop/k8slab/app/api
source .venv/bin/activate
ENABLE_FAILURE_INJECTION=true uvicorn reliability_api.main:app --host 127.0.0.1 --port 8000
```

Do not use auto-reload while collecting final verification evidence; reload creates an extra process and can make lifecycle observations confusing.

### Terminal 3 — Frontend

```bash
cd /Users/m3/Desktop/k8slab
python3 -m http.server 8080 --directory app/frontend
```

Open <http://127.0.0.1:8080> and verify the frontend behavior.

## 19. Verification sequence

Run each request and explain the result:

```bash
curl -i http://127.0.0.1:8000/health/live
curl -i http://127.0.0.1:8000/health/ready
curl -i http://127.0.0.1:8000/api/v1/visits
curl -i -H 'X-Request-ID: phase2-check-001' http://127.0.0.1:8000/api/v1/visits
curl -i 'http://127.0.0.1:8000/api/v1/work?delay_ms=250'
curl -i 'http://127.0.0.1:8000/api/v1/work?fail=true'
curl -s http://127.0.0.1:8000/metrics | grep -E 'http_server|redis_operations|app_info'
```

Check the API terminal for:

- valid JSON log lines;
- the supplied request ID;
- trace and span IDs;
- a server span and Redis child span;
- durations consistent with the 250 ms request;
- the intentional failure represented in logs, metrics, and traces.

Do not expect every signal to use exactly the same field names. Correlation depends on shared request or trace identifiers and time windows.

## 20. Controlled dependency-failure exercise

### Hypothesis

Stopping Redis should leave the API process live, make readiness fail, make visits fail safely, and produce dependency-error telemetry.

### Safety and abort conditions

- Target only the foreground Redis process started for this phase.
- Do not stop an unrelated Redis service.
- No persistent data is expected because persistence was disabled.
- Abort if you are uncertain which Redis process owns port 6379.

Confirm ownership first:

```bash
lsof -nP -iTCP:6379 -sTCP:LISTEN
```

### Introduce the failure

In the Redis terminal, press `Ctrl+C` once.

Then run:

```bash
curl -i http://127.0.0.1:8000/health/live
curl -i http://127.0.0.1:8000/health/ready
curl -i http://127.0.0.1:8000/api/v1/visits
```

Expected:

- liveness: 200;
- readiness: 503;
- visits: 503 with stable safe error response;
- logs: dependency failure with request/trace correlation;
- metrics: error outcome and HTTP status counters increase;
- traces: Redis operation records an error.

### Recover

Restart Redis using the same command, wait for it to accept connections, then verify:

```bash
redis-cli -p 6379 ping
curl -i http://127.0.0.1:8000/health/ready
curl -i http://127.0.0.1:8000/api/v1/visits
```

Because persistence is disabled, the visit count may restart. Recovery means dependency connectivity and application behavior return—not that deliberately ephemeral data survives.

## 21. Troubleshooting

| Symptom | Evidence to collect | Likely causes | Next test |
|---|---|---|---|
| Wrong Python interpreter | `which python`, `python --version` | Virtual environment inactive or Conda active | Reactivate `app/api/.venv` and inspect `PATH` |
| Redis port already used | `lsof -nP -iTCP:6379 -sTCP:LISTEN` | Existing Homebrew, OrbStack, or project Redis | Identify ownership; do not kill an unknown process |
| Readiness hangs | Request duration, Redis timeouts | Missing connect/operation timeout | Test with Redis stopped and inspect configured client timeouts |
| Liveness fails with Redis | Liveness implementation | Dependency check incorrectly included | Remove Redis from liveness; keep it in readiness |
| Metric series grow with requests | `/metrics` label values | Raw paths or request IDs used as labels | Replace with bounded route templates and remove unique labels |
| Logs are not valid JSON | One complete log line | Plain formatter or multiline traceback mixed into output | Configure one JSON object per event and parse it with `jq` |
| Trace lacks Redis child span | Console span output | Redis instrumentation initialized too late | Initialize instrumentation before client operations |
| Browser reports CORS error | Browser console, API headers | Origin not allowlisted or URL mismatch | Compare exact frontend origin with CORS configuration |
| Tests require real Redis | Test fixture and dependency wiring | Redis dependency cannot be overridden | Introduce a narrow dependency interface and fake |
| Failure endpoint works when disabled | Settings and test environment | Guard missing or cached settings not reset in test | Test both enabled and disabled application configurations |

## 22. Production considerations

- Console trace export is for learning; production sends OTLP to a collector.
- Failure injection should not normally ship enabled in a production service.
- Local CORS origins are not production routing policy.
- Redis without authentication and persistence is a local lab choice.
- Health endpoints need timeouts, resource budgets, and protection from cascading dependency load.
- High-volume structured logs require redaction, sampling or rate control, retention, and cost planning.
- Metrics must be designed around bounded label sets.
- A single local API process does not demonstrate graceful multi-replica behavior.

## 23. Cleanup and reset

Stop the foreground frontend, API, and Redis processes with `Ctrl+C` in their respective terminals.

The Redis instance is non-persistent. Its visit counter is intentionally discarded when it stops.

The virtual environment is ignored by Git and may be recreated from the pinned requirements. Do not commit `.venv/`.

Before committing:

```bash
git status --short
git diff
git check-ignore -v app/api/.venv
```

Verify that no `.env`, private key, cache, or raw log file is staged.

## 24. Definition of done

- [ ] Phase 1 is marked complete.
- [ ] Predictions were written before implementation.
- [ ] The documented file structure exists.
- [ ] Python runs from the project virtual environment.
- [ ] Direct dependencies are pinned and `pip check` succeeds.
- [ ] Configuration comes from the documented settings contract.
- [ ] Liveness and readiness have different dependency semantics.
- [ ] Structured logs are valid JSON and contain request and trace correlation.
- [ ] Metrics expose bounded labels for requests, duration, Redis operations, and app information.
- [ ] Local traces show HTTP and Redis spans.
- [ ] The frontend exercises healthy, slow, and failure behavior.
- [ ] All required tests pass without real Redis.
- [ ] The complete local verification sequence passes.
- [ ] The controlled Redis failure was observed and recovered.
- [ ] No sensitive or generated local files are staged.
- [ ] The implementation and learning notes are committed locally.
- [ ] Review questions can be answered in your own words.

When every item is true, change this guide and Phase 2 in the canonical documentation map from `Draft` to `Complete`.

## 25. Review questions

1. Why must liveness avoid depending on Redis?
2. Why should readiness use a short timeout?
3. Why is Redis `INCR` preferable to a read-modify-write counter?
4. What is the difference between a request ID and a trace ID?
5. Why must neither identifier be a Prometheus label?
6. What makes a metric label safe or unsafe?
7. Why should known dependency failures return 503 instead of 500?
8. What evidence proves a 250 ms delay occurred in the intended layer?
9. Why are tests designed to run without a real Redis process?
10. What information must never appear in client errors or logs?
11. Why is failure injection gated and bounded?
12. What did the Redis failure exercise prove about health semantics?

## 26. Further study

- FastAPI documentation: <https://fastapi.tiangolo.com/>
- FastAPI testing: <https://fastapi.tiangolo.com/tutorial/testing/>
- Python virtual environments: <https://docs.python.org/3/library/venv.html>
- redis-py documentation: <https://redis.readthedocs.io/>
- Prometheus metric types: <https://prometheus.io/docs/concepts/metric_types/>
- Prometheus instrumentation practices: <https://prometheus.io/docs/practices/instrumentation/>
- OpenTelemetry Python: <https://opentelemetry.io/docs/languages/python/>
- OpenTelemetry semantic conventions: <https://opentelemetry.io/docs/specs/semconv/>
- Twelve-Factor logs: <https://12factor.net/logs>

## 27. Next phase

After passing this phase gate, continue to `docs/03-containers-and-ci.md`.

Phase 3 will create production-oriented container images, run the application components through the container network, scan and test images, create the GitHub repository, push the reviewed history, configure GitHub Actions, and publish immutable images to GHCR.
