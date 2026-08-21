# Devpost submission draft

## Title
Handoff — the maintenance-coordination agent that owns every handoff

## Track
Professional Agents

## Short pitch (elevator)
Property managers lose 3+ hours a day routing maintenance work between tenants and
vendors — 8–15 manual touches per job. Handoff is an autonomous agent, built with the
Strands Agents SDK on Amazon Bedrock, that owns those handoffs end to end: it triages
tenant reports, discovers vendor prices, dispatches complete job cards, keeps tenants
informed, chases stalled jobs on a schedule, and matches invoices against authorized
scope. It runs in the background and only interrupts the manager for real decisions —
spend above policy threshold, after-hours emergencies, or requests too ambiguous to
classify safely.

## Description sections to fill at submit time
- **What it does / how it works**: intake → triage (structured output + confidence
  floor) → quote discovery → policy gate → dispatch → scheduling → verified closeout;
  nightly sweep for stalled tickets; audit trail as dispute documentation.
- **Who it's for**: independent property-management firms running ~100–500 doors with
  a bench of trade vendors — big enough that coordination breaks, small enough to have
  no dispatch department.
- **Why it matters**: coordination time is the profession's #1 time drain; response
  speed is the top renewal driver after rent. Handoff converts a coordinator's day of
  phone tag into an exceptions-only queue.
- **Strands usage**: Coordinator Agent tool loop; structured-output triage provider;
  model-provider portability (Bedrock in prod, deterministic in CI); idempotency-keyed
  custom tools; durable approval gates; eval-gated judgment.
- **AWS stack**: Amazon Bedrock (Claude), Bedrock AgentCore Runtime (deploy),
  EventBridge Scheduler (sweep heartbeat), DynamoDB-backed state (prod store).

## Checklist mapping
- [x] Public repo + MIT license (About section)
- [x] README + architecture diagram (mermaid)
- [ ] ≤5-min video (script ready — docs/video-script.md)
- [ ] Live demo link (AgentCore deploy once AWS creds exist — recipe:
      https://aws.github.io/bedrock-agentcore-starter-toolkit/user-guide/runtime/quickstart.html)
- [ ] Text description (this doc, finalized)
- [ ] builder.aws.com posts ×3 (drafts ready — docs/blog/)
- [x] $50 credits requested — ⚠️ verify form matches Resources page
      (https://forms.gle/Ssr8zLw4afKg114M7) before Sep 11 12pm PT; see docs/resources.md
