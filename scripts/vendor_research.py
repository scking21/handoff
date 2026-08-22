"""Overnight hill-climber for VendorWeights against the lexicographic reference.

Each iteration: jitter one or two weight fields -> score 500 randomized
dispatch decisions -> keep if fidelity improves, else revert. State lives in
results.tsv + git history on this branch.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.vendorsim_eval import evaluate_random  # noqa: E402
from handoff.workflow.vendor_policy import DEFAULTS, VendorWeights  # noqa: E402

RESULTS = ROOT / "results.tsv"
FIELDS = ["rating", "drive_minutes", "open_jobs", "no_show",
          "on_call_bonus", "emergency_oncall_mult", "hourly_rate"]


def fmt(w: VendorWeights) -> dict:
    return {f: round(getattr(w, f), 4) for f in FIELDS}


def run_eval(w: VendorWeights) -> dict:
    return evaluate_random(weights=w)


def total(d: dict) -> float:
    return d["urgency_accuracy"]


def jitter(w: VendorWeights, rng: random.Random) -> VendorWeights:
    """Perturb 1-2 fields by ±(5-25%), clamped to sign-preserving ranges."""
    kwargs = fmt(w)
    for _ in range(rng.randint(1, 2)):
        f = rng.choice(FIELDS)
        base = kwargs[f] if kwargs[f] != 0 else 0.05 * rng.choice([1, -1])
        factor = rng.uniform(0.75, 1.30)
        new = base * factor
        # clamp: penalties stay >= 0, rating stays positive, multipliers >= 0
        floor = 0.0 if f != "rating" else 1.0
        ceiling = 60.0 if f == "rating" else 200.0 if f == "hourly_rate" else 50.0
        new = max(floor, min(ceiling, new))
        kwargs[f] = new
    return VendorWeights(**kwargs)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=6)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    rng = random.Random(args.seed or int(time.time()))

    best_w = DEFAULTS
    best = run_eval(best_w)
    best_score = total(best)
    print(f"baseline fidelity={best_score:.3f} ({best['n']} cases)", flush=True)

    for i in range(args.iterations):
        cand_w = jitter(best_w, rng)
        d = run_eval(cand_w)
        s = total(d)
        keep = s > best_score
        desc = json.dumps(fmt(cand_w))
        if keep:
            best_w, best_score = cand_w, s
            Path(ROOT / "src" / "handoff" / "workflow" / "_vendor_weights_override.json").write_text(
                json.dumps(fmt(cand_w), indent=2))
            subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True)
            subprocess.run(["git", "commit", "-q", "-m",
                            f"vendor-weights iter{i}: fidelity {s:.3f} {desc}"],
                           cwd=ROOT, check=True)
            sha = git("rev-parse", "--short", "HEAD")
            with RESULTS.open("a") as f:
                f.write(f"{sha}\t{s:.3f}\t-\t{d['latency_p50_s']:.6f}\tkeep\tvendor-weights {desc}\n")
            print(f"[{i}] KEEP  fidelity={s:.3f} {desc}", flush=True)
        else:
            with RESULTS.open("a") as f:
                f.write(f"uncommitted\t{s:.3f}\t-\t{d['latency_p50_s']:.6f}\tdiscard\tvendor-weights {desc}\n")
            print(f"[{i}] discard fidelity={s:.3f} {desc}", flush=True)
        time.sleep(2)

    print(f"\nfinal best fidelity={best_score:.3f} weights={json.dumps(fmt(best_w))}")


if __name__ == "__main__":
    main()
