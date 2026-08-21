# Building Handoff: the agent that takes the 2 a.m. maintenance call

> builder.aws.com post 1 of 3 · "Agents for Humans" hackathon build story
> Status: READY — Bedrock integration verified live 2026-08-21; public demo up (see end)

Every property manager knows the 2 a.m. ceiling-flood text. Here's what nobody
says out loud: the repair was never the expensive part. The fifteen handoffs
around it are. Triage the voicemail. Phone-tag three vendors. Chase two quotes,
take the third because the first two never called back. Schedule around a
tenant's work shift. Check status. Chase status again. Reconcile an invoice
that doesn't match the quote. Multiply by a few hundred doors and coordination
stops being part of the job — it becomes the job. Which is backwards: the
manager should be the exception handler, not the router.

For the Agents for Humans hackathon we built **Handoff**, an agent that owns
those handoffs end to end. It runs in the background and surfaces only when a
human actually needs to weigh in: spend above the policy threshold, an
after-hours emergency dispatch, or a report too ambiguous to classify safely.
Everything else — tenant ack, triage, price discovery, dispatch, scheduling
nudges, closeout verification, invoice matching — it handles on its own.

## Why Strands Agents

Three requirements killed every simpler option:

1. **A real agent loop, not a prompt chain.** A chain breaks the first time a
   vendor declines or a quote comes back weird — the recovery path isn't a
   branch you predicted, it's a decision. The Coordinator Agent gets tools and
   a policy, and works the problem: look up context, classify severity, search
   the bench, collect quotes, dispatch or gate.
2. **Structured output for judgment calls.** Triage comes back typed
   (`urgency`, `category`, `confidence`), not parsed prose. Below the
   confidence floor the ticket routes to a human queue instead of guessing.
3. **Model-provider portability.** Same agent code runs against Amazon Bedrock
   in production and a deterministic rules provider in tests. Our CI never
   calls a model; our demo always does. And the portability is real, not
   aspirational: the live provider started as Nova Lite (Claude Sonnet ready
   behind a config flag), and switching models never touched the agent code.

That third one sounds like a nice-to-have until you try to test an agent. More
on that in the evals post.

## The policy is the product

Here's the system prompt the Coordinator Agent runs on — abridged, but this is
the actual text from `src/handoff/agents/coordinator.py`:

```python
POLICY = """You are Handoff, the maintenance-coordination agent for a property-management firm.
You handle each incoming tenant request END TO END using your tools. Work autonomously;
only stop when the ticket is dispatched, gated for approval, or escalated.

POLICY
- Triage urgency: emergency = active water intrusion, gas odor, sparking/burning electrical,
  lockout, sewage backup. urgent = primary systems down (heat in cold weather, no hot water),
  safety-adjacent (dead outlet). routine = everything else.
- If confidence < 0.55 after reading the request, call escalate_to_human instead of guessing.
- search_vendors for the trade, then request_quote from the best 2-3 candidates.
- If the quoted price exceeds $APPROVAL_THRESHOLD, call create_approval_gate — never dispatch
  above threshold without approval.
- Use idem_key "<ticket_id>:<step>" everywhere so retries are safe.
Finish with a one-line summary of the outcome."""
```

Notice what the policy spends its words on. Not persuasion, not persona —
*limits*. When to stop, when to ask, when to refuse. An agent that dispatches
real-world actions needs its boundaries written down where the model can see
them on every turn.

## Probabilistic reasoning, deterministic mechanics

One design rule shaped everything else: **the LLM never mutates ticket state
directly.** Every side effect — dispatching a vendor, messaging a tenant,
creating an approval gate — goes through tools keyed by an idempotency key.
Retry the workflow after a crash and a replayed tool call returns the recorded
outcome instead of double-texting a tenant at midnight.

The model proposes; the tool layer disposes. That split is what makes the rest
of this series possible: the durable approval-gate pattern and the eval gate
both assume side effects are keyed and replayable.

## Run it yourself

The repo is MIT-licensed, public at github.com/scking21/handoff, and still runs
locally without credentials or API keys — same code that serves the live demo:

```bash
uv venv --python 3.13 .venv && uv pip install -e ".[dev]"
.venv/bin/python -m pytest tests/     # full suite, 50+ tests
.venv/bin/python -m handoff.demo      # intake → triage → quotes → dispatch/gate
```

Prefer clicking to cloning? The deployed system (API Gateway → Lambda →
DynamoDB + Bedrock AgentCore) is public:
https://0fmmk8vbt0.execute-api.us-east-2.amazonaws.com/

Posts 2 and 3 cover the parts we're proudest of: how the approval gate survives
restarts, and how triage judgment gets tested like code.
