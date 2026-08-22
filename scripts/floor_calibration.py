"""Confidence-floor calibration study.

The triage confidence floor decides which tickets dispatch autonomously and
which escalate to the human queue — currently 0.55 by intuition. This study:

1. Runs ONE live evaluation pass over the scenario library (Bedrock).
2. Sweeps the floor analytically across that capture, reporting for each
   value: effective dispatch accuracy, escalation burden, and — the metric
   that must never move — critical undertriage (emergencies dispatched as
   lesser urgencies).

Usage:
  AWS_PROFILE=handoff HANDOFF_MODEL_PROVIDER=bedrock \\
      .venv/bin/python -m scripts.floor_calibration [--json]
"""

from __future__ import annotations

import argparse
import json

from handoff.agents.decisions import get_triage_provider
from handoff.config import settings
from handoff.data.synth.generate import SCENARIOS


def capture() -> list[dict]:
    provider = get_triage_provider(settings.model_provider)
    rows = []
    for scen in SCENARIOS:
        d = provider.classify(scen["raw"], list(scen["photos"]))
        rows.append({
            "scenario": scen["key"],
            "expected_urgency": scen["expect_urgency"].value,
            "got_urgency": d.urgency.value,
            "category_ok": d.category == scen["expect_category"],
            "confidence": d.confidence,
        })
    return rows


def calibrate(rows: list[dict], floors) -> list[dict]:
    table = []
    for f in floors:
        dispatched = [r for r in rows if r["confidence"] >= f]
        escalated = len(rows) - len(dispatched)
        if dispatched:
            urg_ok = sum(1 for r in dispatched if r["got_urgency"] == r["expected_urgency"])
            cat_ok = sum(1 for r in dispatched if r["category_ok"])
            eff_acc = (urg_ok + cat_ok) / (2 * len(dispatched))
        else:
            eff_acc = 0.0
        # catastrophic: an emergency dispatched (not escalated) as something lesser,
        # or any dispatched row whose urgency was wrong at all counts via eff_acc;
        # this metric tracks ONLY the unrecoverable class.
        crit = sum(
            1 for r in dispatched
            if r["expected_urgency"] == "emergency" and r["got_urgency"] != "emergency"
        )
        table.append({
            "floor": round(f, 2),
            "dispatched": len(dispatched),
            "escalated": escalated,
            "escalation_rate": round(escalated / len(rows), 3),
            "effective_accuracy": round(eff_acc, 3),
            "critical_undertriage": crit,
        })
    return table


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows = capture()
    floors = [0.0, 0.3, 0.4, 0.5, 0.55, 0.6, 0.7, 0.8, 0.9, 0.95]
    table = calibrate(rows, floors)

    if args.json:
        print(json.dumps({"rows": rows, "calibration": table}))
        return

    print(f"{'floor':>6} {'dispatched':>10} {'esc_rate':>9} {'eff_acc':>8} {'crit_under':>10}")
    for t in table:
        print(f"{t['floor']:>6} {t['dispatched']:>10} {t['escalation_rate']:>9} "
              f"{t['effective_accuracy']:>8} {t['critical_undertriage']:>10}")


if __name__ == "__main__":
    main()
