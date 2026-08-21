"""A deterministic Model that drives the real Strands agent loop offline.

Emits Bedrock-style streaming chunks from a policy function that reads the
conversation, so the Coordinator Agent's full loop — tool calls, tool results,
hooks, stop reasons — executes genuinely in CI and demos without AWS
credentials. Setting HANDOFF_MODEL_PROVIDER=bedrock swaps the brain, not the
body.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncIterable
from typing import Any

from handoff.agents.decisions import HeuristicTriageProvider
from strands.event_loop.streaming import process_stream
from strands.models.model import Model
from strands.types.tools import ToolSpec


def _chunks_for_text(text: str) -> list[dict[str, Any]]:
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockDelta": {"delta": {"text": text}}},
        {"contentBlockStop": {}},
        {"messageStop": {"stopReason": "end_turn"}},
        {"metadata": {"usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
                      "metrics": {"latencyMs": 1}}},
    ]


def _chunks_for_tool_use(name: str, tool_input: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockStart": {"start": {"toolUse": {"toolUseId": f"tu_{uuid.uuid4().hex[:8]}", "name": name}}}},
        {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(tool_input)}}}},
        {"contentBlockStop": {}},
        {"messageStop": {"stopReason": "tool_use"}},
        {"metadata": {"usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
                      "metrics": {"latencyMs": 1}}},
    ]


def _collect(messages: list[dict]) -> tuple[dict[str, str], set[str], str]:
    """Return (toolUseId -> result text, executed tool names, first user text)."""
    results: dict[str, str] = {}
    called: set[str] = set()
    first_user = ""
    for msg in messages:
        for block in msg.get("content", []):
            if "toolUse" in block:
                called.add(block["toolUse"]["name"])
            elif "toolResult" in block:
                tr = block["toolResult"]
                text = "".join(c.get("text", "") for c in tr.get("content", []))
                results[tr["toolUseId"]] = text
            elif "text" in block and msg.get("role") == "user" and not first_user:
                first_user = block["text"]
    return results, called, first_user


def _vendor_score(v: dict) -> float:
    return v["rating"] * 12 - v["drive_minutes"] * 0.15 - v["open_jobs"] * 3 - v["no_show_count"] * 5


class ScriptedModelProvider(Model):
    """Deterministic stand-in brain implementing the coordinator POLICY."""

    def __init__(self, approval_threshold: int = 400):
        self.approval_threshold = approval_threshold
        self.triage = HeuristicTriageProvider()
        self.config: dict[str, Any] = {"model_id": "handoff-scripted"}

    # -- Model interface --------------------------------------------------

    def update_config(self, **kwargs: Any) -> None:
        self.config.update(kwargs)

    def get_config(self) -> dict[str, Any]:
        return self.config

    @staticmethod
    def _parse_brief(first_user: str) -> tuple[str, str]:
        tid_m = re.search(r"ticket_id:\s*(\S+)", first_user)
        raw_m = re.search(r"tenant report:\s*(.+)", first_user, re.S)
        ticket_id = tid_m.group(1) if tid_m else ""
        raw = raw_m.group(1).strip() if raw_m else ""
        return ticket_id, raw

    async def stream(
        self,
        messages: list[dict],
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[dict[str, Any]]:
        results, called, first_user = _collect(messages)
        ticket_id, raw = self._parse_brief(first_user)

        # ONE action per model response. Real models batch tool calls and the
        # executor may run them concurrently; a scripted brain that batches
        # would reintroduce exactly the race the atomic store prevents.
        done_text = f"Ticket {ticket_id} handled: triaged, priced, and dispatched or gated per policy."
        decision = self.triage.classify(raw, [])
        turns: list[list[dict[str, Any]]] = []
        if "lookup_ticket_context" not in called:
            turns.append(_chunks_for_tool_use("lookup_ticket_context", {"ticket_id": ticket_id}))
        elif "apply_triage" not in called:
            turns.append(_chunks_for_tool_use("apply_triage", {
                "ticket_id": ticket_id,
                "urgency": decision.urgency.value,
                "category": decision.category.value,
                "confidence": decision.confidence,
                "rationale": decision.rationale,
            }))
        elif "search_vendors" not in called:
            turns.append(_chunks_for_tool_use("search_vendors", {"trade": decision.category.value}))
        elif not any(name.startswith("request_quote") for name in called):
            vendors: list[dict] = []
            for text in results.values():
                if text.startswith("[{"):
                    vendors = json.loads(text)
                    break
            if not vendors:
                turns.append(_chunks_for_tool_use(
                    "escalate_to_human",
                    {"ticket_id": ticket_id, "reason": f"no vendors cover {decision.category.value}"},
                ))
            else:
                best_vendor = sorted(vendors, key=_vendor_score, reverse=True)[0]
                turns.append(_chunks_for_tool_use(
                    "request_quote",
                    {
                        "ticket_id": ticket_id,
                        "vendor_id": best_vendor["id"],
                        "urgency": decision.urgency.value,
                        "idem_key": f"{ticket_id}:quote:{best_vendor['id']}",
                    },
                ))
        elif (
            "dispatch_work_order" not in called
            and "create_approval_gate" not in called
            and "escalate_to_human" not in called
        ):
            quotes = []
            for text in results.values():
                try:
                    q = json.loads(text)
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(q, dict) and "vendor_id" in q and "amount" in q:
                    quotes.append(q)
            best = min(quotes, key=lambda q: q["amount"]) if quotes else None
            if best is None:
                turns.append(_chunks_for_tool_use(
                    "escalate_to_human",
                    {"ticket_id": ticket_id, "reason": "no quotes returned"},
                ))
            elif best["amount"] > self.approval_threshold:
                turns.append(_chunks_for_tool_use(
                    "create_approval_gate",
                    {
                        "ticket_id": ticket_id,
                        "reason": f"Quoted ${best['amount']} exceeds ${self.approval_threshold} threshold",
                        "est_cost": best["amount"],
                        "idem_key": f"{ticket_id}:gate",
                        "vendor_id": best["vendor_id"],
                    },
                ))
            else:
                turns.append(_chunks_for_tool_use(
                    "dispatch_work_order",
                    {
                        "ticket_id": ticket_id,
                        "vendor_id": best["vendor_id"],
                        "scope": f"repair per ticket {ticket_id}",
                        "cost": best["amount"],
                        "idem_key": f"{ticket_id}:dispatch:{best['vendor_id']}",
                    },
                ))
        elif "dispatch_work_order" in called and "message_tenant" not in called:
            # dispatched last cycle; the tenant update gets its own cycle
            turns.append(_chunks_for_tool_use(
                "message_tenant",
                {
                    "ticket_id": ticket_id,
                    "kind": "update",
                    "body": "Update: a vendor is assigned and confirming an arrival window.",
                    "idem_key": f"{ticket_id}:assigned_update",
                },
            ))
        else:
            turns.append(_chunks_for_text(done_text))

        # Yield RAW Bedrock-style chunks: the agent loop applies
        # process_stream() itself. Wrapping here would double-process.
        for turn in turns:
            for chunk in turn:
                yield chunk

    async def structured_output(self, output_model, prompt, system_prompt=None, **kwargs):
        """Mirror the Bedrock implementation: force a tool call carrying the payload."""
        from strands.tools import convert_pydantic_to_tool_spec

        tool_spec = convert_pydantic_to_tool_spec(output_model)
        name = tool_spec["name"]
        decision = self.triage.classify(str(prompt), [])
        payload = {
            "urgency": decision.urgency.value,
            "category": decision.category.value,
            "confidence": decision.confidence,
            "rationale": decision.rationale,
        }

        async def gen():
            for chunk in _chunks_for_tool_use(name, payload):
                yield chunk

        last_event = None
        async for event in process_stream(gen(), start_time=0.0):
            last_event = event
            yield event
        stop_reason, msgs, _, _ = last_event["stop"]
        output = None
        for block in msgs["content"]:
            if block.get("toolUse") and block["toolUse"]["name"] == name:
                output = block["toolUse"]["input"]
        yield {"output": output_model(**output)}
