# Phase 2A — Application Foundations Code Lab

> Exercise mode: Guided completion  
> Lessons: configuration, Redis, health semantics

Attempt each `TODO` before opening its reference answer. If your existing implementation already passes, audit it against the contract instead of replacing it.

## Lesson 1 — Validated configuration

Target: `app/api/reliability_api/config.py`

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # TODO 1: Add all seven typed fields and defaults from Phase 2 Section 6.1.

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    # TODO 2: Return a validated Settings instance.
    ...
```

Required fields: `app_name`, `app_version`, `app_environment`, `redis_url`, `enable_failure_injection`, `log_level`, and `otel_console_exporter`.

Checkpoint:

```bash
cd /Users/m3/Desktop/k8slab/app/api
source .venv/bin/activate
python -c 'from reliability_api.config import get_settings; print(get_settings().model_dump())'
APP_VERSION=phase-2 python -c 'from reliability_api.config import get_settings; print(get_settings().app_version)'
```

The second command must print `phase-2`.

Learner-owned experiment: override `APP_ENVIRONMENT` for one command and prove the default returns in a new command.

<details>
<summary>Reference answer</summary>

```python
class Settings(BaseSettings):
    app_name: str = "reliability-api"
    app_version: str = "dev"
    app_environment: str = "local"
    redis_url: str = "redis://127.0.0.1:6379/0"
    enable_failure_injection: bool = False
    log_level: str = "INFO"
    otel_console_exporter: bool = True

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

</details>

## Lesson 2 — Asynchronous Redis boundary

Target: `app/api/reliability_api/redis_client.py`

```python
from redis.asyncio import Redis

from reliability_api.config import get_settings


VISITS_KEY = "reliability-api:visits"


class RedisClient:
    def __init__(self, redis_url: str) -> None:
        self._client = Redis.from_url(
            redis_url,
            # TODO 1: Decode replies and set one-second connect/operation timeouts.
        )

    async def ping(self) -> bool:
        # TODO 2: Await PING and return bool.
        ...

    async def increment_visits(self) -> int:
        # TODO 3: Atomically increment VISITS_KEY and return int.
        ...

    async def reset_visits(self) -> None:
        # TODO 4: Remove VISITS_KEY.
        ...

    async def close(self) -> None:
        # TODO 5: Close the async client with the current redis-py method.
        ...


settings = get_settings()
redis_client = RedisClient(settings.redis_url)


def get_redis_client() -> RedisClient:
    return redis_client
```

Why one shared object? `Redis` manages a connection pool. Creating it once avoids constructing a new pool on every HTTP request. `get_redis_client()` is a small dependency boundary that tests can replace.

Checkpoint with Redis running:

```bash
redis-cli -p 6379 ping
python -c 'import asyncio; from reliability_api.redis_client import get_redis_client; print(asyncio.run(get_redis_client().ping()))'
```

Expected: `PONG` and `True`.

Learner-owned question: explain, with two simultaneous requests, why Redis `INCR` avoids the lost-update problem of read → add in Python → write.

<details>
<summary>Progressive hints</summary>

- Keywords: `decode_responses`, `socket_connect_timeout`, and `socket_timeout`.
- Redis methods: `ping`, `incr`, and `delete`.
- The current asynchronous cleanup method is `aclose`.

</details>

<details>
<summary>Reference answer</summary>

```python
self._client = Redis.from_url(
    redis_url,
    decode_responses=True,
    socket_connect_timeout=1.0,
    socket_timeout=1.0,
)

async def ping(self) -> bool:
    return bool(await self._client.ping())

async def increment_visits(self) -> int:
    return int(await self._client.incr(VISITS_KEY))

async def reset_visits(self) -> None:
    await self._client.delete(VISITS_KEY)

async def close(self) -> None:
    await self._client.aclose()
```

</details>

## Lesson 3 — Liveness and readiness

Target: the first version of `app/api/reliability_api/main.py`. Later lessons extend it.

```python
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from reliability_api.config import Settings, get_settings
from reliability_api.redis_client import RedisClient, get_redis_client


logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    # TODO 1: Close the shared Redis client during shutdown.


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)


@app.get("/health/live")
async def health_live(current_settings: Settings = Depends(get_settings)):
    # TODO 2: Return status, service, and version without calling Redis.
    ...


@app.get("/health/ready")
async def health_ready(redis: RedisClient = Depends(get_redis_client)):
    try:
        # TODO 3: Await the Redis health operation.
        redis_is_up = ...
    except (RedisConnectionError, RedisTimeoutError):
        redis_is_up = False
    except Exception:
        logger.exception("Unexpected readiness-check failure")
        redis_is_up = False

    if not redis_is_up:
        # TODO 4: Return HTTP 503 with not_ready and redis down.
        ...

    # TODO 5: Return ready and redis up.
    ...
```

Run from `app/api`:

```bash
uvicorn reliability_api.main:app --host 127.0.0.1 --port 8000
```

From another terminal:

```bash
curl -i http://127.0.0.1:8000/health/live
curl -i http://127.0.0.1:8000/health/ready
```

With Redis running, both return 200. Stop only the lab Redis process and repeat: liveness stays 200 and readiness becomes 503.

Learner-owned experiment: temporarily make liveness call Redis, observe the contract violation with Redis stopped, then remove the call. Do not commit the incorrect version.

<details>
<summary>Reference answer</summary>

```python
# TODO 1
await get_redis_client().close()

# TODO 2
return {
    "status": "live",
    "service": current_settings.app_name,
    "version": current_settings.app_version,
}

# TODO 3
redis_is_up = await redis.ping()

# TODO 4
return JSONResponse(
    status_code=503,
    content={"status": "not_ready", "dependencies": {"redis": "down"}},
)

# TODO 5
return {"status": "ready", "dependencies": {"redis": "up"}}
```

</details>

## Foundation checkpoint

You are ready for the observability code lab when:

- configuration defaults and overrides work;
- Redis PING succeeds when Redis is running;
- liveness never depends on Redis;
- readiness changes from 200 to 503 when Redis stops;
- the Redis client closes through `aclose()`.
