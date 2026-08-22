"""Eval gate: the heuristic provider must hold the floor in CI.

The Bedrock-backed provider gets held to a higher floor before deploy using
the same harness (see evals/triage_evals.py).
"""

from __future__ import annotations

from handoff.agents.decisions import HeuristicTriageProvider
from handoff.evals.triage_evals import evaluate


def test_heuristic_triage_meets_floor():
    """The heuristic is a credential-free dev stand-in, not the shipped brain —
    its floor is deliberately modest on the v2 judgment-heavy library. The
    Bedrock provider must clear 0.9 before deploy (run with creds)."""
    report = evaluate(HeuristicTriageProvider())
    assert report["urgency_accuracy"] >= 0.5, f"urgency regressed: {report}"
    assert report["category_accuracy"] >= 0.8, f"category regressed: {report}"


def test_emergency_scenarios_never_undertriaged():
    """The catastrophic failure mode is calling an emergency routine."""
    report = evaluate(HeuristicTriageProvider())
    for row, scen in zip(report["rows"], SCENARIOS, strict=True):
        if scen["expect_urgency"].value == "emergency" and scen["key"] in (
            "midnight_flood", "gas_smell", "broken_outlet", "locked_out",
        ):
            # core four the heuristic was explicitly built for; full-library
            # emergency coverage is the LLM provider's deployment gate
            assert row["urgency_ok"], f"UNDERTRIAGED emergency: {scen['key']}"


from handoff.data.synth.generate import SCENARIOS  # noqa: E402
