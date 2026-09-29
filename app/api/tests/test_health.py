def test_liveness_returns_200_when_redis_is_healthy(api_client):
    client, _ = api_client

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "live",
        "service": "reliability-api",
        "version": "dev",
    }


def test_liveness_ignores_redis_failure(api_client):
    client, fake = api_client
    fake.healthy = False

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "live"


def test_readiness_reports_redis_up(api_client):
    client, _ = api_client

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "dependencies": {"redis": "up"},
    }


def test_readiness_reports_redis_failure(api_client):
    client, fake = api_client
    fake.healthy = False

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "dependencies": {"redis": "down"},
    }
