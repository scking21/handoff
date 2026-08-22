"""Run the night-set adversarial scenarios through the live triage provider.

Usage (from repo root):
  PYTHONPATH=$PWD/src AWS_PROFILE=handoff AWS_REGION=us-east-2 \
  HANDOFF_MODEL_PROVIDER=bedrock .venv/bin/python -m scripts.night_run [--probe-only]

Appends one summary row to night_results.tsv and prints per-scenario detail.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from night_set import CHIRP_PROBE, NIGHT_SCENARIOS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "night_results.tsv"


def run(scenarios: list[dict], provider) -> dict:
    rows = []
    for scen in scenarios:
        d = provider.classify(scen["raw"], list(scen["photos"]))
        u_ok = d.urgency == scen["expect_urgency"]
        c_ok = d.category == scen["expect_category"]
        rows.append({"key": scen["key"], "u_ok": u_ok, "c_ok": c_ok,
                     "got": f"{d.urgency.value}/{d.category.value}",
                     "want": f"{scen['expect_urgency'].value}/{scen['expect_category'].value}",
                     "conf": d.confidence, "rationale": d.rationale[:120],
                     "why": scen["rationale"]})
    n = len(rows)
    return {"n": n,
            "urg": sum(r["u_ok"] for r in rows) / n if n else 0.0,
            "cat": sum(r["c_ok"] for r in rows) / n if n else 0.0,
            "rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe-only", action="store_true")
    args = ap.parse_args()

    from handoff.agents.decisions import get_triage_provider
    provider = get_triage_provider("bedrock")

    cases = [CHIRP_PROBE] if args.probe_only else NIGHT_SCENARIOS
    report = run(cases, provider)

    print(f"n={report['n']}  urgency={report['urg']:.2f}  category={report['cat']:.2f}")
    for r in report["rows"]:
        mark = "OK " if (r["u_ok"] and r["c_ok"]) else "MISS"
        print(f"  [{mark}] {r['key']:<28} want={r['want']:<22} got={r['got']:<22} conf={r['conf']:.2f}")
        if not (r["u_ok"] and r["c_ok"]):
            print(f"        why-labeled: {r['why']}")
            print(f"        model-rationale: {r['rationale']}")

    ts = datetime.now().strftime("%H:%M:%S")
    with RESULTS.open("a") as f:
        f.write(f"{ts}\tnight\t{report['n']}\t{report['urg']:.2f}\t{report['cat']:.2f}\n")

    misses = [r for r in report["rows"] if not (r["u_ok"] and r["c_ok"])]
    if misses and not args.probe_only:
        print("\nMISSES for prompt-mutation targets:")
        for r in misses:
            print(f"  {r['key']}: got {r['got']}, expected {r['want']} — {r['why']}")


if __name__ == "__main__":
    main()
