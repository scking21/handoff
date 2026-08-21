"""Custom Strands tools bound to a Store.

Every side-effecting action is idempotent: callers pass an ``idem_key``
(ticket id + step name); replays return the recorded outcome instead of
re-executing. This is what makes safe retries possible when orchestration
resumes after a crash or an approval wait.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

from strands.tools import tool

from handoff.domain.models import Actor, OutboundMessage, Quote, TicketStatus, Trade, Urgency, WorkOrder
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
        """Return all tools for registration with a Strands Agent."""
        return [
            self.lookup_ticket_context,
            self.search_vendors,
            self.request_quote,
            self.create_approval_gate,
            self.resolve_approval,
            self.dispatch_work_order,
            self.message_tenant,
            self.message_vendor,
            self.escalate_to_human,
            self.log_event,
        ]

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
            "ticket": t.model_dump(include={"id", "status", "raw_request", "photo_descriptions", "urgency", "category", "quotes", "authorized_cost"}),
            "tenant": tenant.model_dump() if tenant else None,
            "prior_tickets_on_unit": len(prior),
            "prior_categories": [str(x.category.value) if x.category else None for x in prior[-5:]],
        }
        return json.dumps(ctx, default=str)

    def search_vendors(self, trade: str) -> str:
        """Vendors covering a trade, with rating, rate, drive time, load, on-call flag."""
        vendors = self.store.list_vendors(trade)
        rows = [
            v.model_dump(include={"id", "company", "rating", "hourly_rate", "trip_fee", "drive_minutes", "open_jobs", "on_call_now", "certifications", "no_show_count"})
            for v in vendors
        ]
        return json.dumps(rows)

    # ---------- write tools (all idempotent) ----------

    def _check_idem(self, t: WorkOrder, idem_key: str) -> str | None:
        if idem_key in t.idempotency_keys:
            return f"REPLAYED: {idem_key} already applied to {t.id} — no action taken"
        t.idempotency_keys.add(idem_key)
        return None

    def request_quote(self, ticket_id: str, vendor_id: str, urgency: str, idem_key: str) -> str:
        """Get a price/ETA quote from a vendor for this ticket. Deterministic per
        (vendor, ticket) so retries are stable."""
        t = self.store.get_ticket(ticket_id)
        if not t:
            return f"ERROR: no ticket {ticket_id}"
        replayed = self._check_idem(t, idem_key)
        if replayed:
            return replayed
        v = next((x for x in self.store.list_vendors() if x.id == vendor_id), None)
        if not v:
            return f"ERROR: no vendor {vendor_id}"
        minutes = BASE_JOB_MINUTES.get(Trade(t.category.value) if t.category else Trade.GENERAL, 90)
        jitter = 0.85 + 0.4 * _stable_jitter(vendor_id, ticket_id)
        amount = int((v.hourly_rate * minutes / 60 + v.trip_fee) * URGENCY_MULTIPLIER[Urgency(urgency)] * jitter)
        eta = max(2, int(v.drive_minutes / 30 * 2 + (24 if not v.on_call_now else 3)))
        q = Quote(vendor_id=vendor_id, amount=amount, eta_hours=eta, notes=f"quote by {v.company}")
        t.quotes = [x for x in t.quotes if x.vendor_id != vendor_id] + [q]
        t.record(Actor.AGENT, "quote_requested", f"{v.company}: ${amount}, ETA {eta}h")
        self.store.put_ticket(t)
        return json.dumps(q.model_dump(mode="json"))

    def create_approval_gate(self, ticket_id: str, reason: str, est_cost: int, idem_key: str) -> str:
        """Pause the ticket pending property-manager approval (spend over policy
        threshold, emergency after hours, unusual scope). Durable: the ticket
        stays AWAITING_APPROVAL until resolve_approval is called."""
        t = self.store.get_ticket(ticket_id)
        if not t:
            return f"ERROR: no ticket {ticket_id}"
        replayed = self._check_idem(t, idem_key)
        if replayed:
            return replayed
        t.status = TicketStatus.AWAITING_APPROVAL
        t.authorized_scope = reason
        t.authorized_cost = est_cost
        t.record(Actor.AGENT, "approval_gate_created", f"{reason} (${est_cost})")
        self.store.put_ticket(t)
        self.store.record_message(
            OutboundMessage(
                ticket_id=t.id,
                to_role=Actor.PM,
                to_id="pm",
                channel="push",
                kind="approval_request",
                body=f"Approval needed (${est_cost}): {reason}. Ticket {t.id}.",
            )
        )
        return f"APPROVAL_GATE_CREATED: ticket {t.id} paused awaiting PM decision"

    def resolve_approval(self, ticket_id: str, decision: str, note: str = "") -> str:
        """Apply the property manager's decision ('approve'/'reject') and resume flow."""
        t = self.store.get_ticket(ticket_id)
        if not t:
            return f"ERROR: no ticket {ticket_id}"
        if t.status != TicketStatus.AWAITING_APPROVAL:
            return f"IGNORED: ticket {t.id} not awaiting approval (status={t.status.value})"
        from handoff.domain.models import ApprovalDecision

        t.approval = ApprovalDecision(decision=decision, note=note)
        t.status = TicketStatus.TRIAGED if decision == "approve" else TicketStatus.EXCEPTION
        t.record(Actor.PM, "approval_decided", f"{decision}: {note}")
        self.store.put_ticket(t)
        return f"APPROVAL_{decision.upper()}: ticket {t.id} resumed"

    def dispatch_work_order(self, ticket_id: str, vendor_id: str, scope: str, cost: int, idem_key: str) -> str:
        """Send the winning vendor a complete job offer (scope, access context,
        authorized cost). Exactly-once per idem_key: a retry never double-dispatches."""
        t = self.store.get_ticket(ticket_id)
        if not t:
            return f"ERROR: no ticket {ticket_id}"
        replayed = self._check_idem(t, idem_key)
        if replayed:
            return replayed
        v = next((x for x in self.store.list_vendors() if x.id == vendor_id), None)
        if not v:
            return f"ERROR: no vendor {vendor_id}"
        t.selected_vendor_id = vendor_id
        t.authorized_scope = scope
        t.authorized_cost = cost
        t.status = TicketStatus.DISPATCHED
        t.record(Actor.AGENT, "dispatched", f"to {v.company} (${cost})")
        self.store.put_ticket(t)
        job_card = (
            f"Work order {t.id}\nUnit {t.unit}: {t.raw_request[:140]}\n"
            f"Authorized scope: {scope}\nAuthorized: ${cost}\nReply ACCEPT or DECLINE."
        )
        self.store.record_message(
            OutboundMessage(ticket_id=t.id, to_role=Actor.VENDOR, to_id=v.id, kind="dispatch_offer", body=job_card)
        )
        return f"DISPATCHED: ticket {t.id} offered to {v.company}"

    def message_tenant(self, ticket_id: str, kind: str, body: str, idem_key: str = "") -> str:
        """Send a tenant update (acknowledgment, schedule offer, reminder, closeout check)."""
        t = self.store.get_ticket(ticket_id)
        if not t:
            return f"ERROR: no ticket {ticket_id}"
        if idem_key:
            replayed = self._check_idem(t, idem_key)
            if replayed:
                return replayed
        self.store.record_message(
            OutboundMessage(ticket_id=t.id, to_role=Actor.TENANT, to_id=t.tenant_id, kind=kind, body=body)
        )
        t.record(Actor.AGENT, f"tenant_msg:{kind}", body[:80])
        self.store.put_ticket(t)
        return f"SENT: {kind} to tenant on {t.id}"

    def message_vendor(self, ticket_id: str, body: str, idem_key: str = "") -> str:
        """Send the assigned vendor a message (nudge, schedule confirm, parts question)."""
        t = self.store.get_ticket(ticket_id)
        if not t or not t.selected_vendor_id:
            return f"ERROR: no ticket/vendor for {ticket_id}"
        if idem_key:
            replayed = self._check_idem(t, idem_key)
            if replayed:
                return replayed
        self.store.record_message(
            OutboundMessage(ticket_id=t.id, to_role=Actor.VENDOR, to_id=t.selected_vendor_id, kind="nudge", body=body)
        )
        t.record(Actor.AGENT, "vendor_msg", body[:80])
        self.store.put_ticket(t)
        return f"SENT to vendor on {t.id}"

    def escalate_to_human(self, ticket_id: str, reason: str) -> str:
        """Park a ticket in the human queue: low triage confidence, repeated
        failure, invoice discrepancy. Escalation is a capability, not an error."""
        t = self.store.get_ticket(ticket_id)
        if not t:
            return f"ERROR: no ticket {ticket_id}"
        t.status = TicketStatus.EXCEPTION
        t.stall_count += 1
        t.record(Actor.AGENT, "escalated", reason)
        self.store.put_ticket(t)
        self.store.record_message(
            OutboundMessage(
                ticket_id=t.id, to_role=Actor.PM, to_id="pm", kind="escalation",
                body=f"Needs your attention: {reason} (ticket {t.id})",
            )
        )
        return f"ESCALATED: {t.id} — {reason}"

    def log_event(self, ticket_id: str, kind: str, detail: str = "") -> str:
        """Append an audit event. The audit trail doubles as dispute documentation."""
        t = self.store.get_ticket(ticket_id)
        if not t:
            return f"ERROR: no ticket {ticket_id}"
        t.record(Actor.AGENT, kind, detail)
        self.store.put_ticket(t)
        return "LOGGED"


def sla_deadline(created: datetime, urgency: Urgency) -> datetime:
    """Response-time benchmarks: acknowledge fast, dispatch emergencies in 2h."""
    hours = {Urgency.EMERGENCY: 2, Urgency.URGENT: 24, Urgency.ROUTINE: 72}[urgency]
    return created + timedelta(hours=hours)
