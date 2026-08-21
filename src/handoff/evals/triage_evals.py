"""Triage evaluation harness.

Replays the scenario library through any TriageProvider and scores urgency +
category accuracy. The same harness scores the heuristic provider in CI and
the Bedrock-backed provider before deploy — an eval gate, not vibes.
"""

from __future__ import annotations

from handoff.agents.decisions import TriageProvider, get_triage_provider
from handoff.config import settings
from handoff.data.synth.generate import SCENARIOS


def evaluate(provider: TriageProvider) -> dict:
    rows = []
    for scen in SCENARIOS:
        d = provider.classify(scen["raw"], list(scen["photos"]))
        rows.append(
            {
                "scenario": scen["key"],
                "urgency_ok": d.urgency == scen["expect_urgency"],
                "category_ok": d.category == scen["expect_category"],
                "confidence": d.confidence,
            }
        )
    n = len(rows)
    return {
        "provider": type(provider).__name__,
        "n": n,
        "urgency_accuracy": sum(r["urgency_ok"] for r in rows) / n,
        "category_accuracy": sum(r["category_ok"] for r in rows) / n,
        "rows": rows,
    }


def main() -> None:
    report = evaluate(get_triage_provider(settings.model_provider))
    print(f"provider={report['provider']}  n={report['n']}")
    print(f"urgency accuracy : {report['urgency_accuracy']:.0%}")
    print(f"category accuracy: {report['category_accuracy']:.0%}")
    for r in report["rows"]:
        marks = ("✓" if r["urgency_ok"] else "✗", "✓" if r["category_ok"] else "✗")
        print(f"  {r['scenario']:<22} urgency={marks[0]} category={marks[1]} conf={r['confidence']:.2f}")


if __name__ == "__main__":
    main()
