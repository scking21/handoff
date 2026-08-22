"""Unit tests for the SafetyEnsembleProvider smoke-detector chatter guard.

Contract: the guard may ONLY suppress escalation when the sole 'smoke'
evidence is the device noun phrase + malfunction cue + no activation cue.
Real fire/smoke signals must still escalate. CO detectors never guarded.

Run: PYTHONPATH=src .venv/bin/python -m pytest tests/test_night_guard.py -q
"""

from __future__ import annotations

import pytest

from handoff.agents.decisions import HeuristicTriageProvider, SafetyEnsembleProvider
from handoff.domain.models import Urgency


def ensemble() -> SafetyEnsembleProvider:
    return SafetyEnsembleProvider(HeuristicTriageProvider())


CHIRP = ("The smoke detector in the hallway keeps chirping every 30 seconds. "
         "Pretty sure it just needs a new battery, it's driving us crazy.")


@pytest.mark.parametrize("text", [
    CHIRP,
    "Smoke detector is beeping low battery, swapped it but it chirps again.",
    "The smoke detector keeps giving false alarms when I cook.",
])
def test_chatter_not_escalated(text):
    d = ensemble().classify(text, [])
    assert d.urgency != Urgency.EMERGENCY


@pytest.mark.parametrize("text,why", [
    ("Smoke detector went off in the bedroom and there's smoke everywhere!",
     "activation + visible smoke"),
    ("The smoke detector won't stop sounding and I smell smoke from the kitchen.",
     "won't stop + smell smoke"),
    ("Smoke detector triggered, small kitchen fire on the stove.",
     "fire keyword"),
    ("There's smoke coming from the outlet and the smoke detector is beeping.",
     "real smoke present — device mention must not suppress"),
    ("Smoke detector went off, no battery issue I can find.",
     "went off beats trouble cue"),
])
def test_real_signals_still_escalate(text, why):
    d = ensemble().classify(text, [])
    assert d.urgency == Urgency.EMERGENCY, why


@pytest.mark.parametrize("text", [
    # Spelled out -> HAZARD_KEYWORDS hit -> unconditional escalation (main
    # library's co_detector_beeping contract preserved).
    "Carbon monoxide detector is beeping intermittently even after I opened "
    "the windows.",
])
def test_co_detectors_never_guarded(text):
    d = ensemble().classify(text, [])
    assert d.urgency == Urgency.EMERGENCY


def test_co_abbreviation_is_a_known_net_gap():
    # DOCUMENTED finding, not a regression: the hazard net matches
    # "carbon monoxide" but not the bare abbreviation "CO", so abbreviation-only
    # reports don't net-escalate (the LLM layer still judges them on context).
    # Reported to Agent 1 as suggested vocabulary addition.
    d = ensemble().classify("CO detector low battery chirp.", [])
    assert d.urgency != Urgency.EMERGENCY


def test_chatter_rationale_has_no_escalation_marker():
    d = ensemble().classify(CHIRP, [])
    assert "escalated" not in d.rationale


def test_other_keywords_unaffected():
    assert ensemble().classify("Water pouring through the ceiling!", []).urgency == Urgency.EMERGENCY
    assert ensemble().classify("I smell gas near the stove.", []).urgency == Urgency.EMERGENCY
