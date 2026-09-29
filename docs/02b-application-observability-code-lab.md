# Phase 2B — Application Observability Code Lab

> Exercise mode: Guided completion  
> Lessons: logs, metrics, traces, remaining API endpoints

Start only after the foundation checkpoint in `docs/02a-application-foundations-code-lab.md` passes.

## Lesson 4 — Request IDs and JSON logs

Target: `app/api/reliability_api/logging_config.py`

```python
import json
import logging
import re
from contextvars import ContextVar
from datetime import UTC, datetime
from uuid import uuid4

from opentelemetry import trace

from reliability_api.config import Settings


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
request_id_context: ContextVar[str | None] = ContextVar(
    "request_id",
    default=None,
)


def choose_request_id(candidate: str | None) -> str:
    # TODO 1: Preserve a valid candidate; otherwise generate a UUID string.
    ...


def current_trace_id() -> str | None:
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return None
    return format(span_context.trace_id, "032x")


class JsonFormatter(logging.Formatter):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "service": self.settings.app_name,
            "environment": self.settings.app_environment,
            "version": self.settings.app_version,
            "request_id": request_id_context.get(),
            "trace_id": current_trace_id(),
        }
        for field in ("method", "route", "status_code", "duration_ms"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, separators=(",", ":"))


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(settings))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    # TODO 2: Apply settings.log_level, falling back to logging.INFO.
```

In `main.py`, call `configure_logging(settings)` before serving requests, then add middleware:

```python
from time import perf_counter

from fastapi import Request

from reliability_api.logging_config import (
    choose_request_id,
    configure_logging,
    request_id_context,
)


configure_logging(settings)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = choose_request_id(request.headers.get("X-Request-ID"))
    token = request_id_context.set(request_id)
    started = perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        # TODO 3: Echo request_id in the X-Request-ID response header.
        return response
    finally:
        duration_ms = round((perf_counter() - started) * 1000, 3)
        route = getattr(request.scope.get("route"), "path", "unmatched")
        logger.info(
            "request_complete",
            extra={
                "method": request.method,
                "route": route,
                "status_code": status_code,
                "duration_ms": duration_ms,
            },
        )
        request_id_context.reset(token)
```

Checkpoint:

```bash
curl -i -H 'X-Request-ID: phase2-check-001' http://127.0.0.1:8000/health/live
curl -i -H 'X-Request-ID: contains spaces' http://127.0.0.1:8000/health/live
```

The first ID is echoed; the invalid second ID is replaced. Copy one complete log line and parse it with `jq`.

<details>
<summary>Reference answers</summary>

```python
if candidate and REQUEST_ID_PATTERN.fullmatch(candidate):
    return candidate
return str(uuid4())

root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

response.headers["X-Request-ID"] = request_id
```

</details>

## Lesson 5 — Prometheus metrics

Target: `app/api/reliability_api/metrics.py`

```python
from fastapi import Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from reliability_api.config import Settings


# TODO 1: Choose Counter, Histogram, or Gauge for each metric.
HTTP_REQUESTS = ...(
    "http_server_requests_total",
    "Completed HTTP requests",
    ["method", "route", "status_code"],
)
HTTP_DURATION = ...(
    "http_server_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "route"],
)
REDIS_OPERATIONS = ...(
    "redis_operations_total",
    "Completed Redis operations",
    ["operation", "outcome"],
)
APP_INFO = ...(
    "app_info",
    "Application build information",
    ["service", "version", "environment"],
)


def configure_app_info(settings: Settings) -> None:
    APP_INFO.labels(
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_environment,
    ).set(1)


def normalized_route(request: Request) -> str:
    # TODO 2: Return the matched route template or the fixed value unmatched.
    ...


def metrics_response() -> Response:
    # TODO 3: Return generated metrics with the official content type.
    ...
```

In the request middleware `finally` block, replace the local route expression with `normalized_route(request)` and add:

```python
HTTP_REQUESTS.labels(
    method=request.method,
    route=route,
    status_code=str(status_code),
).inc()
HTTP_DURATION.labels(
    method=request.method,
    route=route,
).observe(duration_ms / 1000)
```

Configure application information once and expose metrics:

```python
configure_app_info(settings)


@app.get("/metrics", include_in_schema=False)
async def metrics():
    return metrics_response()
```

To instrument Redis without repeating error-label code, add this helper inside `RedisClient` and route its three operations through it:

```python
from collections.abc import Awaitable
from typing import TypeVar

from reliability_api.metrics import REDIS_OPERATIONS


T = TypeVar("T")


async def _record(self, operation: str, call: Awaitable[T]) -> T:
    try:
        result = await call
    except Exception:
        REDIS_OPERATIONS.labels(operation=operation, outcome="error").inc()
        raise
    REDIS_OPERATIONS.labels(operation=operation, outcome="success").inc()
    return result
```

Example learner TODO: change `ping()` to return `bool(await self._record("ping", self._client.ping()))`, then apply the same pattern to `incr` and `delete`.

Checkpoint:

```bash
curl -s http://127.0.0.1:8000/health/live >/dev/null
curl -s http://127.0.0.1:8000/metrics | grep -E 'http_server_requests_total|http_server_request_duration_seconds|redis_operations_total|app_info'
```

Learner-owned experiment: send requests with ten unique request IDs and prove none appears in `/metrics`.

<details>
<summary>Reference answers</summary>

Use `Counter`, `Histogram`, `Counter`, and `Gauge`, in that order.

```python
def normalized_route(request: Request) -> str:
    return getattr(request.scope.get("route"), "path", "unmatched")


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

</details>

## Lesson 6 — Local OpenTelemetry traces

Target: `app/api/reliability_api/telemetry.py`

```python
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

from reliability_api.config import Settings


def configure_telemetry(app: FastAPI, settings: Settings) -> TracerProvider:
    resource = Resource.create(
        {
            # TODO 1: Set service.name, service.version, and deployment.environment.name.
        }
    )
    provider = TracerProvider(resource=resource)
    if settings.otel_console_exporter:
        # TODO 2: Attach ConsoleSpanExporter through SimpleSpanProcessor.
        ...
    # TODO 3: Install provider globally.
    ...
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="health/live,health/ready,metrics",
    )
    # TODO 4: Instrument redis-py.
    ...
    return provider
```

Call this once after `app` exists and save the returned provider. During lifespan shutdown, close Redis and then call `telemetry_provider.shutdown()`.

Checkpoint: call `/api/v1/visits` and find an HTTP server span plus a Redis child span sharing one trace ID in the API terminal.

Learner-owned experiment: restart with `OTEL_CONSOLE_EXPORTER=false` and explain why requests still work while spans stop printing.

<details>
<summary>Reference answers</summary>

```python
resource = Resource.create(
    {
        "service.name": settings.app_name,
        "service.version": settings.app_version,
        "deployment.environment.name": settings.app_environment,
    }
)
provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)
RedisInstrumentor().instrument()
```

</details>

## Lesson 7 — Remaining API endpoints

Add local-only CORS after creating `app`:

```python
from fastapi.middleware.cors import CORSMiddleware


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8080", "http://localhost:8080"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Request-ID"],
)
```

Add the root response directly from the contract. Then complete these behavior-bearing gaps:

```python
import asyncio
from typing import Annotated

from fastapi import Query, Response


@app.get("/api/v1/visits")
async def visits(redis: RedisClient = Depends(get_redis_client)):
    try:
        # TODO 1: Get the next atomic count.
        count = ...
    except (RedisConnectionError, RedisTimeoutError):
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "dependency_unavailable",
                    "message": "Redis is unavailable",
                }
            },
        )
    return {
        "visits": count,
        # TODO 2: Read the active request ID.
        "request_id": ...,
    }


@app.post("/api/v1/visits/reset")
async def reset_visits(redis: RedisClient = Depends(get_redis_client)):
    # TODO 3: Return 403 unless failure injection is enabled.
    ...
    try:
        await redis.reset_visits()
    except (RedisConnectionError, RedisTimeoutError):
        return JSONResponse(
            status_code=503,
            content={"error": {"code": "dependency_unavailable"}},
        )
    return Response(status_code=204)


@app.get("/api/v1/work")
async def work(
    delay_ms: Annotated[int, Query(ge=0, le=2000)] = 0,
    fail: bool = False,
):
    requested_failure = delay_ms > 0 or fail
    # TODO 4: Return 403 when controlled failure is requested but disabled.
    ...
    if delay_ms:
        # TODO 5: Perform a non-blocking delay in seconds.
        ...
    if fail:
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "intentional_failure"}},
        )
    return {"status": "ok", "delay_ms": delay_ms}
```

Checkpoint with failure injection enabled:

```bash
curl -i http://127.0.0.1:8000/api/v1/visits
curl -i 'http://127.0.0.1:8000/api/v1/work?delay_ms=250'
curl -i 'http://127.0.0.1:8000/api/v1/work?fail=true'
```

Restart without `ENABLE_FAILURE_INJECTION=true`; controlled delay and failure must return 403. A delay of 2001 must be rejected by FastAPI validation.

<details>
<summary>Reference answers</summary>

```python
count = await redis.increment_visits()
request_id_context.get()

if not settings.enable_failure_injection:
    return JSONResponse(
        status_code=403,
        content={"error": {"code": "failure_injection_disabled"}},
    )

if requested_failure and not settings.enable_failure_injection:
    return JSONResponse(
        status_code=403,
        content={"error": {"code": "failure_injection_disabled"}},
    )

await asyncio.sleep(delay_ms / 1000)
```

</details>

## Observability checkpoint

Continue when one request can be found in:

- a JSON log using request or trace ID;
- the bounded Prometheus request and duration series;
- an HTTP server span;
- a Redis child span when the route uses Redis.

Request IDs must never appear as Prometheus label values.
