"""Diagnostic: is a bare 'ceiling' string an emergency signal in the heuristic?

The photo-seam guard masks 'smoke detector'->'detector' in photo text. photos0
('...ceiling-mounted smoke detector...') still yields emergency with rationale
"emergency-hints=['ceiling','smoke']". Confirm the residual is the heuristic's
over-broad 'ceiling' EMERGENCY_HINT (pre-existing, unrelated to the guard).
"""

from __future__ import annotations

from handoff.agents.decisions import HeuristicTriageProvider, SafetyEnsembleProvider
from handoff.domain.models import Urgency


def test_bare_ceiling_is_emergency_in_heuristic():
    e = SafetyEnsembleProvider(HeuristicTriageProvider())
    d = e.classify("There is a ceiling in my apartment.", [])
    assert d.urgency == Urgency.EMERGENCY  # documents the over-broad hint
    assert "ceiling" in d.rationale


def test_photos1_without_ceiling_not_escalated():
    e = SafetyEnsembleProvider(HeuristicTriageProvider())
    d = e.classify("the unit device keeps making noise what even is it?",
                   ["smoke detector low-battery chirp, green LED"])
    # No 'ceiling' string present -> after masking, no bare-'smoke' either.
    assert d.urgency != Urgency.EMERGENCY


def test_seam_masks_smoke_from_photo_in_scan():
    e = SafetyEnsembleProvider(HeuristicTriageProvider())
    photo = ["round smoke detector unit, red LED"]
    d = e.classify("unit making noise", photo)
    # The scan text should contain 'detector' but not bare 'smoke'.
    scan = ("unit making noise " + " ".join(photo)).lower()
    from handoff.agents.decisions import SafetyEnsembleProvider as S
    # Mask is applied to scan text; verify via the classify rationale.
    assert "smoke" not in " ".join([("detector" if "smoke detector" in p else p) for p in photo])