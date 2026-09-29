import asyncio
import logging
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from reliability_api.config import Settings, get_settings
from reliability_api.logging_config import (
    choose_request_id,
    configure_logging,
    request_id_context,
)
from reliability_api.metrics import (
    HTTP_DURATION,
    HTTP_REQUESTS,
    configure_app_info,
    metrics_response,
    normalized_route,
)
from reliability_api.redis_client import RedisClient, get_redis_client
from reliability_api.telemetry import configure_telemetry


logger = logging.getLogger(__name__)
settings = get_settings()
configure_logging(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await get_redis_client().close()
    telemetry_provider.shutdown()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8080", "http://localhost:8080"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Request-ID"],
)

configure_app_info(settings)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = choose_request_id(request.headers.get("X-Request-ID"))
    token = request_id_context.set(request_id)
    started = perf_counter()
    status_code = 500

    try:
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("unhandled_request_exception")
            response = JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "internal_error",
                        "message": "An unexpected error occurred",
                    }
                },
            )

        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        duration_seconds = perf_counter() - started
        route = normalized_route(request)
        HTTP_REQUESTS.labels(
            method=request.method,
            route=route,
            status_code=str(status_code),
        ).inc()
        HTTP_DURATION.labels(
            method=request.method,
            route=route,
        ).observe(duration_seconds)
        logger.info(
            "request_complete",
            extra={
                "method": request.method,
                "route": route,
                "status_code": status_code,
                "duration_ms": round(duration_seconds * 1000, 3),
            },
        )
        request_id_context.reset(token)


@app.get("/")
async def root():
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "links": {
            "docs": "/docs",
            "liveness": "/health/live",
            "readiness": "/health/ready",
            "metrics": "/metrics",
        },
    }


@app.get("/health/live")
async def health_live(
    current_settings: Settings = Depends(get_settings),
):
    return {
        "status": "live",
        "service": current_settings.app_name,
        "version": current_settings.app_version,
    }


@app.get("/health/ready")
async def health_ready(
    redis: RedisClient = Depends(get_redis_client),
):
    try:
        redis_is_up = await redis.ping()
    except (RedisConnectionError, RedisTimeoutError):
        redis_is_up = False
    except Exception:
        logger.exception("unexpected_readiness_check_failure")
        redis_is_up = False

    if not redis_is_up:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "dependencies": {"redis": "down"},
            },
        )

    return {
        "status": "ready",
        "dependencies": {"redis": "up"},
    }


@app.get("/api/v1/visits")
async def visits(redis: RedisClient = Depends(get_redis_client)):
    try:
        count = await redis.increment_visits()
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
        "request_id": request_id_context.get(),
    }


@app.post("/api/v1/visits/reset")
async def reset_visits(redis: RedisClient = Depends(get_redis_client)):
    if not settings.enable_failure_injection:
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "code": "failure_injection_disabled",
                    "message": "Failure injection is disabled",
                }
            },
        )

    try:
        await redis.reset_visits()
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

    return Response(status_code=204)


@app.get("/api/v1/work")
async def work(
    delay_ms: Annotated[int, Query(ge=0, le=2000)] = 0,
    fail: bool = False,
):
    requested_failure = delay_ms > 0 or fail
    if requested_failure and not settings.enable_failure_injection:
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "code": "failure_injection_disabled",
                    "message": "Failure injection is disabled",
                }
            },
        )

    if delay_ms:
        await asyncio.sleep(delay_ms / 1000)

    if fail:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "intentional_failure",
                    "message": "Intentional bounded lab failure",
                }
            },
        )

    return {
        "status": "ok",
        "delay_ms": delay_ms,
    }


@app.get("/metrics", include_in_schema=False)
async def metrics():
    return metrics_response()


telemetry_provider = configure_telemetry(app, settings)
