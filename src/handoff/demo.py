"""Demo runner: seeds a synthetic world and pushes scenarios through the pipeline.

Usage: .venv/bin/python -m handoff.demo
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from handoff.agents.decisions import get_triage_provider
from handoff.config import settings
from handoff.data.synth.generate import seed_world
from handoff.pipeline import run_request
from handoff.store.base import FileStore
from handoff.tools.toolkit import HandoffTools


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="handoff-demo-"))
    store = FileStore(root=root)
    tenants = seed_world(store)
    tools = HandoffTools(store, approval_threshold=settings.approval_threshold)
    triage = get_triage_provider(settings.model_provider)

    print(f"Handoff demo — provider={settings.model_provider}, world at {root}\n")

    scenarios = [
        ("midnight_flood", True),   # after-hours emergency
        ("vague_noise", False),
        ("broken_outlet", False),
        ("dripping_faucet", False),
    ]
    from handoff.data.synth.generate import make_request

    for key, after_hours in scenarios:
        payload = make_request(store, key, tenant=tenants[0])
        t = run_request(store, tools, triage, payload, after_hours=after_hours)
        t = store.get_ticket(t.id)
        print(f"[{key}] -> {t.status.value.upper()}  urgency={t.urgency.value if t.urgency else '?'} "
              f"category={t.category.value if t.category else '?'} conf={t.triage_confidence}")
        if t.selected_vendor_id:
            v = next(v for v in store.list_vendors() if v.id == t.selected_vendor_id)
            print(f"    vendor: {v.company}  authorized: ${t.authorized_cost}")
        for m in store.list_messages(t.id):
            print(f"    msg[{m.kind}] -> {m.to_role.value}: {m.body[:90]}")
        print()

    # simulate PM approving the gated flood ticket, then vendor accepting + closing out
    gated = [t for t in store.list_tickets() if t.status.value == "awaiting_approval"]
    if gated:
        from handoff.workflow import engine

        t = gated[0]
        print(f"PM approves {t.id} ...")
        engine.resume_after_approval(tools, t.id, approve=True)
        t = store.get_ticket(t.id)
        print(f"  -> {t.status.value}")
        engine.vendor_response(tools, t.id, accept=True)
        res = engine.complete_and_verify(tools, t.id, "replaced supply line, tested 30min", ["supply line"], t.authorized_cost or 300)
        print(f"  closeout -> {res}")


if __name__ == "__main__":
    main()
