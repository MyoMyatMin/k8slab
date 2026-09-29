import os

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError


os.environ["ENABLE_FAILURE_INJECTION"] = "false"
os.environ["OTEL_CONSOLE_EXPORTER"] = "false"

from reliability_api.main import app  # noqa: E402
from reliability_api.redis_client import get_redis_client  # noqa: E402


class FakeRedis:
    def __init__(self) -> None:
        self.healthy = True
        self.visits = 0

    def require_healthy(self) -> None:
        if not self.healthy:
            raise RedisConnectionError("fake Redis unavailable")

    async def ping(self) -> bool:
        self.require_healthy()
        return True

    async def increment_visits(self) -> int:
        self.require_healthy()
        self.visits += 1
        return self.visits

    async def reset_visits(self) -> None:
        self.require_healthy()
        self.visits = 0


@pytest.fixture(scope="session")
def test_client():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def api_client(test_client):
    fake = FakeRedis()
    app.dependency_overrides[get_redis_client] = lambda: fake
    yield test_client, fake
    app.dependency_overrides.clear()
