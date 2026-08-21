# Content notes — Stream D sharpening pass (2026-08-21)

What changed, why, and what got verified vs. cut. Branch: `content/docs`.

## docs/blog/01-build-story.md — build story

- **Opened on the 2 a.m. text instead of "Every property manager knows…"** and
  replaced the unsourced "industry data puts it at 3.2 hours/day" claim with
  owned arithmetic (counting the 15 touches). We can't cite a source for
  3.2 hrs; we can count steps per work order.
- **Added the real POLICY excerpt** from `src/handoff/agents/coordinator.py`
  (abridged with an explicit `…`). The point it makes — the policy spends its
  words on limits, not persona — is the post's thesis and needed code on screen.
- **"Why Strands" tightened** from feature-list to decisions: agent loop over
  prompt chain (because recovery paths are decisions), typed triage, provider
  portability as a *testing* strategy ("CI never calls a model; our demo always
  does" kept — it's true and load-bearing).
- Run commands now match README exactly (`uv venv --python 3.13 .venv`,
  `.venv/bin/python -m pytest tests/`).

## docs/blog/02-reliability-patterns.md — reliability

- **Swapped the idealized snippet for real code**: `_check_idem` +
  `dispatch_work_order` from `src/handoff/tools/toolkit.py` verbatim (with `…`
  elisions), plus the actual double-send test from
  `tests/test_workflow.py::test_idempotent_dispatch_never_double_sends`
  including its `"dispatch offer must be sent exactly once"` message.
- **Gate section quotes the real `gate_and_dispatch`** persistence block from
  `src/handoff/workflow/engine.py`, comment included — the "PM approves *this*
  vendor at *this* price" line was already in the code and is better than
  anything I'd write about it.
- **Reroute loop quoted** from `vendor_response`; escalation framed as one of
  four designed outcomes rather than error handling.
- Ending is now a measured fact: **nine tests green in under four seconds**
  (`9 passed in 3.71s`, run locally on this branch). Kept the track-language
  echo ("make the safe calls themselves and surface only when a human needs to
  weigh in") in the gates section.

## docs/blog/03-evals-gate.md — evals gate

- **Cut the unverifiable "first run scored 75% urgency / 88% category."**
  Nothing in git history or tests backs those numbers; keeping them risked a
  judge or reader asking how they were measured. Replaced with the *actual*
  harness output (ran `uv run python -m handoff.evals.triage_evals`: heuristic
  provider, n=8, 100%/100%) and reframed the three famous misses as fixes that
  are still visible in the scorer's weighted-hint table — which I verified in
  `src/handoff/agents/decisions.py` ("locked myself out", "standing outside"
  hints; the literal comment "specific fixtures outrank generic symptoms";
  plumbing weights pouring:3/ceiling:2 above water:1).
- **Quoted the real asymmetric gate**:
  `tests/test_evals.py::test_emergency_scenarios_never_undertriaged`, plus the
  aggregate floors (≥0.85 / ≥0.75) from `test_triage_accuracy_floors`.
- Snippet fixed to the real signature: `provider.classify(scen["raw"],
  list(scen["photos"]))`.
- Title changed to the argument: "Agent judgment is testable. Test it like
  code."

## docs/devpost-submission.md — field limits (verified online)

Checked Devpost Help Center (article 145 "set up the Submission Period" +
article 122/126): the short pitch is the **elevator-pitch tagline, hard limit
140 characters**; the long description is the **Project story** (markdown,
prompted headings: Inspiration / What it does / How we built it / Challenges /
Accomplishments / What we learned / What's next; no enforced cap). Restructured
the doc to mirror those fields so submit day is paste-and-go.

- Tagline picked (135/140): *"An autonomous coordinator that triages tenant
  reports, works vendors, matches invoices — and pings the manager only for
  real decisions."* Two alternates included **with measured character counts**;
  the 140-char alternate is flagged as at-cap.
- Story sections rewritten around Devpost's own headings; official Professional
  Agents language woven into Inspiration ("clears the runway…") and What it
  does ("makes the safe calls on its own and surfaces only when a human
  actually needs to weigh in") — naturally, not as a quote block.
- "Built with" tags list added (Devpost asks for sponsor tools explicitly).
- Checklist updated: description now checked off.

## Cold-open storyboards → docs/video-script.md

Three variants added under "Cold-open variants"; beat 1 carries a recording
note pointing at the pick.

- **A — "The 2:07 a.m. text" (in medias res) ← PICKED.** Tenant text on a lock
  screen, split-screen old-way-vs-Handoff, ends on the approve-click at 0:25.
  Wins because it needs zero context, shows the product's core promise inside
  25 seconds (ack instantly, work quietly, ask once), and the click is a
  built-in transition to beat 2.
- **B — "Fifteen touches" (quantified pain).** Counter overlay stamps each
  manual touch, burns to zero. Fallback if dashboard footage isn't ready — no
  product shots needed. Risk: colder hook, nothing but slides until late.
- **C — "Approve?" (decision-first).** Opens on the approval card itself.
  Boldest thesis statement but confusing for the first five seconds — and a
  confused judge at 0:05 is a lost judge. C's card survives as variant A's
  closing beat.

## Honesty ledger (claims audited)

| Claim | Status |
|---|---|
| 9 tests pass <4 s | ✅ ran locally: `9 passed in 3.71s` |
| Eval output table (n=8, 100%/100% heuristic) | ✅ ran locally |
| Idempotency/durable-gate/reroute snippets | ✅ verbatim from src + tests |
| POLICY prompt excerpt | ✅ verbatim (abridged, marked) |
| "75%/88% first eval run" | ❌ unverifiable — removed |
| "3.2 hours/day industry data" | ⚠️ unsourced — recast as counted touches |
| Devpost 140-char tagline limit | ✅ Devpost Help Center |

## Follow-ups for other streams

- Blog posts still say "publish after Bedrock integration is verified" — keep
  that gating.
- Repo has no public GitHub URL yet; blog 01 references repo paths only, but
  devpost links + README About need the URL when it exists.
- Credits-form verification (Sep 11 12pm PT deadline) already flagged in
  checklist — unchanged.
