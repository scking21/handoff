# Draft: Building Handoff — an autonomous maintenance coordinator with Strands Agents SDK

> builder.aws.com post 1 of 3 · "Agents for Humans" hackathon build story
> Status: DRAFT — publish after Bedrock integration is verified

Every property manager knows the 6:40 a.m. water heater call. What they know less
formally is that the pain was never the repair — it's the fifteen handoffs around it:
triage from a voicemail, vendor phone tag, quote chasing, tenant scheduling, status
checks, invoice matching. Industry data puts it at 3.2 hours per manager per day,
and it's the top driver of both negative reviews and non-renewals.

For the Agents for Humans hackathon we built **Handoff**: an agent that owns those
handoffs end to end, runs quietly in the background, and only interrupts the property
manager when there's a real decision — spend above policy threshold, an after-hours
emergency dispatch, or a request too ambiguous to classify safely.

## Why Strands Agents

Strands gave us three things the architecture needed on day one:

1. **A real agent loop with tool calling.** The Coordinator Agent receives a raw
   tenant report and works the problem: look up context, classify severity, search
   the vendor bench, collect quotes, dispatch or gate. We didn't want a chain of
   prompts; we wanted an agent that decides *how* to get to "dispatched."
2. **Structured output.** Triage decisions come back typed (`urgency`, `category`,
   `confidence`) instead of parsed prose. Below a confidence floor the ticket routes
   to a human queue rather than guessing — escalation as a designed capability.
3. **Model-provider portability.** The same agent code runs against Amazon Bedrock
   Claude in production and a deterministic provider in tests. Our CI never calls a
   model; our demo always does.

## The design rule that shaped everything

**Probabilistic reasoning, deterministic mechanics.** The LLM never mutates ticket
state directly. Every side effect — dispatching a vendor, messaging a tenant,
creating an approval gate — goes through tools keyed by an idempotency key. Retry
the workflow after a crash and a replayed tool call returns the recorded outcome
instead of double-texting a tenant at midnight.

The full architecture, the durable approval-gate pattern, and what the Strands
agent loop looks like in practice are covered in the follow-up posts in this series.

## Try it

The repo is MIT-licensed and runs locally without credentials:
`pytest` proves the reliability core; `python -m handoff.demo` walks four scenarios
through intake → triage → price discovery → dispatch/gate.
