"""Strands-native observability: hook callbacks that trace every tool call.

Registered on the CoordinatorAgent via the HookRegistry; writes a JSONL trace
alongside the ticket store. This is the seam OpenTelemetry export replaces in
production — same events, different sink.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from strands.hooks import AfterToolCallEvent, BeforeToolCallEvent, HookProvider, HookRegistry


class ToolTraceHook(HookProvider):
    def __init__(self, path: str | Path = "data/runtime/tool_trace.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._starts: dict[str, float] = {}

    def register_hooks(self, registry: HookRegistry, **kwargs) -> None:
        registry.add_callback(BeforeToolCallEvent, self._before)
        registry.add_callback(AfterToolCallEvent, self._after)

    def _before(self, event: BeforeToolCallEvent) -> None:
        tu = event.tool_use
        self._starts[tu.get("toolUseId", "")] = time.time()

    def _after(self, event: AfterToolCallEvent) -> None:
        tu = event.tool_use
        duration_ms = int((time.time() - self._starts.pop(tu.get("toolUseId", ""), time.time())) * 1000)
        record = {
            "ts": time.time(),
            "tool": tu.get("name"),
            "input": tu.get("input"),
            "duration_ms": duration_ms,
            "error": str(event.exception) if event.exception else None,
        }
        with self.path.open("a") as f:
            f.write(json.dumps(record, default=str) + "\n")
