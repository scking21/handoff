"""Handoff dashboard.

The property manager's surface: ticket board, approvals inbox, message outbox.
Also hosts the simulation controls used in the demo video (submit scenario,
act as vendor, act as tenant). Server-rendered Jinja2 + a little CSS; no JS
build step.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from handoff.agents.decisions import get_triage_provider
from handoff.config import settings
from handoff.data.synth.generate import SCENARIOS, make_request, seed_world
from handoff.domain.models import Actor, TicketStatus
from handoff.pipeline import run_request, run_request_with_coordinator
from handoff.scheduler.service import SchedulerService
from handoff.store.base import FileStore
from handoff.tools.toolkit import HandoffTools
from handoff.workflow import engine

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

STATUS_ORDER = [
    TicketStatus.INTAKE, TicketStatus.TRIAGED, TicketStatus.AWAITING_APPROVAL,
    TicketStatus.DISPATCHED, TicketStatus.SCHEDULED, TicketStatus.IN_PROGRESS,
    TicketStatus.COMPLETED, TicketStatus.CLOSED, TicketStatus.EXCEPTION,
]


MAX_OPEN_TICKETS = 120  # public demo: cap paid inference surface
RATE_LIMIT = 6          # submissions per IP per window
WINDOW_SECONDS = 300.0


class RateLimiter:
    """In-memory fixed-window limiter. Demo-grade: resets on restart, per-instance."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < WINDOW_SECONDS]
            if len(hits) >= RATE_LIMIT:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True


limiter = RateLimiter()


def client_key(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return (fwd.split(",")[0].strip() if fwd else None) or (request.client.host if request.client else "unknown")


class DashboardState:
    def __init__(self) -> None:
        if settings.store_backend == "dynamodb":
            from handoff.store.dynamodb import DynamoDBStore

            self.store = DynamoDBStore(table_name=settings.dynamodb_table)
            self.store.ensure_table()
        else:
            self.store = FileStore(root=settings.data_dir)
        from handoff.tracing import configure_tracing

        configure_tracing()
        self.tools = HandoffTools(self.store, approval_threshold=settings.approval_threshold)
        self.triage = get_triage_provider(settings.model_provider)
        self.scheduler = SchedulerService(self.tools, interval_seconds=300)
        self.coordinator = None
        if settings.model_provider in ("bedrock", "scripted"):
            from handoff.agents.coordinator import CoordinatorAgent

            model = None
            if settings.model_provider == "bedrock":
                from handoff.agents.decisions import build_bedrock_model

                model = build_bedrock_model()
            else:
                from handoff.agents.scripted_model import ScriptedModelProvider

                model = ScriptedModelProvider(approval_threshold=settings.approval_threshold)
            from handoff.agents.audit_hook import ToolTraceHook

            self.coordinator = CoordinatorAgent(
                self.tools, model=model,
                trace_hook=ToolTraceHook(path=Path(settings.data_dir) / "tool_trace.jsonl"),
            )
        if not self.store.list_properties():
            seed_world(self.store)


state = DashboardState()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    state.scheduler.start()
    yield
    state.scheduler.stop()


app = FastAPI(title="Handoff", docs_url=None, redoc_url=None, lifespan=lifespan)


def _vendor_name(vendor_id: str | None) -> str:
    if not vendor_id:
        return ""
    return next((v.company for v in state.store.list_vendors() if v.id == vendor_id), vendor_id)


@app.get("/", response_class=HTMLResponse)
def board(request: Request):
    tickets = sorted(state.store.list_tickets(), key=lambda t: t.created_at, reverse=True)
    columns = []
    for status in STATUS_ORDER:
        cols = [t for t in tickets if t.status == status]
        if cols or status in (TicketStatus.AWAITING_APPROVAL, TicketStatus.DISPATCHED, TicketStatus.EXCEPTION):
            columns.append({"status": status, "tickets": cols})
    return TEMPLATES.TemplateResponse(
        request,
        "board.html",
        {"columns": columns, "scenarios": [s["key"] for s in SCENARIOS], "vendor_name": _vendor_name},
    )


@app.get("/tickets/{ticket_id}", response_class=HTMLResponse)
def ticket_detail(request: Request, ticket_id: str):
    t = state.store.get_ticket(ticket_id)
    if not t:
        return RedirectResponse("/", status_code=303)
    return TEMPLATES.TemplateResponse(
        request,
        "ticket.html",
        {
            "t": t,
            "messages": state.store.list_messages(ticket_id),
            "vendor_name": _vendor_name(t.selected_vendor_id),
            "pending_vendor_name": _vendor_name(t.pending_vendor_id),
        },
    )


VALID_SCENARIOS = {s["key"] for s in SCENARIOS}


@app.post("/tickets/new")
def new_ticket(request: Request, scenario: str = Form(...), after_hours: bool = Form(False)):
    if scenario not in VALID_SCENARIOS:
        return HTMLResponse(f"Unknown scenario '{scenario[:40]}'.", status_code=400)
    if not limiter.allow(client_key(request)):
        return HTMLResponse("Slow down — try again in a few minutes.", status_code=429)
    open_count = sum(
        1 for t in state.store.list_tickets()
        if t.status not in (TicketStatus.CLOSED, TicketStatus.VERIFIED, TicketStatus.DECLINED_BY_TENANT)
    )
    if open_count >= MAX_OPEN_TICKETS:
        return HTMLResponse("Demo at capacity — please enjoy the existing tickets.", status_code=503)
    payload = make_request(state.store, scenario)
    if state.coordinator is not None:
        run_request_with_coordinator(state.store, state.coordinator, payload)
    else:
        run_request(state.store, state.tools, state.triage, payload, after_hours=after_hours)
    return RedirectResponse("/", status_code=303)


@app.post("/tickets/{ticket_id}/decision")
def pm_decision(ticket_id: str, decision: str = Form(...)):
    if decision not in ("approve", "reject"):
        return RedirectResponse(f"/tickets/{ticket_id}", status_code=303)
    if state.store.get_ticket(ticket_id):
        engine.resume_after_approval(state.tools, ticket_id, approve=(decision == "approve"))
    return RedirectResponse(f"/tickets/{ticket_id}", status_code=303)


@app.post("/tickets/{ticket_id}/vendor")
def vendor_action(
    ticket_id: str,
    action: str = Form(...),
    notes: str = Form(""),
    parts: str = Form(""),
    invoice: int = Form(0),
):
    t = state.store.get_ticket(ticket_id)
    if not t or action not in ("accept", "decline", "complete"):
        return RedirectResponse(f"/tickets/{ticket_id}", status_code=303)
    if action == "accept":
        engine.vendor_response(state.tools, ticket_id, accept=True)
    elif action == "decline":
        alternates = [q.vendor_id for q in t.quotes if q.vendor_id != t.selected_vendor_id]
        engine.vendor_response(state.tools, ticket_id, accept=False, alternates=alternates)
    elif action == "complete":
        parts_list = [p.strip() for p in parts.split(",") if p.strip()]
        engine.complete_and_verify(state.tools, ticket_id, notes, parts_list, invoice or t.authorized_cost or 0)
    return RedirectResponse(f"/tickets/{ticket_id}", status_code=303)


@app.post("/tickets/{ticket_id}/verify")
def tenant_verify(ticket_id: str, ok: bool = Form(True)):
    if not ok:
        engine.tenant_rejects_fix(state.tools, ticket_id, note="issue persists after repair")
    else:
        t = state.store.get_ticket(ticket_id)
        if t:
            t.status = TicketStatus.VERIFIED
            t.record(Actor.TENANT, "verified", "")
            state.store.put_ticket(t)
    return RedirectResponse(f"/tickets/{ticket_id}", status_code=303)


@app.post("/sweep")
def sweep():
    actions = state.scheduler.tick_once()
    return RedirectResponse("/", status_code=303)
