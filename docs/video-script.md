# Demo video script (≤5 min)

> Format: screen recording + voiceover. No camera. YouTube/Vimeo public link.
> Hard requirement coverage: (1) problem, (2) who it's for, (3) why it matters + working demo.

## Beat sheet

| # | Time | Visual | Voiceover |
|---|------|--------|-----------|
| 1 | 0:00–0:30 | Title card → stats slide (3.2 hrs/day, 8–15 touches, 64% no updates) | "Every day, property managers lose hours to the same loop: a tenant reports a problem, and a human becomes the router — triaging, calling vendors, chasing quotes, checking status, matching invoices. Fifteen touches per work order." *(recording note: replace with cold-open variant A — see below)* |
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

## Cold-open variants (first 30 seconds)

Judges are tired and decide fast. The current beat 1 (title card → stats slide)
is the weakest possible start — it spends the decisive half-minute on slides.
Three alternatives, all built to hit the rubric's first three requirements
(problem, who it's for, why it matters) *and* show the product before 0:30:

### A — "The 2:07 a.m. text" (in medias res) ← PICKED

| Time | Screen |
|------|--------|
| 0:00–0:05 | Black → iPhone lock screen, buzz: tenant text "there's water coming through the kitchen CEILING!!" Timestamp reads 2:07 AM. |
| 0:05–0:12 | Split screen, LEFT ("the old way"): voicemail waveform plays to a dark ceiling; clock spins 2 AM → 8 AM; sticky notes multiply on a fridge. VO (dry): "By the time anyone calls back, the floor's done." |
| 0:12–0:25 | RIGHT side lights up: Handoff acks the tenant in seconds ("help is on the way"), ticket card lands on a real dashboard, quotes tick in from the vendor bench — then an approval card slides up: **"After-hours emergency · $640 · vendor 4.8★ · [Approve] [Deny]"**. VO: "Handoff does everything except the decision." |
| 0:25–0:30 | Cursor clicks **Approve**. Cut to logo + one-liner: "Agents handle the handoffs. Humans handle the judgment." Roll into beat 2. |

Why it wins: no context required, emotionally concrete, and the product is
demonstrating its core promise (ack instantly, work quietly, ask once) inside
25 seconds. The approve-click doubles as the transition into beat 2.

### B — "Fifteen touches" (quantified pain)

A real paper work order on screen. Each manual touch stamps a huge counter
overlay synced to the VO listing them — triage (1), call vendor (2), leave
voicemail (3), call next vendor (4)… — until 15 fills the frame. Freeze. The
counter burns down to **0**. Logo: "Handoff. Agents handle the handoffs."

Strongest rubric-legibility (problem quantified before 0:15) and cheapest to
shoot; risk is zero product on screen for the full 30 seconds and a colder,
less human hook.

### C — "Approve?" (decision-first)

Open full-screen ON the approval card itself — "Handoff needs you: after-hours
emergency dispatch · $640 · vendor rated 4.8, 12 min away · [Approve] [Deny]" —
cursor hovering. VO: "This is the only screen a property manager ever has to
see. Here's everything that happened before it." Rewind-wipe into a
fast-forward montage of agent work, landing back on the click at 0:30.

Boldest statement of the human-in-the-loop thesis — the track's exact language —
but the first five seconds are confusing without context, and confusion at 0:05
is how you lose a tired judge.

**Recommendation: A**, with C's approval card as its closing beat (already
is). If recording time runs short, B is the fallback — it needs no dashboard
footage.

