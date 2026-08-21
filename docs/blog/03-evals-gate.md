# Agent judgment is testable. Test it like code.

> builder.aws.com post 3 of 3 · evals gate
> Status: DRAFT — publish after Bedrock triage evals run on the live model

"Does the agent classify emergencies correctly?" is not a vibe question, and
eyeballing a demo doesn't answer it. Before Handoff (our Agents for Humans
build) dispatches anything to a real vendor, its triage judgment has to pass a
gate — the same way code passes CI. Same pipeline, same fail-the-build rule.

## The harness

We keep a scenario library of judgment-heavy maintenance reports: a midnight
ceiling flood, a gas smell near the stove, "the AC makes a weird noise
sometimes," a locked-out tenant standing outside with groceries. Eight
scenarios so far, each carrying expected urgency and category labels. The eval
runner replays every scenario through whatever provider is configured —
deterministic rules in CI, Claude via Amazon Bedrock before deploy — and scores
both axes:

```python
def evaluate(provider: TriageProvider) -> dict:
    for scen in SCENARIOS:
        d = provider.classify(scen["raw"], list(scen["photos"]))
        rows.append({
            "scenario": scen["key"],
            "urgency_ok": d.urgency == scen["expect_urgency"],
            "category_ok": d.category == scen["expect_category"],
            "confidence": d.confidence,
        })
    ...
    return {"urgency_accuracy": ..., "category_accuracy": ..., "rows": rows}
```

Running it today against the heuristic provider:

```text
provider=HeuristicTriageProvider  n=8
urgency accuracy : 100%
category accuracy: 100%
  midnight_flood         urgency=✓ category=✓ conf=0.90
  gas_smell              urgency=✓ category=✓ conf=0.80
  no_heat_winter         urgency=✓ category=✓ conf=0.76
  vague_noise            urgency=✓ category=✓ conf=0.60
  ...
```

That's not a victory lap — it's the point. The heuristics *earned* that table,
and the library is what made every fix measurable instead of vibes.

Two design choices matter more than they look:

## The floor is asymmetric by failure mode

The catastrophic error is calling an emergency *routine* — a flood that waits
until morning because the agent wanted a balanced scorecard. Over-triage costs
money; under-triage costs trust and habitability. We price them differently, so
beyond the aggregate accuracy floor there's a dedicated test that refuses to
pass while any emergency is under-triaged:

```python
def test_emergency_scenarios_never_undertriaged():
    """The catastrophic failure mode is calling an emergency routine."""
    report = evaluate(HeuristicTriageProvider())
    for row, scen in zip(report["rows"], SCENARIOS):
        if scen["expect_urgency"].value == "emergency":
            assert row["urgency_ok"], f"UNDERTRIAGED emergency: {scen['key']}"
```

Aggregate thresholds can regress a little (`>= 0.85` urgency, `>= 0.75`
category); this one can't regress at all.

## Confidence is honest, or the human queue fills up

Every classification ships a confidence score; below 0.55 the ticket escalates
instead of acting. That number lives in one place —

```python
CONFIDENCE_FLOOR = 0.55  # below this, triage goes to a human instead of guessing
```

— and it turns "the model wasn't sure" from a silent failure into a visible
queue with an owner. An agent that never says "not sure" isn't confident;
it's unaudited.

## What the misses taught us

The scenario library earned its keep while we built the scorer. Three failure
modes forced fixes, and each fix is still visible in the weighted-hint table
that drives classification:

- **"Locked myself out" scored nothing** because the emergency hint list only
  indexed "locked out." People don't say it that way. Now the hints include
  "locked myself out" and "standing outside."
- **A dishwasher leak categorized as plumbing** because generic symptom words
  outranked specific fixtures. Fix: fixture nouns ("dishwasher", "fridge",
  "oven") carry triple weight over generic symptoms — the comment in the
  scoring table literally reads "specific fixtures outrank generic symptoms"
  now.
- **Water pouring through a ceiling light fixture classified as electrical**
  because the fixture outranked the water. Wrong trade shows up with a toolbox
  full of wire strippers. Fix: source-of-water signals ("pouring", "ceiling")
  indicate the trade that must respond, not the location of the symptom.

None of those were model problems. They were specification problems, and the
harness surfaced each one in seconds. That's the argument of this whole post:
agent judgment is testable, and the test belongs in the same pipeline as
everything else you ship. When the Bedrock provider lands, nothing about the
gate changes — the model just has to clear the same bar the rules did.
