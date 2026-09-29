import json
import logging

from opentelemetry import trace
from prometheus_client import CONTENT_TYPE_LATEST
from prometheus_client.parser import text_string_to_metric_families

from reliability_api.logging_config import JsonFormatter, request_id_context
from reliability_api.main import settings


def metric_value(text, name, labels):
    for family in text_string_to_metric_families(text):
        for sample in family.samples:
            if sample.name == name and all(
                sample.labels.get(key) == value
                for key, value in labels.items()
            ):
                return sample.value
    return 0.0


def test_metrics_use_prometheus_content_type(api_client):
    client, _ = api_client

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST


def test_request_increments_normalized_metric(api_client):
    client, _ = api_client
    labels = {
        "method": "GET",
        "route": "/health/live",
        "status_code": "200",
    }
    before = metric_value(
        client.get("/metrics").text,
        "http_server_requests_total",
        labels,
    )

    client.get("/health/live")

    after = metric_value(
        client.get("/metrics").text,
        "http_server_requests_total",
        labels,
    )
    assert after == before + 1


def test_metrics_use_route_templates_without_request_ids(api_client):
    client, _ = api_client
    unique_request_id = "must-not-be-a-prometheus-label-001"

    client.get(
        "/api/v1/work",
        headers={"X-Request-ID": unique_request_id},
    )
    metrics = client.get("/metrics").text

    assert 'route="/api/v1/work"' in metrics
    assert unique_request_id not in metrics


def test_structured_log_is_json_with_correlation_fields():
    formatter = JsonFormatter(settings)
    record = logging.LogRecord(
        name="reliability_api.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request_complete",
        args=(),
        exc_info=None,
    )
    record.method = "GET"
    record.route = "/health/live"
    record.status_code = 200
    record.duration_ms = 1.25
    token = request_id_context.set("phase2-log-test-001")

    try:
        tracer = trace.get_tracer(__name__)
        with tracer.start_as_current_span("structured-log-test"):
            payload = json.loads(formatter.format(record))
    finally:
        request_id_context.reset(token)

    assert payload["message"] == "request_complete"
    assert payload["request_id"] == "phase2-log-test-001"
    assert payload["method"] == "GET"
    assert payload["route"] == "/health/live"
    assert payload["status_code"] == 200
    assert len(payload["trace_id"]) == 32
