"""Deterministic workflow engine.

Agents make *decisions* (classify, rank, draft); this engine applies them
through idempotent tools. The split means retries, crashes, and approval
waits can never corrupt a ticket's lifecycle — the same property AWS's
durable-workflow guidance calls "deterministic orchestration around
probabilistic reasoning".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from pydantic import BaseModel

from handoff.domain.models import Actor, TicketStatus, Trade, Urgency, WorkOrder
from handoff.tools.toolkit import HandoffTools, utcnow


class TriageDecision(BaseModel):
    """Pydantic (not dataclass): Strands structured_output requires
    model_json_schema for tool-spec conversion."""

    urgency: Urgency
    category: Trade
    confidence: float
    rationale: str = ""


@dataclass
class VendorChoice:
    vendor_id: str
    estimated_cost: int
    justification: str = ""
    alternates: list[str] = field(default_factory=list)


CONFIDENCE_FLOOR = 0.55  # below this, triage goes to a human instead of guessing


def intake_request(store, tools: HandoffTools, payload: dict) -> WorkOrder:
    """New request -> ticket + instant tenant acknowledgment (the #1 satisfaction lever)."""
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
    tools.message_tenant(
        t.id,
        "ack",
        (
            f"Got it — we've received your report about unit {t.unit} and it's in the queue now. "
            f"You'll hear back shortly with next steps. Reply here if anything changes."
        ),
        idem_key=f"{t.id}:ack",
    )
    return t


def apply_triage(tools: HandoffTools, ticket_id: str, decision: TriageDecision) -> str:
    """Apply classification. Low-confidence triage escalates rather than guesses."""
    t = _must(tools, ticket_id)
    t.category = decision.category
    t.urgency = decision.urgency
    t.triage_confidence = decision.confidence
    t.triage_rationale = decision.rationale
    t.status = TicketStatus.TRIAGED
    t.record(Actor.AGENT, "triaged", f"{decision.urgency.value}/{decision.category.value} conf={decision.confidence:.2f}")
    tools.store.put_ticket(t)
    if decision.confidence < CONFIDENCE_FLOOR:
        return tools.escalate_to_human(ticket_id, f"triage confidence {decision.confidence:.2f} below floor")
    return "TRIAGED"


def select_vendor(candidates: list[dict], category: Trade, urgency: Urgency) -> VendorChoice | None:
    """Score vendors via the per-urgency tiered policy in vendor_policy.
    Skill fit is guaranteed by the caller's trade filter; this ranks
    reliability, proximity, load and cost within it."""
    from handoff.workflow.vendor_policy import score_vendor, weights_for

    if not candidates:
        return None

    w = weights_for(urgency)

    def score(v: dict) -> float:
        return score_vendor(v, w, urgency)

    ranked = sorted(candidates, key=score, reverse=True)
    best = ranked[0]
    est = int(best["hourly_rate"] * 1.5 + best["trip_fee"])
    return VendorChoice(
        vendor_id=best["id"],
        estimated_cost=est,
        justification=(
            f"{best['company']}: rating {best['rating']}, {best['drive_minutes']}min out, "
            f"load {best['open_jobs']}, {'on-call' if best.get('on_call_now') else 'standard hours'}"
        ),
        alternates=[v["id"] for v in ranked[1:3]],
    )


def gate_and_dispatch(tools: HandoffTools, ticket_id: str, choice: VendorChoice, after_hours: bool = False) -> str:
    """Spend policy: above threshold or after-hours emergency needs PM approval.
    Otherwise dispatch immediately. Returns the resulting status transition."""
    t = _must(tools, ticket_id)
    needs_approval = choice.estimated_cost > tools.approval_threshold or (after_hours and t.urgency == Urgency.EMERGENCY)
    if needs_approval:
        # Persist the exact intended dispatch: the PM approves *this* vendor at
        # *this* price, and resume must replay exactly that — not a re-search.
        t.pending_vendor_id = choice.vendor_id
        tools.store.put_ticket(t)
        reason = (
            f"Estimated ${choice.estimated_cost} exceeds ${tools.approval_threshold} policy threshold"
            if choice.estimated_cost > tools.approval_threshold
            else f"After-hours emergency dispatch to {choice.vendor_id}"
        )
        return tools.create_approval_gate(
            ticket_id, reason, choice.estimated_cost, idem_key=f"{t.id}:gate", vendor_id=choice.vendor_id
        )
    return _dispatch(tools, ticket_id, choice)


def resume_after_approval(tools: HandoffTools, ticket_id: str, approve: bool) -> str:
    """PM decided; resume or park. Replays the exact dispatch that was gated."""
    tools.resolve_approval(ticket_id, "approve" if approve else "reject")
    if not approve:
        return "PARKED_FOR_PM"
    t = _must(tools, ticket_id)
    if not t.pending_vendor_id:
        return tools.escalate_to_human(ticket_id, "approval resumed but no pending vendor recorded")
    choice = VendorChoice(vendor_id=t.pending_vendor_id, estimated_cost=t.authorized_cost or 0)
    return _dispatch(tools, ticket_id, choice)


def _dispatch(tools: HandoffTools, ticket_id: str, choice: VendorChoice) -> str:
    t = _must(tools, ticket_id)
    scope = f"{t.category.value if t.category else 'general'} repair: {t.raw_request[:100]}"
    result = tools.dispatch_work_order(ticket_id, choice.vendor_id, scope, choice.estimated_cost, idem_key=f"{t.id}:dispatch:{choice.vendor_id}")
    if "REPLAYED" in result:
        return result
    tools.message_tenant(
        ticket_id,
        "update",
        "Good news — we've assigned a vendor and they're confirming a arrival window. We'll text you the time as soon as it's locked.",
        idem_key=f"{t.id}:assigned_update",
    )
    return result


def vendor_response(tools: HandoffTools, ticket_id: str, accept: bool, alternates: list[str] | None = None) -> str:
    """Vendor accepted (-> scheduling) or declined (-> re-route down the bench).
    Only a ticket actually awaiting vendor response may transition."""
    t = _must(tools, ticket_id)
    if t.status != TicketStatus.DISPATCHED:
        return f"IGNORED: ticket {t.id} not awaiting vendor response (status={t.status.value})"
    if accept:
        # Propose the earliest window from vendor ETA and lock it with the
        # tenant — a confirmed window is what kills no-access trips.
        eta_h = _selected_eta_hours(tools.store, t) or 24
        window_dt = utcnow() + timedelta(hours=eta_h)
        t.scheduled_window = window_dt.strftime("%a %b %d, %H:%M–%H:%M UTC")
        t.status = TicketStatus.SCHEDULED
        t.record(Actor.VENDOR, "accepted", f"window {t.scheduled_window}")
        tools.store.put_ticket(t)
        tools.message_tenant(
            t.id,
            "schedule_offer",
            f"Your repair is scheduled: {t.scheduled_window}. Reply here if that time doesn't work "
            f"and we'll rearrange.",
            idem_key=f"{t.id}:schedule_offer",
        )
        return "ACCEPTED"
    t.record(Actor.VENDOR, "declined", "")
    tools.store.put_ticket(t)
    for alt in alternates or []:
        res = tools.dispatch_work_order(
            t.id, alt, t.authorized_scope, t.authorized_cost or 0, idem_key=f"{t.id}:dispatch:{alt}"
        )
        if "REPLAYED" not in res and "REFUSED" not in res:
            return f"REROUTED: {alt}"
    return tools.escalate_to_human(t.id, "all candidate vendors declined")


def _selected_eta_hours(store, t: WorkOrder) -> int | None:
    if not t.selected_vendor_id:
        return None
    q = next((q for q in t.quotes if q.vendor_id == t.selected_vendor_id), None)
    return q.eta_hours if q else None


def tenant_rejects_fix(tools: HandoffTools, ticket_id: str, note: str = "") -> str:
    """Tenant says the problem persists after 'completion'. Reopen as urgent and
    route back to triage with full history — never silently close."""
    t = _must(tools, ticket_id)
    if t.status != TicketStatus.VERIFIED and t.status != TicketStatus.CLOSED:
        return f"IGNORED: ticket {t.id} not in a verified state (status={t.status.value})"
    t.status = TicketStatus.TRIAGED
    t.triage_confidence = 0.95  # history makes this high-confidence: same trade, repeat issue
    t.record(Actor.TENANT, "reopened", note or "issue persists after repair")
    tools.store.put_ticket(t)
    return tools.escalate_to_human(
        ticket_id,
        f"tenant reports the issue persists after repair ({t.category.value if t.category else '?'}) — "
        f"prior vendor may need re-dispatch",
    )


def complete_and_verify(tools: HandoffTools, ticket_id: str, notes: str, parts: list[str], invoice_amount: int) -> str:
    """Closeout: completion record, tenant verification ping, invoice three-way match.
    Only tickets in an active work state can complete — forged closeouts on
    untriaged or gated tickets are ignored."""
    t = _must(tools, ticket_id)
    if t.status not in (TicketStatus.SCHEDULED, TicketStatus.IN_PROGRESS):
        return f"IGNORED: ticket {t.id} not in an active work state (status={t.status.value})"
    t.completion_notes = notes
    t.parts_used = parts
    t.invoice_amount = invoice_amount
    t.status = TicketStatus.COMPLETED
    t.record(Actor.VENDOR, "completed", notes[:80])
    tools.store.put_ticket(t)

    authorized = t.authorized_cost or 0
    if invoice_amount > authorized * 1.1:  # >10% over authorization is a discrepancy
        return tools.escalate_to_human(
            ticket_id, f"invoice ${invoice_amount} exceeds authorized ${authorized}"
        )
    tools.message_tenant(
        ticket_id,
        "closeout_check",
        "Your repair was marked complete today. Can you confirm everything's working? If not, reply and we'll reopen it.",
        idem_key=f"{t.id}:closeout_check",
    )
    t.status = TicketStatus.CLOSED
    t.record(Actor.AGENT, "invoice_matched", f"${invoice_amount} vs authorized ${authorized}")
    tools.store.put_ticket(t)
    return "CLOSED"


def nightly_sweep(tools: HandoffTools) -> list[str]:
    """Background sweep: nudge stalled dispatches, remind pending approvals,
    escalate anything aging past its lane. Runs on a schedule; the PM sees
    only the exceptions summary."""
    actions: list[str] = []
    for t in tools.store.list_tickets():
        if t.status == TicketStatus.DISPATCHED:
            tools.message_vendor(t.id, "Checking on work order — can you confirm the arrival window?", idem_key=f"{t.id}:nudge:{t.stall_count}")
            t.stall_count += 1
            tools.store.put_ticket(t)
            actions.append(f"nudged vendor on {t.id}")
            if t.stall_count >= 3:
                actions.append(tools.escalate_to_human(t.id, "vendor unresponsive after 3 nudges"))
        elif t.status == TicketStatus.AWAITING_APPROVAL:
            age_hours = (utcnow() - t.updated_at).total_seconds() / 3600
            if age_hours >= 12:
                actions.append(f"approval still pending on {t.id} ({age_hours:.0f}h)")
    return actions


def _must(tools: HandoffTools, ticket_id: str) -> WorkOrder:
    t = tools.store.get_ticket(ticket_id)
    if not t:
        raise ValueError(f"no ticket {ticket_id}")
    return t


def _soft(tools: HandoffTools, ticket_id: str) -> WorkOrder | None:
    return tools.store.get_ticket(ticket_id)
