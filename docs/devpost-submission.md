# Devpost submission draft

> Field names below match Devpost's actual submission form (checked against the
> Devpost Help Center, 2026-08): **Project title**, **Elevator pitch** = tagline,
> hard limit **140 characters**, **Project story** (markdown; Devpost prompts the
> standard headings used below — no enforced character cap, but judges skim),
> **Built with** tags, repo/video links.

## Project title

Handoff

## Elevator pitch (tagline) — 135/140 chars

An autonomous coordinator that triages tenant reports, works vendors, matches
invoices — and pings the manager only for real decisions.

Alternates (measured):

- 105: `Handoff — the autonomous maintenance coordinator. Agents handle the handoffs; humans handle the judgment.` (echoes the video's closing line)
- 140: `Agents handle the handoffs, humans handle the judgment. Handoff runs property maintenance end to end and asks only when a human must decide.` — exactly at the cap; don't edit without recounting

## Project story

### Inspiration

A great professional agent clears the runway by drafting, checking, organizing,
and following up so the expert can spend their time on the part that needs
them. For property managers, the expert time is judgment — which vendor, which
price, is this an emergency? — and it's buried under everything around it:
triaging reports, phone-tagging vendors, chasing quotes, checking status,
matching invoices. Count the touches and it's 8–15 manual steps per work order;
coordination is the profession's #1 time drain, and slow response is a top
driver of non-renewals. We built Handoff to be the runway-clearer so managers
can do the part that needs them.

### What it does

Handoff owns maintenance coordination end to end: intake → triage (structured
output + confidence floor) → vendor quote discovery → policy gate → dispatch of
complete job cards → scheduling → verified closeout → invoice three-way match.
A nightly sweep nudges stalled jobs and escalates what ages out of its lane.

It makes the safe calls on its own and surfaces only when a human actually
needs to weigh in: spend above the firm's approval threshold, after-hours
emergency dispatch, or a request too ambiguous to classify safely. Every step
lands on an audit trail that doubles as dispute documentation.

For whom: independent property-management firms running ~100–500 doors with a
bench of trade vendors — big enough that coordination breaks, small enough to
have no dispatch department.

### How we built it

- **Strands Agents SDK**: one Coordinator Agent runs a tool loop over the
  ticket (triage → vendor search → quotes → gate-or-dispatch → tenant updates);
  structured-output triage with an explicit confidence floor (0.55).
- **Model-provider portability**: same agent code targets Amazon Bedrock
  (Claude) and a deterministic heuristic provider — CI never calls a model, so
  the reliability core is tested on every push for free.
- **Reliability mechanics**: idempotency keys on every side-effecting tool;
  approval gates persist the exact intended dispatch before pausing, so they
  survive process restarts; escalation is a designed outcome (dispatch / gate /
  escalate / park), not an exception.
- **Eval gate in CI**: an 8-scenario judgment library replays through whatever
  triage provider is configured; aggregate floors (≥0.85 urgency, ≥0.75
  category) plus a hard rule that no emergency is ever under-triaged.
- **AWS deploy path**: Bedrock AgentCore Runtime (quickstart recipe in
  docs/resources.md), EventBridge Scheduler for the sweep heartbeat,
  DynamoDB-backed store for production state.

### Challenges we ran into

- **Agent judgment is a specification problem.** Our first scoring misses were
  spec bugs, not model bugs: "locked myself out" wasn't in the emergency hints;
  generic symptom words outranked specific fixtures (a dishwasher leak read as
  plumbing); water pouring through a ceiling *fixture* read as electrical
  instead of plumbing. Each fix lives in the scorer's weighted-hint table and
  is covered by the eval gate now.
- **Approvals have to survive restarts.** Blocking in-process dies with the
  process; persisting the gated dispatch first means resume replays exactly
  what was approved — and a duplicate resume is a no-op.
- **Testing real-world actions without sending them.** Idempotency keys plus a
  deterministic provider let us assert "exactly one dispatch offer exists"
  across a simulated crash-retry in milliseconds.

### Accomplishments we're proud of

Nine tests, green in under four seconds, covering crash-retry double-send
prevention, durable approval + duplicate-resume no-op, vendor-decline reroute,
invoice-discrepancy escalation, low-confidence triage to human, and the nightly
sweep — run against the same code that drives the demo. The demo itself runs
fully offline (`python -m handoff.demo`, four scenarios end to end), so the
build is verifiable today while the Bedrock integration lands.

### What we learned

- Failure costs are asymmetric — over-triaging wastes money, under-triaging a
  flood costs trust and habitability — so thresholds should be too: aggregates
  may regress within bounds, emergencies never.
- An agent that never says "not sure" isn't confident, it's unaudited. Honest
  confidence scores turn uncertainty into a visible queue with an owner.
- The policy prompt is the product: most of its words are limits (when to stop,
  when to ask, when to refuse), not personality.

### What's next

Live Bedrock integration once AWS credits land (requested; see checklist),
AgentCore deployment, and a pilot with an independent PM firm — the durable-gate
and idempotency contracts don't change when the store moves from in-memory to
DynamoDB.

## Built with (Devpost tags)

`strands-agents-sdk` `amazon-bedrock` `bedrock-agentcore` `amazon-eventbridge`
`dynamodb` `python` `fastapi` `pytest`

## Links

- Repo: public GitHub URL + MIT license in About (required)
- Video demo: ≤5 min, YouTube/Vimeo public link — script in docs/video-script.md

## Checklist mapping

- [x] Public repo + MIT license (About section)
- [x] README + architecture diagram (mermaid)
- [ ] ≤5-min video (script ready — docs/video-script.md; cold-open variants added)
- [ ] Live demo link (AgentCore deploy once AWS creds exist — recipe:
      https://aws.github.io/bedrock-agentcore-starter-toolkit/user-guide/runtime/quickstart.html)
- [x] Text description (this doc — paste sections into matching Devpost fields)
- [ ] builder.aws.com posts ×3 (drafts ready — docs/blog/)
- [x] $50 credits requested — ⚠️ verify form matches Resources page
      (https://forms.gle/Ssr8zLw4afKg114M7) before Sep 11 12pm PT; see docs/resources.md
