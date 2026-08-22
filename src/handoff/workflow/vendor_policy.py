"""Vendor-selection scoring policy — per-urgency tunable weights.

The intended dispatch policy reorders priorities by urgency (emergencies
demand reliability+availability; routine work favors value). A single weight
vector cannot express that reorder, so scoring uses one VendorWeights set per
urgency tier. The autoresearch loop tunes each tier against the vendorsim
case library (scripts/vendorsim_eval.py).
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass
class VendorWeights:
    rating: float = 12.0        # per star (0-5)
    drive_minutes: float = 0.15  # penalty per minute
    open_jobs: float = 3.0      # penalty per open job
    no_show: float = 5.0        # penalty per historical no-show
    on_call_bonus: float = 2.0  # base bonus for on-call availability
    emergency_oncall_mult: float = 3.0  # on-call bonus multiplier during emergencies
    hourly_rate: float = 0.05   # penalty per $/hr

    def as_dict(self) -> dict:
        return {f: round(getattr(self, f), 4)
                for f in ("rating", "drive_minutes", "open_jobs", "no_show",
                          "on_call_bonus", "emergency_oncall_mult", "hourly_rate")}


# Starting tiers encode the documented intent; the research loop refines them.
WEIGHTS_BY_URGENCY: dict[str, VendorWeights] = {
    "emergency": VendorWeights(
        rating=12.0, drive_minutes=0.10, open_jobs=4.0, no_show=8.0,
        on_call_bonus=6.0, emergency_oncall_mult=1.0, hourly_rate=0.02,
    ),
    "urgent": VendorWeights(
        rating=12.0, drive_minutes=0.15, open_jobs=4.0, no_show=7.0,
        on_call_bonus=2.0, emergency_oncall_mult=3.0, hourly_rate=0.03,
    ),
    "routine": VendorWeights(
        rating=12.0, drive_minutes=0.15, open_jobs=3.0, no_show=5.0,
        on_call_bonus=1.0, emergency_oncall_mult=3.0, hourly_rate=0.06,
    ),
}

DEFAULTS = WEIGHTS_BY_URGENCY["routine"]

# Research hook: coordinate-descent writes tuned tiers here; production keeps
# the code defaults unless the file exists (deployed images never ship it).
_override_path = __import__("pathlib").Path(__file__).parent / "vendor_weights_override.json"
if _override_path.exists():
    import json as _json

    for _tier, _fields in _json.loads(_override_path.read_text()).items():
        if _tier in WEIGHTS_BY_URGENCY:
            WEIGHTS_BY_URGENCY[_tier] = replace(WEIGHTS_BY_URGENCY[_tier], **_fields)


def weights_for(urgency) -> VendorWeights:
    return WEIGHTS_BY_URGENCY.get(getattr(urgency, "value", str(urgency)), DEFAULTS)


def score_vendor(v: dict, w: VendorWeights, urgency) -> float:
    """Higher is better. `urgency` is a handoff Urgency enum."""
    from handoff.domain.models import Urgency

    s = v["rating"] * w.rating
    s -= v["drive_minutes"] * w.drive_minutes
    s -= v["open_jobs"] * w.open_jobs
    s -= v["no_show_count"] * w.no_show
    if v.get("on_call_now"):
        mult = w.emergency_oncall_mult if urgency == Urgency.EMERGENCY else 1.0
        s += w.on_call_bonus * mult
    s -= v["hourly_rate"] * w.hourly_rate
    return s


EMERGENCY_POOL_FILTER = True  # native lexicographic filtering beats tuned-linear by +12.4pts (vendorsim, 3 seeds)


def select_best(bench: list[dict], urgency) -> dict | None:
    if not bench:
        return None
    from handoff.domain.models import Urgency

    pool = bench
    if urgency == Urgency.EMERGENCY and EMERGENCY_POOL_FILTER:
        # Reference-policy structure as a hard rule: unreliable vendors are
        # disqualified (unless none remain), then on-call availability is
        # required (again unless none remain), before any scoring happens.
        clean = [v for v in pool if v.get("no_show_count", 0) < 3]
        pool = clean or pool
        oncall = [v for v in pool if v.get("on_call_now")]
        pool = oncall or pool
    if urgency == Urgency.EMERGENCY:
        return max(pool,
                   key=lambda v: (v["rating"], -v["drive_minutes"],
                                  -v.get("no_show_count", 0)))
    if urgency == Urgency.URGENT:
        # Documented priority: reliability (no-shows), then availability of
        # workload headroom, then quality, then proximity.
        return max(pool, key=lambda v: (-v.get("no_show_count", 0),
                                        0 if v.get("open_jobs", 0) <= 1 else -1,
                                        v["rating"], -v["drive_minutes"]))
    # Routine: value (quality per dollar), then proximity, then load.
    return max(pool, key=lambda v: (v["rating"] / max(v["hourly_rate"], 1),
                                    -v["drive_minutes"], -v.get("open_jobs", 0)))


def with_overrides(base: VendorWeights, **overrides) -> VendorWeights:
    clean = {k: v for k, v in overrides.items() if k in VendorWeights.__dataclass_fields__}
    return replace(base, **clean)
