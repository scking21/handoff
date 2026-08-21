# Draft: Deterministic enforcement around probabilistic agents

> builder.aws.com post 2 of 3 · reliability deep-dive
> Status: DRAFT — publish after Bedrock integration is verified

An agent that works in a demo and an agent you can operate are different artifacts.
The demo needs to succeed once. Operations needs it to fail in ways you can name,
bound, and recover from — at 3 a.m., unattended. Handoff (our Agents for Humans
build) is exactly that kind of agent: it dispatches real-world actions on a schedule.
Here are the three patterns that make that safe.

## 1. Idempotency keys on every side effect

LLM retries are not like HTTP retries. The model cannot reliably know whether its
previous attempt landed, so "just retry" can double-dispatch a plumber or text a
tenant twice. Every side-effecting tool in Handoff takes an idempotency key
(`ticket_id` + step name); the key is recorded on the ticket before the action
runs, and a replay returns `REPLAYED` instead of re-executing:

```python
def dispatch_work_order(self, ticket_id, vendor_id, scope, cost, idem_key):
    t = self.store.get_ticket(ticket_id)
    replayed = self._check_idem(t, idem_key)
    if replayed:
        return replayed          # crash-retry lands here, not in a second SMS
    ...
```

Our test suite asserts the guarantee directly: fire the same dispatch twice,
assert exactly one vendor offer exists.

## 2. Approval gates that survive restarts

The hackathon theme — agents that only surface for real decisions — needs a pause
mechanism. The naive version blocks in-process; restart the process and the
approval silently dies. Handoff's gate persists the *exact intended dispatch*
(vendor + authorized price) onto the ticket before pausing. When the property
manager approves hours later, resume replays precisely that dispatch — no
re-search, no stale price, and a duplicate resume is a no-op.

This maps cleanly onto AWS's durable-orchestration guidance (Step Functions
`.waitForTaskToken`); at our scale the ticket store plays the durable-wait role
and the pattern stays testable in CI without cloud dependencies.

## 3. Escalation as a capability, not an error path

Most agent implementations have two outcomes: answer or throw. We designed four:
dispatch, gate for approval, escalate to the human queue, or park with a reason.
Low-confidence triage escalates instead of guessing. Invoice >10% over authorized
scope escalates with both numbers attached. A vendor who declines re-routes down
the ranked bench before ever becoming a human problem. The property manager's
dashboard shows only the fourth category — which is the entire product promise:
the background work stays background.

The result we verify in tests: seven scenarios covering happy path, crash-retry,
durable approval, decline-reroute, invoice discrepancy, low-confidence triage,
and the nightly sweep — all passing against the same code that runs in the demo.
