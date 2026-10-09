const API = "";

const livenessElement = document.querySelector("#liveness");
const readinessElement = document.querySelector("#readiness");
const resultElement = document.querySelector("#result");
const actionButtons = document.querySelectorAll("button[data-action]");

async function callApi(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    cache: "no-store",
    ...options,
  });
  const requestId = response.headers.get("X-Request-ID");
  const text = response.status === 204 ? "" : await response.text();

  let body = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = { message: "The API returned a non-JSON response" };
    }
  }

  return {
    ok: response.ok,
    status: response.status,
    requestId,
    body,
  };
}

function setHealth(element, label, result) {
  element.textContent = `${label}: HTTP ${result.status}`;
  element.className = `status ${result.ok ? "healthy" : "unhealthy"}`;
}

function showResult(result) {
  resultElement.textContent = JSON.stringify(result, null, 2);
}

async function runAction(action) {
  actionButtons.forEach((button) => {
    button.disabled = true;
  });

  try {
    if (action === "health") {
      const [live, ready] = await Promise.all([
        callApi("/health/live"),
        callApi("/health/ready"),
      ]);
      setHealth(livenessElement, "Liveness", live);
      setHealth(readinessElement, "Readiness", ready);
      showResult({ live, ready });
      return;
    }

    const paths = {
      visits: "/api/v1/visits",
      normal: "/api/v1/work",
      slow: "/api/v1/work?delay_ms=250",
      fail: "/api/v1/work?fail=true",
    };
    showResult(await callApi(paths[action]));
  } catch (error) {
    showResult({
      status: "network_error",
      message: error.message,
    });
  } finally {
    actionButtons.forEach((button) => {
      button.disabled = false;
    });
  }
}

actionButtons.forEach((button) => {
  button.addEventListener("click", () => runAction(button.dataset.action));
});
