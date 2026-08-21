"""End-to-end pipeline: request in, dispatched-or-escalated ticket out."""

from __future__ import annotations

from handoff.agents.decisions import TriageProvider
from handoff.domain.models import TicketStatus, WorkOrder
from handoff.store.base import Store
from handoff.tools.toolkit import HandoffTools
from handoff.workflow import engine


def run_request(
    store: Store,
    tools: HandoffTools,
    triage: TriageProvider,
    payload: dict,
    after_hours: bool = False,
) -> WorkOrder:
    """Full intake path. Returns the ticket in whatever state the policy lands it:
    DISPATCHED (auto), AWAITING_APPROVAL (gate), or EXCEPTION (human queue)."""
    t = engine.intake_request(store, tools, payload)

    decision = triage.classify(payload["raw"], payload.get("photos", []))
    engine.apply_triage(tools, t.id, decision)

    t = store.get_ticket(t.id)
    if t.status != TicketStatus.TRIAGED:
        return t  # escalated at triage

    candidates = [v.model_dump() for v in store.list_vendors(decision.category.value)]
    choice = engine.select_vendor(candidates, decision.category, decision.urgency)
    if not choice:
        tools.escalate_to_human(t.id, f"no vendor covers {decision.category.value}")
        return store.get_ticket(t.id)

    # ask the bench for quotes so the record shows price discovery
    for vid in [choice.vendor_id, *choice.alternates][:3]:
        tools.request_quote(t.id, vid, decision.urgency.value, idem_key=f"{t.id}:quote:{vid}")

    # authorize against the actual quoted price, not the back-of-envelope estimate
    t = store.get_ticket(t.id)
    winning = next((q.amount for q in t.quotes if q.vendor_id == choice.vendor_id), None)
    if winning is not None:
        choice.estimated_cost = winning

    engine.gate_and_dispatch(tools, t.id, choice, after_hours=after_hours)
    return store.get_ticket(t.id)


def run_request_with_coordinator(store: Store, coordinator, payload: dict) -> WorkOrder:
    """Agent-driven path: a Strands Agent with tool access owns the ticket loop.
    Intake + tenant ack stay deterministic (guaranteed within 60s benchmark);
    the agent does triage through dispatch."""
    t = engine.intake_request(store, coordinator.tools, payload)
    coordinator.handle_request(
        {"ticket_id": t.id, "unit": t.unit, "raw": t.raw_request, "photos": t.photo_descriptions}
    )
    return store.get_ticket(t.id)


def _intake_only(store: Store, payload: dict) -> WorkOrder:
    from handoff.domain.models import Actor, WorkOrder

    t = WorkOrder(
        property_id=payload["property_id"],
        unit=payload["unit"],
        tenant_id=payload["tenant_id"],
        raw_request=payload["raw"],
        photo_descriptions=payload.get("photos", []),
    )
    store.put_ticket(t)
    t.record(Actor.TENANT, "request_received", payload["raw"][:80])
    store.put_ticket(t)
    return t
