"""Bedrock AgentCore Runtime entrypoint.

Hosts BOTH surfaces in one runtime:
- ``/invocations`` (platform protocol): JSON actions driving the agent
  (new_request / sweep / decide / status) — this is what EventBridge and the
  demo page call.
- ``/`` : the full PM dashboard, mounted lazily as ASGI sub-app, so the
  live-demo link renders a real product instead of JSON.

Cold-start budget is 30s, so NOTHING heavy runs at import: stores, models,
and the dashboard all initialize on first use.
"""

from __future__ import annotations

import threading

from bedrock_agentcore.runtime import BedrockAgentCoreApp

agent_app = BedrockAgentCoreApp()


class _LazyState:
    """Deferred initialization of store/tools/triage/coordinator."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = None

    def get(self):
        with self._lock:
            if self._state is None:
                from handoff.agents.decisions import get_triage_provider
                from handoff.config import in_agentcore_container, settings
                from handoff.data.synth.generate import seed_world
                from handoff.scheduler.service import SchedulerService
                from handoff.store.base import FileStore
                from handoff.tools.toolkit import HandoffTools

                provider = settings.model_provider
                data_dir = settings.data_dir
                store_backend = settings.store_backend
                if in_agentcore_container():
                    # Container: /var/task is not writable and shell env vars
                    # don't reach us — the runtime role carries AWS identity,
                    # so the real Bedrock brain + durable DynamoDB state are
                    # always the right call.
                    provider = "bedrock" if provider == "heuristic" else provider
                    data_dir = "/tmp/handoff-data"
                    store_backend = "dynamodb"

                if store_backend == "dynamodb":
                    from handoff.store.dynamodb import DynamoDBStore

                    store = DynamoDBStore(table_name=settings.dynamodb_table,
                                          region=settings.aws_region)
                    store.ensure_table()
                else:
                    store = FileStore(root=data_dir)
                tools = HandoffTools(store, approval_threshold=settings.approval_threshold)
                triage = get_triage_provider(provider)
                scheduler = SchedulerService(tools, interval_seconds=300)
                coordinator = None
                if provider in ("bedrock", "scripted"):
                    from handoff.agents.coordinator import CoordinatorAgent

                    if provider == "bedrock":
                        from handoff.agents.decisions import build_bedrock_model

                        model = build_bedrock_model()
                    else:
                        from handoff.agents.scripted_model import ScriptedModelProvider

                        model = ScriptedModelProvider(approval_threshold=settings.approval_threshold)
                    from handoff.agents.audit_hook import ToolTraceHook

                    coordinator = CoordinatorAgent(
                        tools, model=model,
                        trace_hook=ToolTraceHook(path=f"{data_dir}/tool_trace.jsonl"),
                    )
                if not store.list_properties():
                    seed_world(store)
                scheduler.start()
                self._state = type(
                    "S", (), {"store": store, "tools": tools, "triage": triage,
                              "scheduler": scheduler, "coordinator": coordinator}
                )()
            return self._state


_state = _LazyState()


class _LazyDashboard:
    """ASGI adapter that imports the FastAPI dashboard on first request."""

    def __init__(self) -> None:
        self._app = None
        self._lock = threading.Lock()

    async def __call__(self, scope, receive, send):
        if self._app is None:
            with self._lock:
                if self._app is None:
                    from handoff.web.app import app as fastapi_app

                    self._app = fastapi_app
        await self._app(scope, receive, send)


@agent_app.entrypoint
def invoke(event: dict) -> dict:
    st = _state.get()
    action = event.get("action", "new_request")
    if action == "new_request":
        from handoff.data.synth.generate import make_request
        from handoff.pipeline import run_request, run_request_with_coordinator

        payload = make_request(st.store, event.get("scenario"))
        t = (
            run_request_with_coordinator(st.store, st.coordinator, payload)
            if st.coordinator is not None
            else run_request(st.store, st.tools, st.triage, payload,
                             after_hours=bool(event.get("after_hours")))
        )
        t = st.store.get_ticket(t.id)
        return {"ticket_id": t.id, "status": t.status.value,
                "urgency": t.urgency.value if t.urgency else None,
                "authorized_cost": t.authorized_cost}
    if action == "sweep":
        return {"actions": st.scheduler.tick_once()}
    if action == "decide":
        from handoff.workflow import engine

        engine.resume_after_approval(st.tools, event["ticket_id"], approve=bool(event.get("approve", True)))
        t = st.store.get_ticket(event["ticket_id"])
        return {"ticket_id": t.id, "status": t.status.value}
    if action == "status":
        tickets = [
            {"id": x.id, "status": x.status.value, "urgency": x.urgency.value if x.urgency else None}
            for x in st.store.list_tickets()
        ]
        return {"tickets": tickets}
    return {"error": f"unknown action {action}"}


# Dashboard at root; /invocations, /ping, /ws keep platform priority.
agent_app.mount("/", _LazyDashboard())
