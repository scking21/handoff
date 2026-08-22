"""CoordinatorAgent — the Strands agent-loop showcase.

One Strands Agent owns a ticket end-to-end by calling the HandoffTools in an
agentic loop: triage -> vendor search -> quotes -> gate-or-dispatch -> tenant
ack. The LLM decides; the tools enforce policy (idempotency keys, approval
gates, escalation lanes), so a hallucinated or repeated action cannot corrupt
a ticket's lifecycle.
"""

from __future__ import annotations

import json

from handoff.tools.toolkit import HandoffTools

POLICY = """You are Handoff, the maintenance-coordination agent for a property-management firm.
You handle each incoming tenant request END TO END using your tools. Work autonomously;
only stop when the ticket is dispatched, gated for approval, or escalated.

POLICY
- Triage urgency: emergency = active water intrusion, gas odor, sparking/burning electrical,
  lockout, sewage backup. urgent = primary systems down (heat in cold weather, no hot water),
  safety-adjacent (dead outlet). routine = everything else.
- If confidence < 0.55 after reading the request, call escalate_to_human instead of guessing.
- search_vendors for the trade, then request_quote from the best 2-3 candidates.
- Pick the winning vendor weighing rating, drive time, current load, no-show history, price.
- Threshold math is EXACT: if the winning quote is strictly greater than $APPROVAL_THRESHOLD,
  call create_approval_gate (include vendor_id). If it is at or under the threshold, call
  dispatch_work_order directly — do NOT gate. Never claim a quote exceeds the threshold
  when its amount does not.
- AFTER-HOURS EMERGENCIES: always create_approval_gate before dispatching, regardless of
  amount, and include the words 'after-hours' in the gate reason. Waking a vendor at night
  is a PM decision even at modest cost.
- Otherwise dispatch_work_order with a clear authorized scope, then message_tenant with a
  short warm acknowledgment of progress.
- Use idem_key "<ticket_id>:<step>" everywhere so retries are safe.
Finish with a one-line summary of the outcome."""


class CoordinatorAgent:
    def __init__(self, tools: HandoffTools, model=None, trace_hook=None):
        from strands import Agent, ModelRetryStrategy
        from strands.agent.conversation_manager import SlidingWindowConversationManager

        self.tools = tools
        hooks = [trace_hook] if trace_hook is not None else None
        self.agent = Agent(
            model=model,
            system_prompt=POLICY.replace("$APPROVAL_THRESHOLD", str(tools.approval_threshold)),
            tools=tools.all(),
            hooks=hooks,
            # Best practice (Strands docs): bound the loop's context growth and
            # keep throttle-retries inside a serverless time budget. A strategy
            # instance carries per-turn state — one per agent, never shared.
            conversation_manager=SlidingWindowConversationManager(window_size=40),
            retry_strategy=ModelRetryStrategy(max_attempts=4, initial_delay=2, max_delay=30),
        )

    def handle_request(self, payload: dict) -> str:
        """payload: {ticket_id, unit, raw, photos} as created by pipeline.intake_request."""
        brief = (
            f"New maintenance request.\n"
            f"ticket_id: {payload['ticket_id']}\n"
            f"unit: {payload['unit']}\n"
            f"AFTER-HOURS: {'YES — after-hours emergency gating policy applies' if payload.get('after_hours') else 'no (business hours)'}\n"
            f"tenant report: {payload['raw']}\n"
        )
        if payload.get("photos"):
            brief += "photo descriptions: " + "; ".join(payload["photos"]) + "\n"
        result = self.agent(brief)
        return str(result)


def summarize_ticket(store, ticket_id: str) -> str:
    t = store.get_ticket(ticket_id)
    if not t:
        return "ticket not found"
    return json.dumps(
        {
            "id": t.id,
            "status": t.status.value,
            "urgency": t.urgency.value if t.urgency else None,
            "category": t.category.value if t.category else None,
            "vendor": t.selected_vendor_id,
            "authorized": t.authorized_cost,
        }
    )
