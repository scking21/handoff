"""Trace exactly what reaches the heuristic inner and its keyword scan."""

from __future__ import annotations

from handoff.agents.decisions import HeuristicTriageProvider, SafetyEnsembleProvider


def test_dump_paths():
    e = SafetyEnsembleProvider(HeuristicTriageProvider())
    raw = "the unit device keeps making noise what even is it?"
    photos = ["modern smoke detector mounted up high, red blinking light"]
    text = (raw + " " + " ".join(photos)).lower()
    chatter = e._smoke_detector_chatter(text)

    # Replicate the mask exactly as classify does for a heuristic inner.
    import re
    masked = lambda t: t if not chatter else e._SMOKE_DETECTOR_RE.sub("detector", t)
    inner_raw = masked(raw)
    inner_photos = [masked(p) for p in photos]
    scan_text = (inner_raw + " " + " ".join(inner_photos)).lower()

    print("\nchatter =", chatter)
    print("inner_raw   =", repr(inner_raw))
    print("inner_photo =", repr(inner_photos))
    print("scan_text   =", repr(scan_text))
    print("'smoke' in scan_text =", "smoke" in scan_text)

    import inspect
    src = inspect.getsource(SafetyEnsembleProvider.classify)
    print("\n--- classify source ---")
    print(src)