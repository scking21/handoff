"""Eval gate: the heuristic provider must hold the floor in CI.

The Bedrock-backed provider gets held to a higher floor before deploy using
the same harness (see evals/triage_evals.py).
"""

from __future__ import annotations

from handoff.agents.decisions import HeuristicTriageProvider
from handoff.evals.triage_evals import evaluate


def test_heuristic_triage_meets_floor():
    report = evaluate(HeuristicTriageProvider())
    assert report["urgency_accuracy"] >= 0.85, f"urgency regressed: {report}"
    assert report["category_accuracy"] >= 0.75, f"category regressed: {report}"


def test_emergency_scenarios_never_undertriaged():
    """The catastrophic failure mode is calling an emergency routine."""
    report = evaluate(HeuristicTriageProvider())
    for row, scen in zip(report["rows"], SCENARIOS):
        if scen["expect_urgency"].value == "emergency":
            assert row["urgency_ok"], f"UNDERTRIAGED emergency: {scen['key']}"


from handoff.data.synth.generate import SCENARIOS  # noqa: E402
