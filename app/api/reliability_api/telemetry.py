from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

from reliability_api.config import Settings


def configure_telemetry(app: FastAPI, settings: Settings) -> TracerProvider:
    resource = Resource.create(
        {
            "service.name": settings.app_name,
            "service.version": settings.app_version,
            "deployment.environment.name": settings.app_environment,
        }
    )
    provider = TracerProvider(resource=resource)

    if settings.otel_console_exporter:
        provider.add_span_processor(
            SimpleSpanProcessor(ConsoleSpanExporter())
        )

    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="health/live,health/ready,metrics",
    )
    RedisInstrumentor().instrument()
    return provider
