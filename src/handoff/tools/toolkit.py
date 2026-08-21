"""Custom Strands tools bound to a Store.

Every side-effecting action is idempotent (``idem_key`` replays return the
recorded outcome) and runs through ``store.update_ticket`` so concurrent tool
calls can never lose updates. These two guarantees are what make safe retries
possible when orchestration resumes after a crash or an approval wait.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

from handoff.domain.models import (
    Actor,
    ApprovalDecision,
    OutboundMessage,
    Quote,
    TicketStatus,
    Trade,
    Urgency,
    WorkOrder,
)
from handoff.store.base import Store


def _stable_jitter(*parts: str) -> float:
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF  # 0..1


URGENCY_MULTIPLIER = {Urgency.EMERGENCY: 1.8, Urgency.URGENT: 1.25, Urgency.ROUTINE: 1.0}

BASE_JOB_MINUTES = {
    Trade.PLUMBING: 120,
    Trade.HVAC: 150,
    Trade.ELECTRICAL: 90,
    Trade.APPLIANCE: 75,
    Trade.GENERAL: 60,
    Trade.LOCKSMITH: 30,
}


class HandoffTools:
    def __init__(self, store: Store, approval_threshold: int = 400):
        self.store = store
        self.approval_threshold = approval_threshold

    def all(self) -> list:
        """All tools, decorated for registration with a Strands Agent."""
        from strands.tools import tool as strand_tool

        return [strand_tool(fn) for fn in (
            self.lookup_ticket_context,
            self.apply_triage,
            self.search_vendors,
            self.request_quote,
            self.create_approval_gate,
            self.resolve_approval,
            self.dispatch_work_order,
            self.message_tenant,
            self.message_vendor,
            self.escalate_to_human,
            self.log_event,
        )]

    # ---------- read tools ----------

    def lookup_ticket_context(self, ticket_id: str) -> str:
        """Full context for a work order: request, status, tenant/unit info,
        prior history on the unit, and any quotes already gathered."""
        t = self.store.get_ticket(ticket_id)
        if not t:
            return f"ERROR: no ticket {ticket_id}"
        tenant = self.store.get_tenant(t.tenant_id)
        prior = [
            x
            for x in self.store.list_tickets()
            if x.id != t.id and x.property_id == t.property_id and x.unit == t.unit
        ]
        ctx = {
            "ticket": t.model_dump(include={
                "id", "status", "raw_request", "photo_descriptions", "urgency",
                "category", "quotes", "authorized_cost",
            }),
            "tenant": tenant.model_dump() if tenant else None,
            "prior_tickets_on_unit": len(prior),
            "prior_categories": [str(x.category.value) if x.category else None for x in prior[-5:]],
        }
        return json.dumps(ctx, default=str)

    def apply_triage(
        self, ticket_id: str, urgency: str, category: str, confidence: float, rationale: str = ""
    ) -> str:
        """Persist the triage decision on the ticket. Confidence below 0.55
        escalates to a human instead of acting — honesty over guessing."""
        def mut(t: WorkOrder):
            t.urgency = Urgency(urgency)
            t.category = Trade(category)
            t.triage_confidence = confidence
            t.triage_rationale = rationale
            if confidence < 0.55:
                t.status = TicketStatus.EXCEPTION
                t.stall_count += 1
                t.record(Actor.AGENT, "escalated", f"triage confidence {confidence:.2f} below floor")
                return f"ESCALATED: {t.id} — triage confidence {confidence:.2f} below floor"
            t.status = TicketStatus.TRIAGED
            t.record(Actor.AGENT, "triaged", f"{urgency}/{category} conf={confidence:.2f}")
            return f"TRIAGED: {t.id} as {urgency}/{category}"

        out = self.store.update_ticket(ticket_id, mut)
        return out if isinstance(out, str) else f"ERROR: no ticket {ticket_id}"

    def search_vendors(self, trade: str) -> str:
        """Vendors covering a trade, with rating, rate, drive time, load, on-call flag."""
        vendors = self.store.list_vendors(trade)
        rows = [
            v.model_dump(include={
                "id", "company", "rating", "hourly_rate", "trip_fee", "drive_minutes",
                "open_jobs", "on_call_now", "certifications", "no_show_count",
            })
            for v in vendors
        ]
        return json.dumps(rows)

    # ---------- write tools (atomic + idempotent) ----------

    @staticmethod
    def _check_idem(t: WorkOrder, idem_key: str) -> str | None:
        if idem_key in t.idempotency_keys:
            return f"REPLAYED: {idem_key} already applied to {t.id} — no action taken"
        t.idempotency_keys.add(idem_key)
        return None

    def request_quote(self, ticket_id: str, vendor_id: str, urgency: str, idem_key: str) -> str:
        """Get a price/ETA quote from a vendor for this ticket. Deterministic per
        (vendor, ticket) so retries are stable."""
        v = next((x for x in self.store.list_vendors() if x.id == vendor_id), None)
        if not v:
            return f"ERROR: no vendor {vendor_id}"

        def mut(t: WorkOrder):
            replayed = self._check_idem(t, idem_key)
            if replayed:
                return replayed
            minutes = BASE_JOB_MINUTES.get(Trade(t.category.value) if t.category else Trade.GENERAL, 90)
            jitter = 0.85 + 0.4 * _stable_jitter(vendor_id, ticket_id)
            amount = int(
                (v.hourly_rate * minutes / 60 + v.trip_fee) * URGENCY_MULTIPLIER[Urgency(urgency)] * jitter
            )
            eta = max(2, int(v.drive_minutes / 30 * 2 + (24 if not v.on_call_now else 3)))
            q = Quote(vendor_id=vendor_id, amount=amount, eta_hours=eta, notes=f"quote by {v.company}")
            t.quotes = [x for x in t.quotes if x.vendor_id != vendor_id] + [q]
            t.record(Actor.AGENT, "quote_requested", f"{v.company}: ${amount}, ETA {eta}h")
            return json.dumps(q.model_dump(mode="json"))

        out = self.store.update_ticket(ticket_id, mut)
        return out if isinstance(out, str) else (f"ERROR: no ticket {ticket_id}" if out is None else out)

    def create_approval_gate(
        self, ticket_id: str, reason: str, est_cost: int, idem_key: str, vendor_id: str = ""
    ) -> str:
        """Pause the ticket pending property-manager approval. Durable: stays
        AWAITING_APPROVAL until resolve_approval is called. The intended
        dispatch (vendor + price) is persisted at gate time so a decision made
        hours later resumes exactly this action — not a re-search."""
        def mut(t: WorkOrder):
            replayed = self._check_idem(t, idem_key)
            if replayed:
                return replayed
            t.status = TicketStatus.AWAITING_APPROVAL
            t.authorized_scope = reason
            t.authorized_cost = est_cost
            if vendor_id:
                t.pending_vendor_id = vendor_id
            t.record(Actor.AGENT, "approval_gate_created", f"{reason} (${est_cost})")
            return f"APPROVAL_GATE_CREATED: ticket {t.id} paused awaiting PM decision"

        out = self.store.update_ticket(ticket_id, mut)
        if not isinstance(out, str):
            return f"ERROR: no ticket {ticket_id}"
        if out.startswith("APPROVAL_GATE_CREATED"):
            t = self.store.get_ticket(ticket_id)
            self.store.record_message(OutboundMessage(
                ticket_id=ticket_id, to_role=Actor.PM, to_id="pm", channel="push",
                kind="approval_request",
                body=f"Approval needed (${est_cost}): {reason}. Ticket {ticket_id}.",
            ))
        return out

    def resolve_approval(self, ticket_id: str, decision: str, note: str = "") -> str:
        """Apply the property manager's decision ('approve'/'reject')."""
        def mut(t: WorkOrder):
            if t.status != TicketStatus.AWAITING_APPROVAL:
                return f"IGNORED: ticket {t.id} not awaiting approval (status={t.status.value})"
            t.approval = ApprovalDecision(decision=decision, note=note)
            t.status = TicketStatus.TRIAGED if decision == "approve" else TicketStatus.EXCEPTION
            t.record(Actor.PM, "approval_decided", f"{decision}: {note}")
            return f"APPROVAL_{decision.upper()}: ticket {t.id} resumed"

        out = self.store.update_ticket(ticket_id, mut)
        return out if isinstance(out, str) else f"ERROR: no ticket {ticket_id}"

    def dispatch_work_order(self, ticket_id: str, vendor_id: str, scope: str, cost: int, idem_key: str) -> str:
        """Send the winning vendor a complete job offer. Exactly-once per idem_key."""
        v = next((x for x in self.store.list_vendors() if x.id == vendor_id), None)
        if not v:
            return f"ERROR: no vendor {vendor_id}"

        def mut(t: WorkOrder):
            replayed = self._check_idem(t, idem_key)
            if replayed:
                return replayed
            t.selected_vendor_id = vendor_id
            t.authorized_scope = scope
            t.authorized_cost = cost
            t.status = TicketStatus.DISPATCHED
            t.record(Actor.AGENT, "dispatched", f"to {v.company} (${cost})")
            return f"DISPATCHED: ticket {t.id} offered to {v.company}"

        out = self.store.update_ticket(ticket_id, mut)
        if not isinstance(out, str):
            return f"ERROR: no ticket {ticket_id}"
        if out.startswith("DISPATCHED"):
            job_card = (
                f"Work order {ticket_id}\nUnit {_unit_of(self.store, ticket_id)}: "
                f"{_raw_of(self.store, ticket_id)[:140]}\n"
                f"Authorized scope: {scope}\nAuthorized: ${cost}\nReply ACCEPT or DECLINE."
            )
            self.store.record_message(OutboundMessage(
                ticket_id=ticket_id, to_role=Actor.VENDOR, to_id=vendor_id,
                kind="dispatch_offer", body=job_card,
            ))
        return out

    def message_tenant(self, ticket_id: str, kind: str, body: str, idem_key: str = "") -> str:
        """Send a tenant update (acknowledgment, schedule offer, reminder, closeout check)."""
        def mut(t: WorkOrder):
            if idem_key:
                replayed = self._check_idem(t, idem_key)
                if replayed:
                    return replayed
            t.record(Actor.AGENT, f"tenant_msg:{kind}", body[:80])
            return f"SENT: {kind} to tenant on {t.id}"

        out = self.store.update_ticket(ticket_id, mut)
        if not isinstance(out, str) or out.startswith("ERROR"):
            return out if isinstance(out, str) else f"ERROR: no ticket {ticket_id}"
        t = self.store.get_ticket(ticket_id)
        self.store.record_message(OutboundMessage(
            ticket_id=ticket_id,
            to_role=Actor.TENANT,
            to_id=(t.tenant_id if t else ""),
            kind=kind, body=body,
        ))
        return out

    def message_vendor(self, ticket_id: str, body: str, idem_key: str = "") -> str:
        """Send the assigned vendor a message (nudge, schedule confirm, parts question)."""
        t = self.store.get_ticket(ticket_id)
        if not t or not t.selected_vendor_id:
            return f"ERROR: no ticket/vendor for {ticket_id}"
        vid = t.selected_vendor_id

        def mut(t: WorkOrder):
            if idem_key:
                replayed = self._check_idem(t, idem_key)
                if replayed:
                    return replayed
            t.record(Actor.AGENT, "vendor_msg", body[:80])
            return f"SENT to vendor on {t.id}"

        out = self.store.update_ticket(ticket_id, mut)
        if not isinstance(out, str):
            return f"ERROR: no ticket {ticket_id}"
        if out.startswith("SENT"):
            self.store.record_message(OutboundMessage(
                ticket_id=ticket_id, to_role=Actor.VENDOR, to_id=vid,
                kind="nudge", body=body,
            ))
        return out

    def escalate_to_human(self, ticket_id: str, reason: str) -> str:
        """Park a ticket in the human queue. Escalation is a capability, not an error."""
        def mut(t: WorkOrder):
            t.status = TicketStatus.EXCEPTION
            t.stall_count += 1
            t.record(Actor.AGENT, "escalated", reason)
            return f"ESCALATED: {t.id} — {reason}"

        out = self.store.update_ticket(ticket_id, mut)
        if not isinstance(out, str):
            return f"ERROR: no ticket {ticket_id}"
        self.store.record_message(OutboundMessage(
            ticket_id=ticket_id, to_role=Actor.PM, to_id="pm", kind="escalation",
            body=f"Needs your attention: {reason} (ticket {ticket_id})",
        ))
        return out

    def log_event(self, ticket_id: str, kind: str, detail: str = "") -> str:
        """Append an audit event. The audit trail doubles as dispute documentation."""
        def mut(t: WorkOrder):
            t.record(Actor.AGENT, kind, detail)
            return "LOGGED"

        out = self.store.update_ticket(ticket_id, mut)
        return out if isinstance(out, str) else f"ERROR: no ticket {ticket_id}"


def _unit_of(store: Store, ticket_id: str) -> str:
    t = store.get_ticket(ticket_id)
    return t.unit if t else "?"


def _raw_of(store: Store, ticket_id: str) -> str:
    t = store.get_ticket(ticket_id)
    return t.raw_request if t else ""


def sla_deadline(created: datetime, urgency: Urgency) -> datetime:
    """Response-time benchmarks: acknowledge fast, dispatch emergencies in 2h."""
    hours = {Urgency.EMERGENCY: 2, Urgency.URGENT: 24, Urgency.ROUTINE: 72}[urgency]
    return created + timedelta(hours=hours)


def utcnow() -> datetime:
    return datetime.now(UTC)
