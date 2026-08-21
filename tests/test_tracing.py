"""HANDOFF_OTEL flag contract: off means zero imports and no behavior change;
on means a global TracerProvider Strands will emit through; missing packages
warn instead of crash."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from handoff.tracing import configure_tracing, tracing_enabled

PROBE = """
import json, sys
from handoff.tracing import configure_tracing
provider = configure_tracing(service_name="handoff-test")
from opentelemetry import trace
print(json.dumps({
    "configured": provider is not None,
    "global_set": provider is not None and trace.get_tracer_provider() is provider,
}))
"""

ZERO_IMPORT_PROBE = """
import json, sys
from handoff.tracing import configure_tracing
configured = configure_tracing() is not None
print(json.dumps({
    "configured": configured,
    "otel_loaded": any(m.startswith("opentelemetry") for m in sys.modules),
}))
"""


def _run_probe(script: str, **env_overrides) -> dict:
    env = {k: v for k, v in os.environ.items() if k != "HANDOFF_OTEL"}
    env.update(env_overrides)
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_flag_off_is_a_noop(monkeypatch):
    monkeypatch.delenv("HANDOFF_OTEL", raising=False)
    assert tracing_enabled() is False
    assert configure_tracing() is None


def test_flag_off_imports_zero_opentelemetry_modules():
    result = _run_probe(ZERO_IMPORT_PROBE)
    assert result == {"configured": False, "otel_loaded": False}


def test_flag_on_installs_global_tracer_provider():
    result = _run_probe(PROBE, HANDOFF_OTEL="1", HANDOFF_OTEL_EXPORTER="console")
    assert result == {"configured": True, "global_set": True}


def test_missing_sdk_warns_instead_of_crashing(monkeypatch):
    monkeypatch.setenv("HANDOFF_OTEL", "1")
    monkeypatch.setitem(sys.modules, "opentelemetry", None)
    with pytest.warns(UserWarning, match="OpenTelemetry SDK unavailable"):
        assert configure_tracing() is None


def test_otlp_exporter_missing_falls_back_with_warning(monkeypatch):
    monkeypatch.setenv("HANDOFF_OTEL", "1")
    monkeypatch.setitem(sys.modules, "opentelemetry.exporter", None)
    with pytest.warns(UserWarning, match="OTLP exporter"):
        exporter = __import__("handoff.tracing", fromlist=["_span_exporter"])._span_exporter()
    assert type(exporter).__name__ == "ConsoleSpanExporter"
