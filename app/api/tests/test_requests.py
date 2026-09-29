from uuid import UUID

from reliability_api.main import settings


def test_visits_increment_through_dependency_contract(api_client):
    client, _ = api_client

    first = client.get("/api/v1/visits")
    second = client.get("/api/v1/visits")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["visits"] == 1
    assert second.json()["visits"] == 2


def test_valid_request_id_is_echoed(api_client):
    client, _ = api_client

    response = client.get(
        "/health/live",
        headers={"X-Request-ID": "phase2-test-001"},
    )

    assert response.headers["X-Request-ID"] == "phase2-test-001"


def test_missing_request_id_is_generated(api_client):
    client, _ = api_client

    response = client.get("/health/live")

    UUID(response.headers["X-Request-ID"])


def test_invalid_request_id_is_replaced(api_client):
    client, _ = api_client

    response = client.get(
        "/health/live",
        headers={"X-Request-ID": "contains spaces"},
    )

    returned_id = response.headers["X-Request-ID"]
    assert returned_id != "contains spaces"
    UUID(returned_id)


def test_normal_work_succeeds(api_client):
    client, _ = api_client

    response = client.get("/api/v1/work")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "delay_ms": 0}


def test_failure_controls_are_forbidden_when_disabled(api_client):
    client, _ = api_client

    delayed = client.get("/api/v1/work?delay_ms=1")
    failed = client.get("/api/v1/work?fail=true")

    assert delayed.status_code == 403
    assert failed.status_code == 403
    assert delayed.json()["error"]["code"] == "failure_injection_disabled"
    assert failed.json()["error"]["code"] == "failure_injection_disabled"


def test_delay_validation_rejects_out_of_range_values(api_client):
    client, _ = api_client

    negative = client.get("/api/v1/work?delay_ms=-1")
    excessive = client.get("/api/v1/work?delay_ms=2001")

    assert negative.status_code == 422
    assert excessive.status_code == 422


def test_enabled_failure_controls_are_bounded(api_client, monkeypatch):
    client, _ = api_client
    monkeypatch.setattr(settings, "enable_failure_injection", True)

    delayed = client.get("/api/v1/work?delay_ms=1")
    failed = client.get("/api/v1/work?fail=true")

    assert delayed.status_code == 200
    assert delayed.json()["delay_ms"] == 1
    assert failed.status_code == 500
    assert failed.json()["error"]["code"] == "intentional_failure"


def test_reset_is_gated_and_resets_counter(api_client, monkeypatch):
    client, fake = api_client
    fake.visits = 7

    forbidden = client.post("/api/v1/visits/reset")
    assert forbidden.status_code == 403

    monkeypatch.setattr(settings, "enable_failure_injection", True)
    reset = client.post("/api/v1/visits/reset")

    assert reset.status_code == 204
    assert reset.content == b""
    assert fake.visits == 0


def test_dependency_failure_returns_safe_503(api_client):
    client, fake = api_client
    fake.healthy = False

    response = client.get("/api/v1/visits")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dependency_unavailable"
    assert "fake Redis unavailable" not in response.text
