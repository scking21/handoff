"""Vendor-selection scoring policy — tunable weights.

The autoresearch loop hill-climbs DEFAULTS against the vendorsim case
library (scripts/vendorsim_eval.py): each case encodes an intuitively
"correct" dispatch decision, and the metric is policy fidelity — how often
the weighted scorer agrees with the intended choice.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VendorWeights:
    rating: float = 12.0        # per star (0-5)
    drive_minutes: float = 0.15  # penalty per minute
    open_jobs: float = 3.0      # penalty per open job
    no_show: float = 5.0        # penalty per historical no-show
    on_call_bonus: float = 2.0  # base bonus for on-call availability
    emergency_oncall_mult: float = 3.0  # on-call bonus multiplier during emergencies
    hourly_rate: float = 0.05   # penalty per $/hr


DEFAULTS = VendorWeights()


def score_vendor(v: dict, w: VendorWeights, urgency) -> float:
    """Higher is better. `urgency` is a handoff Urgency enum."""
    from handoff.domain.models import Urgency

    s = v["rating"] * w.rating
    s -= v["drive_minutes"] * w.drive_minutes
    s -= v["open_jobs"] * w.open_jobs
    s -= v["no_show_count"] * w.no_show
    if v.get("on_call_now"):
        s += w.on_call_bonus * (w.emergency_oncall_mult if urgency == Urgency.EMERGENCY else 1.0)
    s -= v["hourly_rate"] * w.hourly_rate
    return s
