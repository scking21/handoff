# Devpost submission — final copy (paste-ready)

## Title
Handoff — the maintenance-coordination agent that owns every handoff

## Track
Professional Agents

## Elevator pitch (≤140 chars)
Handoff owns every maintenance handoff — triage, quotes, dispatch, approvals — so property managers only touch real decisions.

## Short description
Property managers lose 3+ hours a day routing maintenance between tenants and vendors — 8–15 manual touches per work order. **Handoff** is an autonomous agent, built with the Strands Agents SDK on Amazon Bedrock, that owns those handoffs end to end: it triages tenant reports (multimodal), discovers vendor prices, dispatches complete job cards, keeps tenants informed, chases stalled jobs on a schedule, and matches invoices against authorized scope.

It runs in the background and **only interrupts the manager for real decisions**: spend above policy threshold, after-hours emergencies, low-confidence triage, invoice discrepancies.

## Body

### The problem
- Vendor coordination consumes **3.2 hours/day** per property manager — the profession's #1 time drain (NAA 2025)
- Every work order takes **8–15 manual touches** across five channels
- **14%** of vendor dispatches no-show; each costs 22 minutes of re-dispatch plus a day of delay
- **64%** of tenants get zero proactive updates while waiting; maintenance is the top driver of negative reviews (48%) and non-renewals

### Who it's for
Independent property-management firms running ~100–500 doors with a bench of trade vendors — big enough that coordination breaks daily, small enough to have no dispatch department. Today their coordinator IS the routing layer; Handoff makes them exception-handlers instead.

### How it works
1. Tenant reports an issue → instant acknowledgment (the #1 satisfaction lever)
2. Triage via Strands structured output: urgency / category / confidence. Below a confidence floor the ticket routes to a human queue rather than guessing.
3. Price discovery across the vendor bench; best-fit selection by rating, distance, load, no-show history
4. Policy gate: over-threshold or after-hours → durable approval pause (persisted vendor+price) → PM approves from any device, hours later if needed → exact dispatch resumes
5. Complete job card to the vendor: scope, access context, authorized price — accept/decline in one tap; declines re-route down the bench automatically
6. Verified closeout: completion notes + parts + three-way invoice match against authorized scope; >10% variance escalates
7. Nightly sweep nudges stalled vendors, ages out approvals, escalates what exceeds its lane

### Why it matters
Response speed is the top renewal driver after rent. Handoff converts a coordinator's day of phone tag into an exceptions-only queue: industry benchmarks put coordination automation at 55–65% time reduction and 20–30% lower maintenance spend. The audit trail doubles as legal/dispute documentation.

### Strands Agents usage
- Coordinator Agent running the genuine Strands tool-call loop (verified live on Bedrock)
- Structured-output triage provider with honest confidence floor (<0.55 escalates, never guesses)
- Model-provider portability: Bedrock Nova/Sonnet in production, deterministic scripted brain for offline tests and demos
- Custom tools enforcing policy at the layer an adversary can reach: idempotency keys, threshold+approval checks, state preconditions
- SafetyEnsembleProvider: deterministic hazard-keyword escalation layered over LLM judgment — undertriage of critical hazards impossible by construction
- Sliding-window conversation management + tuned ModelRetryStrategy per current docs
- Eval-gated deployment: 22-case judgment library, automated propose→eval→keep/discard optimization loop (docs/research/aug21-summary.md)

### AWS stack (all us-east-2)
Amazon Bedrock (Nova Lite; Sonnet-ready) · Bedrock AgentCore Runtime (agent API) · AWS Lambda + API Gateway (public dashboard) · DynamoDB (shared durable state) · IAM least-privilege roles · CloudWatch + AgentCore observability

**Public-endpoint hardening:** per-IP rate limiting · 120-open-ticket capacity cap · Lambda reserved concurrency 5 · XSS-safe templating pinned by test · `scripts/live_regression.py` runs the deployed URL green before we share it with anyone

**Operating lessons (live):** cross-region model inference needed the *global* foundation-model ARN prefix in IAM, not just the regional one; runtime sessions are warm per session ID, so every deploy/demo take uses a fresh ID

### Results we can demonstrate live
- Flood reported "after hours" → acknowledged instantly → emergency/plumbing triage → $400+ quote → approval gate (not auto-dispatched) → PM approves → dispatched → swept/nudged — every stage from independent sessions
- Live model triage accuracy: **100% urgency, 100% category** on the 22-case judgment library (improved from 64% via eval-driven iteration)
- Crash-retry replay of a dispatch: exactly one vendor offer sent (idempotency proven in CI)
- Live-model safety check: on the first Bedrock run, Nova tried to dispatch past its own approval gate — the tool layer refused it and the ticket ended AWAITING_APPROVAL exactly per policy

### What's next
- Claude Sonnet 4.5 as primary model (one-time Anthropic use-case form; Nova Lite carries the live demo today)
- Real tenant/vendor SMS via the SNS sandbox — the channel layer is abstracted (console/file backends today, SNS-shaped)
- Guardrails PII fencing at intake
- Pilot with an independent property-management firm

## Links
- Repo: https://github.com/scking21/handoff (MIT)
- Live demo: https://0fmmk8vbt0.execute-api.us-east-2.amazonaws.com/
- Video: [YouTube URL at publish]

## Submission checklist
- [x] Live demo link — https://0fmmk8vbt0.execute-api.us-east-2.amazonaws.com/ (board renders + submit→triage→gate verified from the open internet, 2026-08-21)
- [ ] Video (≤5 min) — script + live-recording gotchas ready in `docs/video-script.md`
- [ ] builder.aws.com posts ×3 — drafts READY in `docs/blog/`
