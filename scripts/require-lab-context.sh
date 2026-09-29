#!/usr/bin/env bash

set -u

expected_context="kind-k8slab"

if ! command -v kubectl >/dev/null 2>&1; then
  printf 'BLOCKED: kubectl is not installed or not on PATH.\n' >&2
  exit 1
fi

current_context="$(kubectl config current-context 2>/dev/null || true)"

if [[ "${current_context}" != "${expected_context}" ]]; then
  printf 'BLOCKED: expected Kubernetes context %s, but current context is %s.\n' \
    "${expected_context}" "${current_context:-unset}" >&2
  exit 1
fi

printf 'SAFE: current Kubernetes context is %s.\n' "${current_context}"
