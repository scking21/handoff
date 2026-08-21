"""Handoff domain models.

These types encode the maintenance-coordination workflow as a state machine.
Every side-effecting transition records an audit event, because the audit
trail is itself a product feature: property managers need documentation for
owner disputes, and vendors dispute invoices against the authorized scope.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def utcnow() -> datetime:
    return datetime.now(UTC)


class Trade(str, enum.Enum):
    PLUMBING = "plumbing"
    HVAC = "hvac"
    ELECTRICAL = "electrical"
    APPLIANCE = "appliance"
    GENERAL = "general"
    LOCKSMITH = "locksmith"


class Urgency(str, enum.Enum):
    EMERGENCY = "emergency"  # active water, gas, no heat in winter, security
    URGENT = "urgent"        # habitability-affecting, single-unit heat loss, etc.
    ROUTINE = "routine"


class TicketStatus(str, enum.Enum):
    INTAKE = "intake"
    TRIAGED = "triaged"
    AWAITING_APPROVAL = "awaiting_approval"
    DISPATCHED = "dispatched"          # vendor offer sent, awaiting accept
    SCHEDULED = "scheduled"            # window confirmed with tenant
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"            # vendor closed out
    VERIFIED = "verified"              # tenant confirmed fix
    CLOSED = "closed"                  # invoice matched & recorded
    EXCEPTION = "exception"            # stalled / needs human
    DECLINED_BY_TENANT = "declined_by_tenant"


class Actor(str, enum.Enum):
    TENANT = "tenant"
    AGENT = "agent"
    PM = "property_manager"
    VENDOR = "vendor"
    SYSTEM = "system"


class Property(BaseModel):
    id: str = Field(default_factory=lambda: new_id("prop"))
    name: str
    address: str
    units: list[str] = Field(default_factory=list)


class Tenant(BaseModel):
    id: str = Field(default_factory=lambda: new_id("ten"))
    name: str
    unit: str
    property_id: str
    phone: str
    email: str


class Vendor(BaseModel):
    id: str = Field(default_factory=lambda: new_id("ven"))
    company: str
    contact_name: str
    phone: str
    trades: list[Trade]
    rating: float = Field(ge=0, le=5)
    hourly_rate: int
    trip_fee: int = 0
    drive_minutes: int
    open_jobs: int = 0
    on_call_now: bool = False
    certifications: list[str] = Field(default_factory=list)
    completed_jobs: int = 0
    no_show_count: int = 0


class Quote(BaseModel):
    vendor_id: str
    amount: int
    eta_hours: int
    notes: str = ""


class ApprovalDecision(BaseModel):
    decision: str  # "approve" | "reject" | "modify:<note>"
    decided_by: str = "property_manager"
    decided_at: datetime = Field(default_factory=utcnow)
    note: str = ""


class TimelineEvent(BaseModel):
    at: datetime = Field(default_factory=utcnow)
    actor: Actor
    kind: str
    detail: str = ""


class WorkOrder(BaseModel):
    """Central aggregate. All agents read/write through the store, never directly."""

    id: str = Field(default_factory=lambda: new_id("wo"))
    property_id: str
    unit: str
    tenant_id: str
    raw_request: str
    photo_descriptions: list[str] = Field(default_factory=list)

    status: TicketStatus = TicketStatus.INTAKE
    category: Trade | None = None
    urgency: Urgency | None = None
    triage_rationale: str = ""
    triage_confidence: float = 0.0

    quotes: list[Quote] = Field(default_factory=list)
    selected_vendor_id: str | None = None
    pending_vendor_id: str | None = None  # chosen vendor awaiting PM approval
    authorized_scope: str = ""
    authorized_cost: int | None = None

    scheduled_window: str = ""
    completion_notes: str = ""
    completion_photos: list[str] = Field(default_factory=list)
    parts_used: list[str] = Field(default_factory=list)
    invoice_amount: int | None = None
    invoice_discrepancy: str = ""

    approval: ApprovalDecision | None = None
    idempotency_keys: set[str] = Field(default_factory=set)
    stall_count: int = 0

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    timeline: list[TimelineEvent] = Field(default_factory=list)

    def record(self, actor: Actor, kind: str, detail: str = "") -> None:
        self.timeline.append(TimelineEvent(actor=actor, kind=kind, detail=detail))
        self.updated_at = utcnow()


class OutboundMessage(BaseModel):
    """Every message the agent would send. In production these go via SMS/email
    providers; in the demo they render in the dashboard outbox."""

    id: str = Field(default_factory=lambda: new_id("msg"))
    ticket_id: str
    to_role: Actor
    to_id: str
    channel: str = "sms"
    body: str
    kind: str = "update"  # ack | schedule_offer | dispatch_offer | reminder | closeout_check | summary
    sent_at: datetime = Field(default_factory=utcnow)
