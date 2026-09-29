from fastapi import Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from reliability_api.config import Settings

HTTP_REQUESTS = Counter(
    "http_server_requests_total",
    "Completed HTTP requests",
    ["method", "route", "status_code"],
)
HTTP_DURATION = Histogram(
    "http_server_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "route"],
)
REDIS_OPERATIONS = Counter(
    "redis_operations_total",
    "Completed Redis operations",
    ["operation", "outcome"],
)
APP_INFO = Gauge(
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
    return getattr(request.scope.get("route"), "path", "unmatched")


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
