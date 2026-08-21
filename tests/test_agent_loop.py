"""Full-loop test: the Coordinator Agent runs the REAL Strands event loop with
the ScriptedModelProvider brain — tool calls, tool results, hooks, stop reasons
all genuine. Only the model weights are deterministic."""

from __future__ import annotations

import json

import pytest

from handoff.agents.audit_hook import ToolTraceHook
from handoff.agents.coordinator import CoordinatorAgent
from handoff.agents.scripted_model import ScriptedModelProvider
from handoff.data.synth.generate import make_request, seed_world
from handoff.domain.models import TicketStatus, Urgency
from handoff.workflow import engine
from handoff.store.base import FileStore
from handoff.tools.toolkit import HandoffTools


@pytest.fixture()
def world(tmp_path):
    store = FileStore(root=tmp_path / "runtime")
    tenants = seed_world(store)
    tools = HandoffTools(store, approval_threshold=400)
    model = ScriptedModelProvider(approval_threshold=tools.approval_threshold)
    hook = ToolTraceHook(path=tmp_path / "trace.jsonl")
    coordinator = CoordinatorAgent(tools, model=model, trace_hook=hook)
    return store, tools, tenants, coordinator, tmp_path


def test_coordinator_full_loop_dispatches_under_threshold(world):
    store, tools, tenants, coordinator, tmp_path = world
    payload = make_request(store, "dripping_faucet", tenant=tenants[0])
    t = engine.intake_request(store, tools, payload)

    coordinator.handle_request(
        {"ticket_id": t.id, "unit": t.unit, "raw": t.raw_request, "photos": []}
    )

    final = store.get_ticket(t.id)
    assert final.status == TicketStatus.DISPATCHED
    assert final.selected_vendor_id
    assert final.authorized_cost is not None and final.authorized_cost <= 400
    # tenant ack (deterministic intake) + agent's update message both present
    kinds = [m.kind for m in store.list_messages(t.id)]
    assert "ack" in kinds and "update" in kinds
    # exactly one dispatch offer — idempotency held inside the real loop
    offers = [m for m in store.list_messages(t.id) if m.kind == "dispatch_offer"]
    assert len(offers) == 1
    # Strands hooks traced every tool call
    lines = [json.loads(l) for l in (tmp_path / "trace.jsonl").read_text().splitlines()]
    tools_traced = {r["tool"] for r in lines}
    assert {"lookup_ticket_context", "search_vendors", "request_quote", "dispatch_work_order"} <= tools_traced


def test_coordinator_full_loop_gates_over_threshold(world):
    store, tools, tenants, coordinator, _ = world
    payload = make_request(store, "midnight_flood", tenant=tenants[0])
    t = engine.intake_request(store, tools, payload)

    coordinator.handle_request(
        {"ticket_id": t.id, "unit": t.unit, "raw": t.raw_request, "photos": ["water from ceiling"]}
    )

    final = store.get_ticket(t.id)
    assert final.status == TicketStatus.AWAITING_APPROVAL
    assert final.pending_vendor_id  # exact dispatch persisted for durable resume
    assert final.urgency == Urgency.EMERGENCY
