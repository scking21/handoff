# Demo video script (≤5 min)

> Format: screen recording + voiceover. No camera. YouTube/Vimeo public link.
> Hard requirement coverage: (1) problem, (2) who it's for, (3) why it matters + working demo.

## Beat sheet

| # | Time | Visual | Voiceover |
|---|------|--------|-----------|
| 1 | 0:00–0:30 | Title card → stats slide (3.2 hrs/day, 8–15 touches, 64% no updates) | "Every day, property managers lose hours to the same loop: a tenant reports a problem, and a human becomes the router — triaging, calling vendors, chasing quotes, checking status, matching invoices. Fifteen touches per work order." |
| 2 | 0:30–0:50 | Handoff logo + one-line pitch; dashboard board visible | "This is Handoff — an autonomous maintenance coordinator built with the Strands Agents SDK on Amazon Bedrock. It owns every handoff, runs in the background, and only interrupts the manager when there's a real decision." |
| 3 | 0:50–1:40 | Dashboard: submit `midnight_flood` with after-hours checked; show ticket appear, ack message instantly | "A tenant reports water pouring through the ceiling at 2 a.m. Watch: acknowledgment goes out immediately — tenants judge us on response speed, not repair speed. The agent classifies it: emergency, plumbing, high confidence." |
| 4 | 1:40–2:30 | Ticket detail: quotes from vendor bench, approval gate message to PM | "It discovers prices from three vendors, picks the best fit by rating, distance, load and no-show history. It's after hours and above threshold — so instead of dispatching, it pauses and asks the manager. This is the human-in-the-loop gate: durable, exact, and the only interruption." |
| 5 | 2:30–3:10 | Click Approve → dispatch offer to vendor; act as vendor: accept; schedule window | "The manager approves. The vendor gets a complete job card — scope, access context, authorized price — and accepts with one tap. Tenant gets the arrival window automatically." |
| 6 | 3:10–3:50 | Vendor completes w/ notes+parts+invoice; invoice match; closeout check to tenant; audit trail scroll | "Completion is verified, not assumed: parts, notes, photos, and a three-way invoice match against authorized scope. The tenant confirms the fix. Every step lands on an audit trail — which doubles as dispute documentation." |
| 7 | 3:50–4:20 | Nightly sweep button → nudge + escalation examples; evals terminal run | "On a schedule, the agent sweeps open tickets — nudging stalled vendors, escalating what ages out of its lane. And its judgment is tested like code: an eval gate replays emergency scenarios before any deploy." |
| 8 | 4:20–5:00 | Architecture diagram + closing card (stack: Strands · Bedrock · AgentCore) | "Under the hood: probabilistic reasoning, deterministic mechanics — idempotency keys mean retries never double-send; approval gates survive restarts. Built with Strands Agents SDK, deployed on Amazon Bedrock AgentCore. Handoff: agents handle the handoffs, humans handle the judgment." |

## Shot list (record later)
- [ ] Clean dashboard state (fresh world seed)
- [ ] Terminal: pytest green + evals output
- [ ] Architecture diagram full-screen
- [ ] All interactions at 100% zoom, cursor visible
