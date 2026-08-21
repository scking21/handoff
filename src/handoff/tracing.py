"""Optional OpenTelemetry wiring, enabled only when HANDOFF_OTEL is truthy.

Flag off (default): this module imports nothing beyond the stdlib and changes
no behavior. Flag on: installs a global TracerProvider, which is all Strands
needs — strands.telemetry reads trace_api.get_tracer_provider() and emits
agent/tool spans through it. Missing opentelemetry packages degrade to a
warning instead of crashing; the SDK itself ships transitively with
strands-agents, only the OTLP exporter is an extra.
"""

from __future__ import annotations

import os
import warnings

_TRUTHY = {"1", "true", "yes", "on"}


def tracing_enabled() -> bool:
    return os.getenv("HANDOFF_OTEL", "").strip().lower() in _TRUTHY


def configure_tracing(service_name: str | None = None):
    """Install the global TracerProvider when enabled. Returns the provider,
    or None when tracing stays off (flag unset or packages unavailable)."""
    if not tracing_enabled():
        return None
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        warnings.warn(f"HANDOFF_OTEL=1 but OpenTelemetry SDK unavailable ({exc}); tracing disabled")
        return None

    service = service_name or os.getenv("HANDOFF_OTEL_SERVICE_NAME", "handoff")
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(BatchSpanProcessor(_span_exporter()))
    trace.set_tracer_provider(provider)
    return provider


def _span_exporter():
    choice = os.getenv("HANDOFF_OTEL_EXPORTER", "otlp").strip().lower()
    if choice != "console":
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        except ImportError:
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            except ImportError:
                warnings.warn(
                    "no OTLP exporter installed"
                    " (pip install opentelemetry-exporter-otlp-proto-grpc);"
                    " falling back to ConsoleSpanExporter"
                )
            else:
                return OTLPSpanExporter()
        else:
            return OTLPSpanExporter()
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter

    return ConsoleSpanExporter()
