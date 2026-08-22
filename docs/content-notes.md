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

---

# Reality-sync pass (2026-08-21 ~23:00) — branch `content/live-sync`

Trigger: AWS went live this evening (AgentCore Runtime + Lambda/APIGW public
judges' URL + DynamoDB store; main @ `25d60a4`, suite 53 passed). Every content
artifact was still frozen in its pre-AWS state ("publish after Bedrock is
verified", "demo runs fully offline", unchecked live-demo checklist item).
This pass syncs the words to the shipped system. No src/tests changes; suite
re-run green before commit.

## What changed

- **blog/01-build-story.md** — status DRAFT→READY; "Bedrock Claude in
  production" corrected to Nova Lite-live/Sonnet-behind-flag (the deployed
  model is Nova Lite today); "9 tests"→53; Run-it-yourself gains public repo +
  live demo URL alongside the offline path.
- **blog/02-reliability-patterns.md** — status DRAFT→READY; new paragraph in §1:
  the first live Bedrock run had Nova try to dispatch past its own approval
  gate and the tool layer refused it ("the wall held"); §2's "when we move to
  AgentCore" future tense → paid-off past tense incl. cross-session gate →
  approve-from-another-session verified live; "Nine tests"→53.
- **blog/03-evals-gate.md** — status DRAFT→READY; "Claude via Amazon Bedrock"
  → "the hosted model via Amazon Bedrock"; new closing section "Then the real
  model sat for the same exam": Nova Lite 75% first run → prompt sharpening →
  100% urgency/category through the same harness/floors.
- **devpost-submission.md** — How-we-built-it now describes the DEPLOYED stack
  (AgentCore public invoke API, APIGW→Lambda dashboard, DynamoDB single-table,
  cross-session live E2E) plus public-endpoint hardening (rate limiter,
  capacity cap, reserved concurrency, XSS pin, live regression harness);
  Challenges gains "Live models find new ways to be wrong" (75%→100% eval,
  post-gate dispatch refusal, cross-region-inference IAM ARN lesson);
  Accomplishments: 53 tests + live URL + offline path kept; What's-next
  re-pointed at Sonnet form / SNS sandbox SMS / Guardrails PII / pilot;
  Links: real repo + demo URLs; Checklist: live-demo box CHECKED.
- **devpost-resources.md** — credits landed ($100 remaining), AWS account +
  Bedrock wiring + AgentCore deploy marked done; builder.aws.com posts flagged
  READY pending Corby's publishing account.
- **video-script.md** — shot list gains record-against-LIVE-URL instruction and
  three recording gotchas (fresh session IDs per take, script-the-wait for LLM
  latency, public board is shared).

## Honesty ledger updates

| Claim | Status |
|---|---|
| 53 tests pass | ✅ re-ran in worktree @ `25d60a4`: `53 passed` (shared venv, PYTHONPATH=worktree/src) |
| Live judges' URL serves board | ✅ GET → HTTP 200 from open internet during this pass |
| Nova Lite 75% → 100% on eval library | ✅ git history: eval-driven-prompt-iteration commit message states exactly this |
| Post-gate dispatch refused by tool layer | ✅ same commit + build log (~15:30 entry) |
| Cross-session gate/approve/dispatch live | ✅ build log ~21:15 entry (6 independent sessions); commit hash cited there no longer resolves post filter-repo — behaviors cited, hashes avoided in public copy |
| "$100 credits remaining" | ✅ build log ~15:30 entry |
| Rate limit 6/IP/5min · cap 120 · reserved concurrency 5 | ✅ read from `src/handoff/web/app.py` constants + commit message |
| Public commit hashes in blog/devpost | ❌ deliberately omitted — history was rewritten by the blob purge; local hashes may not exist upstream |

## Still gated on humans

- Corby: Anthropic use-case form (Sonnet switch), video recording (script +
  gotchas ready), Devpost submit, builder.aws.com publishing (drafts ready).

---

# Rebase addendum (2026-08-21 late) — branch rebased onto main @ `361f158`

- **devpost-submission.md portion WITHDRAWN from this branch.** Agent 1 shipped
  their own "Final Devpost copy" on main the same evening, which already
  carries the judges' URL, the deployed-stack framing, and Nova/Sonnet
  portability language — verified before rebasing. Their copy is the final
  voice; two competing rewrites would only force a merge conflict. This branch
  now touches only: blogs ×3, video-script.md, devpost-resources.md, and these
  notes.
- UPDATE (post-audit): the withdrawal rationale was an overclaim caught by
  Corby's no-assumptions rule — full-file comparison showed Agent 1's copy
  omits five evidence-backed items mine had. With Corby's explicit ack, those
  five are folded INTO Agent 1's structure/voice in a follow-up commit on this
  branch (refusal story, hardening specifics, cross-region IAM lesson,
  What's-next items, checked live-demo box); every claim primary-source
  verified before writing (app.py constants, tests/test_public_safety.py,
  scripts/live_regression.py, channels/sms.py Protocol+backends, build log).
  Agent 1 retains full veto at merge time.
- **Test counts made durable** ("50+") — main's suite moved 53 → 58 during the
  same day and is still growing; exact numbers in evergreen copy rot fast.
- Future upgrade candidate (Agent 1's call): blog 3 could gain a second act —
  the 22-scenario harder library (.64 live baseline) and the
  SafetyEnsembleProvider autoresearch result now documented in
  docs/research/aug21-summary.md.
