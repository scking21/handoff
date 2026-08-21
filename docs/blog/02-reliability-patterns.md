# An agent you can operate: three patterns that survive 3 a.m.

> builder.aws.com post 2 of 3 · reliability deep-dive
> Status: DRAFT — publish after Bedrock integration is verified

An agent that works in a demo and an agent you can operate are different
artifacts. The demo has to succeed once. Operations needs it to fail in ways
you can name, bound, and recover from — unattended, at 3 a.m., when the flood
is real and the retry loop is hot. Handoff (our Agents for Humans build)
dispatches real-world actions on a schedule, so we treated these three patterns
as load-bearing walls, not nice-to-haves.

## 1. Idempotency keys on every side effect

LLM retries are not like HTTP retries. The model cannot know whether its
previous attempt landed, so "just try again" is how you double-dispatch a
plumber or text a tenant twice at midnight. So in Handoff, *every*
side-effecting tool takes an `idem_key`. The key is checked before anything
happens, recorded with the action, and a replay returns the recorded outcome
instead of executing again:

```python
def _check_idem(self, t: WorkOrder, idem_key: str) -> str | None:
    if idem_key in t.idempotency_keys:
        return f"REPLAYED: {idem_key} already applied to {t.id} — no action taken"
    t.idempotency_keys.add(idem_key)
    return None

def dispatch_work_order(self, ticket_id: str, vendor_id: str, scope: str,
                        cost: int, idem_key: str) -> str:
    """Send the winning vendor a complete job offer ... Exactly-once per
    idem_key: a retry never double-dispatches."""
    ...
    replayed = self._check_idem(t, idem_key)
    if replayed:
        return replayed          # crash-retry lands here, not in a second SMS
```

The caller doesn't manage this; it's just how tools work. The workflow builds
keys mechanically (`f"{t.id}:dispatch:{vendor_id}"`), which means any crash
anywhere in the pipeline replays into a no-op.

And we don't trust that guarantee because we wrote it — the test suite asserts
it directly:

```python
r1 = engine.gate_and_dispatch(tools, t.id, choice)
r2 = engine.gate_and_dispatch(tools, t.id, choice)  # crash-retry replay

if "APPROVAL" not in r1:
    assert "REPLAYED" in r2
    msgs = [m for m in store.list_messages(t.id) if m.kind == "dispatch_offer"]
    assert len(msgs) == 1, "dispatch offer must be sent exactly once"
```

Fire the same dispatch twice, assert exactly one vendor offer exists.

## 2. Approval gates that survive restarts

The hackathon theme — agents that make the safe calls themselves and surface
only when a human needs to weigh in — requires a pause mechanism. The naive
version blocks in-process: restart the process and the approval silently dies,
along with whatever the agent was about to do.

Handoff's gate persists the *exact intended dispatch* onto the ticket before
pausing:

```python
needs_approval = choice.estimated_cost > tools.approval_threshold or (
    after_hours and t.urgency == Urgency.EMERGENCY
)
if needs_approval:
    # Persist the exact intended dispatch: the PM approves *this* vendor at
    # *this* price, and resume must replay exactly that — not a re-search.
    t.pending_vendor_id = choice.vendor_id
    tools.store.put_ticket(t)
```

When the property manager approves hours later — process restarted, model
re-deployed, whatever — resume replays precisely that dispatch. No re-search,
no stale price, and a duplicate resume is a no-op thanks to pattern 1.

This maps cleanly onto AWS's durable-orchestration guidance (Step Functions'
`.waitForTaskToken`). At our scale the ticket store plays the durable-wait
role, which keeps the whole pattern testable in CI with zero cloud
dependencies. When we move to Bedrock AgentCore, the contract doesn't change —
only the store behind it does.

## 3. Escalation as a capability, not an error path

Most agent implementations have two outcomes: answer or throw. We designed
four: dispatch, gate for approval, escalate to the human queue, park with a
reason. Escalation is something the agent *does*, with a paper trail — not an
exception.

The payoff shows up in boring places. A vendor declines? That's not a human's
problem yet — the agent re-routes down the ranked bench first:

```python
for alt in alternates or []:
    res = tools.dispatch_work_order(
        t.id, alt, ..., idem_key=f"{t.id}:dispatch:{alt}"
    )
    if "REPLAYED" not in res:
        return f"REROUTED: {alt}"
return tools.escalate_to_human(t.id, "all candidate vendors declined")
```

Only when the bench is exhausted does a human see a ticket — with both numbers
attached if it's an invoice discrepancy, with the raw report attached if triage
wasn't confident enough to act. The property manager's dashboard shows only
that fourth category. Which is the entire product promise: the background work
stays background.

## What this buys

Nine tests cover happy path, crash-retry, durable approval, decline-reroute,
invoice discrepancy, low-confidence triage, and the nightly sweep — all green
in under four seconds, against the same code that runs in the demo. No mocks of
the reliability layer, no "we'll add tests later." If a judge (or a property
manager) asks what happens when the process dies mid-dispatch, the answer is a
test name, not a promise.
