# Stage 1: prepare verified Python packages.
FROM python:3.14.8-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83 AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY requirements.lock .

RUN python -m pip wheel \
    --require-hashes \
    --wheel-dir /wheels \
    --requirement requirements.lock


# Stage 2: create the actual runtime image.
FROM python:3.14.8-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83 AS runtime

ARG VERSION=dev
ARG REVISION=unknown
ARG SOURCE=https://github.com/MyoMyatMin/k8slab

LABEL org.opencontainers.image.title="k8slab-api" \
    org.opencontainers.image.version="${VERSION}" \
    org.opencontainers.image.revision="${REVISION}" \
    org.opencontainers.image.source="${SOURCE}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Create a dedicated non-root identity.
RUN groupadd --gid 10001 app \
    && useradd \
    --uid 10001 \
    --gid 10001 \
    --no-create-home \
    --home-dir /nonexistent \
    --shell /usr/sbin/nologin \
    app

# Install only the verified artifacts prepared by the builder.
COPY --from=builder /wheels /wheels
COPY requirements.lock .

RUN python -m pip install \
    --no-index \
    --find-links=/wheels \
    --require-hashes \
    --requirement requirements.lock \
    && rm -rf /wheels requirements.lock

# Copy application code after dependencies for better layer caching.
COPY --chown=10001:10001 reliability_api/ ./reliability_api/

USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "reliability_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
