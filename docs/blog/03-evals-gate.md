# Draft: Evaluating agent judgment before you deploy it

> builder.aws.com post 3 of 3 · evals gate
> Status: DRAFT — publish after Bedrock triage evals run on the live model

"Does the agent classify emergencies correctly?" is not a vibe question. Before
Handoff (our Agents for Humans build) ever dispatches a real vendor, its triage
judgment has to pass a gate — the same way code passes CI.

## The harness

We keep a scenario library of judgment-heavy maintenance reports: a midnight
ceiling flood, a gas smell, "the AC makes a weird noise sometimes," a locked-out
tenant with groceries. Each carries expected urgency and category labels. The
eval runner replays every scenario through whatever provider is configured —
deterministic rules in CI, Claude via Amazon Bedrock before deploy — and scores
urgency and category accuracy.

```python
report = evaluate(get_triage_provider(provider))
assert report["urgency_accuracy"] >= 0.85
```

Two design choices matter more than they look:

**The floor is asymmetric by failure mode.** The catastrophic error is calling an
emergency *routine* — a flood that waits until morning. So beyond aggregate
accuracy, a dedicated test asserts no emergency scenario is ever under-triaged.
Over-triage costs money; under-triage costs trust and habitability. We price them
differently.

**Confidence is honest or the human queue fills up.** Every classification ships a
confidence score; below 0.55 the ticket escalates instead of acting. That turns
"the model isn't sure" from a silent failure into a visible queue with an owner.

## What the evals caught

The first run scored 75% urgency / 88% category — and every miss was instructive.
"Locked myself out" missed the emergency hint list because we'd only indexed
"locked out." A dishwasher leak categorized as plumbing because generic symptom
words outranked specific fixtures — fixed by weighting specific nouns above
generic symptoms. Water pouring through a ceiling *light fixture* classified as
electrical because the fixture outranked the water — fixed by teaching the scorer
that source-of-water signals indicate the trade that must respond, not the
location of the symptom.

None of those are model problems; they're specification problems, and the harness
surfaced them in seconds. That's the point: agent judgment is testable, and the
test belongs in the same pipeline as everything else you ship.
