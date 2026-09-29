#!/usr/bin/env bash

set -u

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd "${script_dir}/.." && pwd)"

# The repository controls this file. It contains version strings only.
# shellcheck source=../versions.env
source "${project_dir}/versions.env"

failures=0

pass() {
  printf 'PASS  %s\n' "$1"
}

fail() {
  printf 'FAIL  %s\n' "$1"
  failures=$((failures + 1))
}

info() {
  printf 'INFO  %s\n' "$1"
}

require_command() {
  local command_name="$1"
  if command -v "${command_name}" >/dev/null 2>&1; then
    pass "${command_name} found at $(command -v "${command_name}")"
  else
    fail "${command_name} is not installed or not on PATH"
  fi
}

expect_version() {
  local tool_name="$1"
  local expected="$2"
  local detected="$3"

  if [[ "${detected}" == *"${expected}"* ]]; then
    pass "${tool_name} ${expected}"
  else
    fail "${tool_name}: expected ${expected}; detected ${detected:-unknown}"
  fi
}

printf 'Kubernetes Reliability Platform prerequisite check\n'
printf 'Project: %s\n\n' "${project_dir}"

for command_name in git orb docker kubectl kind helm kustomize sops age k6 jq yq gh; do
  require_command "${command_name}"
done

printf '\nPinned tool versions\n'

if command -v kubectl >/dev/null 2>&1; then
  detected="$(kubectl version --client=true --output=yaml 2>/dev/null | awk '/gitVersion:/ {print $2; exit}')"
  expect_version kubectl "${KUBECTL_VERSION}" "${detected}"
fi

if command -v kind >/dev/null 2>&1; then
  detected="$(kind version 2>/dev/null | awk '{print $2}')"
  expect_version kind "${KIND_VERSION}" "${detected}"
fi

if command -v helm >/dev/null 2>&1; then
  detected="$(helm version --short 2>/dev/null)"
  expect_version helm "${HELM_VERSION}" "${detected}"
fi

if command -v kustomize >/dev/null 2>&1; then
  detected="$(kustomize version 2>/dev/null)"
  expect_version kustomize "${KUSTOMIZE_VERSION}" "${detected}"
fi

if command -v sops >/dev/null 2>&1; then
  detected="$(sops --version 2>/dev/null | head -n 1)"
  expect_version sops "${SOPS_VERSION}" "${detected}"
fi

if command -v age >/dev/null 2>&1; then
  detected="$(age --version 2>/dev/null)"
  expect_version age "${AGE_VERSION}" "${detected}"
fi

if command -v k6 >/dev/null 2>&1; then
  detected="$(k6 version 2>/dev/null | head -n 1)"
  expect_version k6 "${K6_VERSION}" "${detected}"
fi

if command -v jq >/dev/null 2>&1; then
  detected="$(jq --version 2>/dev/null)"
  expect_version jq "${JQ_VERSION}" "${detected}"
fi

if command -v yq >/dev/null 2>&1; then
  detected="$(yq --version 2>/dev/null)"
  expect_version yq "${YQ_VERSION}" "${detected}"
fi

printf '\nContainer runtime\n'

if command -v orb >/dev/null 2>&1; then
  detected="$(orb version 2>/dev/null | awk '/^Version:/ {print $2; exit}')"
  expect_version OrbStack "${ORBSTACK_VERSION}" "${detected}"
fi

if command -v docker >/dev/null 2>&1; then
  info "Docker context: $(docker context show 2>/dev/null || printf 'unknown')"
  if docker info >/dev/null 2>&1; then
    pass 'Docker-compatible engine is reachable'
  else
    fail 'Docker CLI exists but the engine is not reachable; run docker info directly for details'
  fi
fi

printf '\nHost capacity\n'

available_kib="$(df -Pk "${project_dir}" | awk 'NR == 2 {print $4}')"
minimum_kib=$((40 * 1024 * 1024))
available_gib=$((available_kib / 1024 / 1024))

if ((available_kib >= minimum_kib)); then
  pass "${available_gib} GiB disk space available (minimum 40 GiB)"
else
  fail "${available_gib} GiB disk space available; free at least 40 GiB before cluster creation"
fi

printf '\nKubernetes context safety\n'

if command -v kubectl >/dev/null 2>&1; then
  current_context="$(kubectl config current-context 2>/dev/null || true)"
  if [[ -n "${current_context}" ]]; then
    info "Current context: ${current_context}"
  else
    info 'No current Kubernetes context; this is acceptable before Phase 4'
  fi
fi

printf '\n'
if ((failures == 0)); then
  pass 'Phase 1 automated prerequisite checks passed'
  exit 0
fi

fail "${failures} prerequisite check(s) need attention"
exit 1
