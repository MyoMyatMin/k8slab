# Phase 2C — Frontend and Tests Code Lab

> Exercise mode: Guided completion  
> Lessons: static frontend and dependency-isolated tests

## Lesson 8 — Static frontend

The frontend is supporting boilerplate. Its job is to make healthy, slow, and failing API behavior visible—not to teach a frontend framework.

Target: `app/frontend/index.html`

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Kubernetes Reliability Lab</title>
    <link rel="stylesheet" href="styles.css">
  </head>
  <body>
    <main>
      <h1>Kubernetes Reliability Lab</h1>
      <p id="health">Health not checked</p>
      <pre id="result">No request sent</pre>
      <button data-action="health">Check health</button>
      <button data-action="visits">Increment visits</button>
      <button data-action="normal">Normal work</button>
      <button data-action="slow">250 ms work</button>
      <button data-action="fail">Intentional failure</button>
    </main>
    <script src="app.js"></script>
  </body>
</html>
```

Target: `app/frontend/app.js`

```javascript
const API = "http://127.0.0.1:8000";
const healthElement = document.querySelector("#health");
const resultElement = document.querySelector("#result");

async function callApi(path, options = {}) {
  // TODO 1: Fetch API + path with the supplied options.
  const response = ...;
  const requestId = response.headers.get("X-Request-ID");
  const body = response.status === 204 ? null : await response.json();
  return { status: response.status, requestId, body };
}

async function runAction(action) {
  try {
    let result;
    if (action === "health") {
      // TODO 2: Call both health endpoints and display their status codes.
      ...
      return;
    }
    if (action === "visits") result = await callApi("/api/v1/visits");
    if (action === "normal") result = await callApi("/api/v1/work");
    if (action === "slow") result = await callApi("/api/v1/work?delay_ms=250");
    if (action === "fail") result = await callApi("/api/v1/work?fail=true");
    resultElement.textContent = JSON.stringify(result, null, 2);
  } catch (error) {
    resultElement.textContent = `Network error: ${error.message}`;
  }
}

document.querySelectorAll("button[data-action]").forEach((button) => {
  button.addEventListener("click", () => runAction(button.dataset.action));
});
```

Write a small `styles.css` yourself. It only needs readable spacing, a constrained content width, clear buttons, and preserved whitespace in the result area.

<details>
<summary>Reference answers for JavaScript</summary>

```javascript
const response = await fetch(`${API}${path}`, options);

const live = await callApi("/health/live");
const ready = await callApi("/health/ready");
healthElement.textContent = `live=${live.status} ready=${ready.status}`;
```

</details>

Checkpoint:

```bash
cd /Users/m3/Desktop/k8slab
python3 -m http.server 8080 --directory app/frontend
```

Open `http://127.0.0.1:8080`, use every button, and inspect one request in the browser network panel. Stop Redis and prove the page can distinguish live from ready.

## Lesson 9 — Tests with a fake dependency

Tests should not require Redis unless explicitly marked as integration tests. The fake exercises the dependency contract and makes failure deterministic.

Target: `app/api/tests/conftest.py`

```python
import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from reliability_api.main import app
from reliability_api.redis_client import get_redis_client


class FakeRedis:
    def __init__(self) -> None:
        self.healthy = True
        self.visits = 0

    async def ping(self) -> bool:
        # TODO 1: Raise when unhealthy; otherwise return True.
        ...

    async def increment_visits(self) -> int:
        # TODO 2: Raise when unhealthy; otherwise increment and return visits.
        ...

    async def reset_visits(self) -> None:
        self.visits = 0


@pytest.fixture
def api_client():
    fake = FakeRedis()
    app.dependency_overrides[get_redis_client] = lambda: fake
    with TestClient(app) as client:
        yield client, fake
    app.dependency_overrides.clear()
```

Target: `app/api/tests/test_health.py`

```python
def test_liveness_ignores_redis_failure(api_client):
    client, fake = api_client
    fake.healthy = False
    response = client.get("/health/live")
    # TODO 3: Assert 200 and status live.


def test_readiness_reports_redis_failure(api_client):
    client, fake = api_client
    fake.healthy = False
    response = client.get("/health/ready")
    # TODO 4: Assert 503 and redis down.
```

Target: `app/api/tests/test_requests.py`

```python
def test_visits_increment(api_client):
    client, _ = api_client
    first = client.get("/api/v1/visits")
    second = client.get("/api/v1/visits")
    # TODO 5: Prove the counts are 1 and 2.


def test_valid_request_id_is_echoed(api_client):
    client, _ = api_client
    response = client.get(
        "/health/live",
        headers={"X-Request-ID": "phase2-test-001"},
    )
    # TODO 6: Prove the response header contains the supplied value.
```

<details>
<summary>Progressive hints</summary>

- Raise `RedisConnectionError("fake Redis unavailable")` when unhealthy.
- Inspect `response.status_code`, `response.json()`, and `response.headers`.
- Keep each test focused on one behavior.

</details>

<details>
<summary>Reference answers</summary>

```python
async def ping(self) -> bool:
    if not self.healthy:
        raise RedisConnectionError("fake Redis unavailable")
    return True

async def increment_visits(self) -> int:
    if not self.healthy:
        raise RedisConnectionError("fake Redis unavailable")
    self.visits += 1
    return self.visits

assert response.status_code == 200
assert response.json()["status"] == "live"

assert response.status_code == 503
assert response.json()["dependencies"]["redis"] == "down"

assert first.json()["visits"] == 1
assert second.json()["visits"] == 2

assert response.headers["X-Request-ID"] == "phase2-test-001"
```

</details>

Continue with the complete test inventory in Section 17 of `docs/02-demo-application.md`. Add at least these learner-owned cases:

- an invalid request ID is replaced;
- a Redis failure returns a safe 503 response;
- delay bounds reject negative values and values above 2000;
- failure controls are forbidden when disabled;
- metrics do not contain request IDs.

Run:

```bash
cd /Users/m3/Desktop/k8slab/app/api
source .venv/bin/activate
pytest -q
```

Do not weaken an assertion to make it pass. Compare the implementation with the authoritative application contract first.

## Code-lab completion checkpoint

```bash
cd /Users/m3/Desktop/k8slab
rg -n 'TODO|\.\.\.' app/api/reliability_api app/api/tests app/frontend
cd app/api
source .venv/bin/activate
python -m pip check
pytest -q
```

Review every search match. An intentional ellipsis in text or typing is fine; unfinished application behavior is not.

Return to Section 18 of `docs/02-demo-application.md` for complete local operation, failure injection, Redis outage diagnosis, recovery, and the Phase 2 gate.
