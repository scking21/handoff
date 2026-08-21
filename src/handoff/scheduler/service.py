"""Background scheduler.

The theme is an agent that runs quietly and only surfaces for real decisions.
This service is that heartbeat: on an interval it sweeps open tickets,
nudges stalled vendor dispatches, ages out approval requests, and escalates
what exceeds its lane.

Local/dev: a daemon thread with a small interval.
Production: EventBridge Scheduler -> AgentCore invocation of the same
``run_sweep`` entrypoint (see deploy/).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from handoff.domain.models import TicketStatus, Urgency
from handoff.tools.toolkit import HandoffTools, sla_deadline
from handoff.workflow.engine import nightly_sweep


def run_sweep(tools: HandoffTools) -> list[str]:
    """One sweep pass: engine nudges + SLA deadline enforcement."""
    actions = nightly_sweep(tools)

    # SLA enforcement: emergencies must be dispatched within 2h, urgent 24h.
    for t in tools.store.list_tickets():
        if t.status == TicketStatus.TRIAGED and t.urgency and t.created_at:
            deadline = sla_deadline(t.created_at, t.urgency)
            from handoff.tools.toolkit import utcnow

            if utcnow() > deadline:
                actions.append(
                    tools.escalate_to_human(t.id, f"{t.urgency.value} ticket breached dispatch SLA")
                )
    return actions


class SchedulerService:
    def __init__(self, tools: HandoffTools, interval_seconds: int = 300):
        self.tools = tools
        self.interval = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.history: list[tuple[float, list[str]]] = []

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.history.append((time.time(), run_sweep(self.tools)))
                self.history = self.history[-100:]
            except Exception as exc:  # never let the heartbeat die
                self.history.append((time.time(), [f"sweep error: {exc!r}"]))

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="handoff-sweep", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def tick_once(self) -> list[str]:
        """Manual trigger used by tests and the dashboard."""
        actions = run_sweep(self.tools)
        self.history.append((time.time(), actions))
        return actions


def make_scheduler(tools: HandoffTools, interval_seconds: int = 300) -> SchedulerService:
    return SchedulerService(tools, interval_seconds)
