from collections.abc import Awaitable
from typing import TypeVar

from redis.asyncio import Redis

from reliability_api.config import get_settings
from reliability_api.metrics import REDIS_OPERATIONS


T = TypeVar("T")

VISITS_KEY = "reliability_api:visits"


class RedisClient:
    def __init__(self, redis_url: str) -> None:
        self._client = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
        )

    async def ping(self) -> bool:
        return bool(await self._record("ping", self._client.ping()))

    async def increment_visits(self) -> int:
        return int(
            await self._record(
                "increment_visits",
                self._client.incr(VISITS_KEY),
            )
        )

    async def reset_visits(self) -> None:
        await self._record("reset_visits", self._client.delete(VISITS_KEY))

    async def close(self) -> None:
        await self._client.aclose()

    async def _record(self, operation: str, call: Awaitable[T]) -> T:
        try:
            result = await call
        except Exception:
            REDIS_OPERATIONS.labels(
                operation=operation,
                outcome="error",
            ).inc()
            raise
        REDIS_OPERATIONS.labels(
            operation=operation,
            outcome="success",
        ).inc()
        return result


settings = get_settings()
redis_client = RedisClient(settings.redis_url)


def get_redis_client() -> RedisClient:
    return redis_client
