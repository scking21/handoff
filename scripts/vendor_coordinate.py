"""Coordinate-descent optimizer for per-urgency VendorWeights.

For each urgency tier and each weight field, sweeps candidate multipliers,
evaluates randomized-fidelity on that tier's cases, and keeps the argmax.
Repeats rounds until no field improves. Writes final weights to
src/handoff/workflow/vendor_policy.py WEIGHTS_BY_URGENCY via a JSON sidecar
the module loads if present (vendor_weights_override.json), keeping the code
clean and the tuning data-driven.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys_paths = [str(ROOT / "src"), str(ROOT)]
for p in reversed(sys_paths):
    import sys
    if p not in sys.path:
        sys.path.insert(0, p)

from handoff.domain.models import Urgency  # noqa: E402
from handoff.workflow import vendor_policy as vp  # noqa: E402
from scripts.vendorsim_eval import (  # noqa: E402
    CASES as AUTHORED_CASES,
    evaluate_random, generate_random_bench, reference_pick,
)
from handoff.workflow.vendor_policy import score_vendor as _sv  # noqa: E402


def authored_fidelity(weights_map: dict) -> float:
    """HARD CONSTRAINT: the hand-authored business cases must stay at 100%.
    They encode contracts (quality premium matters, no-show history matters,
    emergency quality gaps matter) that pure statistical fitting will happily
    trade away."""
    ok = 0
    for case in AUTHORED_CASES:
        w = vp.VendorWeights(**weights_map[case["urgency"].value])
        ranked = sorted(case["bench"], key=lambda v: _sv(v, w, case["urgency"]), reverse=True)
        if ranked[0]["id"] == case["expect"]:
            ok += 1
    return ok / len(AUTHORED_CASES)

FIELDS = ["rating", "drive_minutes", "open_jobs", "no_show", "hourly_rate",
          "on_call_bonus", "emergency_oncall_mult"]
TIERS = ["emergency", "urgent", "routine"]

OVERRIDE_PATH = ROOT / "src" / "handoff" / "workflow" / "vendor_weights_override.json"


def load_overrides() -> dict:
    if OVERRIDE_PATH.exists():
        return json.loads(OVERRIDE_PATH.read_text())
    return {}


def save_overrides(data: dict) -> None:
    OVERRIDE_PATH.write_text(json.dumps(data, indent=2))


def apply_overrides() -> None:
    """Inject overrides into the live module (research-time hook)."""
    data = load_overrides()
    for tier, fields in data.items():
        base = vp.WEIGHTS_BY_URGENCY[tier]
        vp.WEIGHTS_BY_URGENCY[tier] = vp.with_overrides(base, **fields)


def tier_cases(tier: str, n: int, seed: int) -> list[tuple[Urgency, list[dict], str]]:
    rng = random.Random(seed)
    u = Urgency(tier)
    cases = []
    for _ in range(n):
        bench = generate_random_bench(rng, u)
        cases.append((u, bench, reference_pick(bench, u)))
    return cases


def fidelity(cases, weights_map: dict) -> float:
    ok = 0
    for u, bench, expected in cases:
        w = vp.VendorWeights(**weights_map[u])
        ranked = sorted(bench, key=lambda v: vp.score_vendor(v, w, u), reverse=True)
        if ranked[0]["id"] == expected:
            ok += 1
    return ok / len(cases)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--cases-per-tier", type=int, default=400)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    overrides = load_overrides()
    if not overrides:
        overrides = {t: vp.WEIGHTS_BY_URGENCY[t].as_dict() for t in TIERS}

    case_sets = {t: tier_cases(t, args.cases_per_tier, args.seed + i)
                 for i, t in enumerate(TIERS)}

    def current_fidelity() -> dict:
        return {t: fidelity(case_sets[t], overrides) for t in TIERS}

    fid = current_fidelity()
    print(f"start fidelity: {json.dumps({k: round(v, 3) for k, v in fid.items()})}", flush=True)

    multipliers = [0.5, 0.75, 1.25, 1.5, 2.0]
    rng = random.Random(args.seed)

    for rnd in range(args.rounds):
        improved_any = False
        for tier in TIERS:
            cases = case_sets[tier]
            for field in FIELDS:
                best_val = overrides[tier][field]
                best_fid = fid[tier]
                for m in multipliers:
                    cand = dict(overrides[tier])
                    floor = 1.0 if field == "rating" else 0.01
                    cand[field] = max(floor, cand[field] * m)
                    f = fidelity(cases, overrides | {tier: cand})
                    candidate_map = overrides | {tier: cand}
                    af = authored_fidelity(candidate_map)
                    if f > best_fid and af >= 1.0:
                        best_fid, best_val = f, cand[field]
                if abs(best_val - overrides[tier][field]) > 1e-9:
                    overrides[tier][field] = best_val
                    fid[tier] = best_fid
                    improved_any = True
                    print(f"  r{rnd} {tier}.{field} -> {best_val:.4f} "
                          f"(tier fidelity {best_fid:.3f})", flush=True)
        save_overrides(overrides)
        apply_overrides()
        fid = current_fidelity()
        print(f"round {rnd} done: {json.dumps({k: round(v, 3) for k, v in fid.items()})}", flush=True)
        if not improved_any:
            print("converged.")
            break

    overall = sum(fid.values()) / len(fid)
    print(f"\nfinal mean fidelity: {overall:.3f}")
    save_overrides(overrides)


if __name__ == "__main__":
    main()
