"""VendorSim: policy-fidelity evaluation for vendor selection.

Each case describes a dispatch decision with an intuitively correct answer
(the choice a competent coordinator would make). The metric is agreement:
how often the weighted scorer picks the intended vendor. This is the eval
the autoresearch loop hill-climbs VendorWeights against.

Usage: .venv/bin/python -m scripts.vendorsim_eval --json
"""

from __future__ import annotations

import json
import statistics
import time

from handoff.domain.models import Trade, Urgency
from handoff.workflow.vendor_policy import DEFAULTS, VendorWeights, score_vendor


def _v(id: str, company: str, rating=4.0, rate=80, trip=50, drive=30,
       jobs=0, no_shows=0, on_call=False) -> dict:
    return {
        "id": id, "company": company, "rating": rating, "hourly_rate": rate,
        "trip_fee": trip, "drive_minutes": drive, "open_jobs": jobs,
        "no_show_count": no_shows, "on_call_now": on_call, "certifications": [],
    }


CASES: list[dict] = [
    # 1. Emergency reliability beats cheap-and-flaky
    dict(name="emergency_reliability",
         bench=[_v("cheap_flaky", "Cheap Flaky", rating=4.8, rate=70, drive=10, no_shows=4),
                _v("solid_oncall", "Solid OnCall", rating=4.2, rate=95, drive=25, no_shows=0, on_call=True)],
         category=Trade.PLUMBING, urgency=Urgency.EMERGENCY,
         expect="solid_oncall"),
    # 2. Routine identical vendors: cheaper wins
    dict(name="routine_price_tiebreak",
         bench=[_v("pricier", "Pricier", rating=4.5, rate=110),
                _v("cheaper", "Cheaper", rating=4.5, rate=75)],
         category=Trade.PLUMBING, urgency=Urgency.ROUTINE,
         expect="cheaper"),
    # 3. Identical except drive time: closer wins
    dict(name="drive_time_tiebreak",
         bench=[_v("far", "Far", rating=4.5, drive=55),
                _v("near", "Near", rating=4.5, drive=12)],
         category=Trade.GENERAL, urgency=Urgency.ROUTINE,
         expect="near"),
    # 4. Urgent: overloaded star vs available mid-tier
    dict(name="load_beats_rating_when_urgent",
         bench=[_v("star_busy", "Star Busy", rating=4.9, jobs=6, drive=15),
                _v("mid_free", "Mid Free", rating=4.1, jobs=0, drive=30)],
         category=Trade.HVAC, urgency=Urgency.URGENT,
         expect="mid_free"),
    # 5. Routine: quality premium acceptable (rating dominates)
    dict(name="routine_rating_preferred",
         bench=[_v("budget_low", "Budget Low", rating=3.4, rate=60),
                _v("quality_high", "Quality High", rating=4.8, rate=100)],
         category=Trade.APPLIANCE, urgency=Urgency.ROUTINE,
         expect="quality_high"),
    # 6. No-show history matters even for routine
    dict(name="no_show_penalty_routine",
         bench=[_v("flaky", "Flaky", rating=4.7, no_shows=5),
                _v("steady", "Steady", rating=4.0, no_shows=0)],
         category=Trade.ELECTRICAL, urgency=Urgency.ROUTINE,
         expect="steady"),
    # 7. Emergency on-call edge over slightly better offline
    dict(name="oncall_edge_emergency",
         bench=[_v("offline_better", "Offline Better", rating=4.6, drive=20),
                _v("oncall_ok", "OnCall OK", rating=4.3, drive=35, on_call=True)],
         category=Trade.PLUMBING, urgency=Urgency.EMERGENCY,
         expect="oncall_ok"),
    # 8. Non-emergency: on-call confers little; quality wins
    dict(name="oncall_irrelevant_routine",
         bench=[_v("oncall_mid", "OnCall Mid", rating=4.0, on_call=True),
                _v("office_star", "Office Star", rating=4.7)],
         category=Trade.HVAC, urgency=Urgency.ROUTINE,
         expect="office_star"),
    # 9. Load balancing across equal candidates (open jobs decide)
    dict(name="load_balance_equal",
         bench=[_v("swamped", "Swamped", rating=4.5, jobs=3),
                _v("light", "Light", rating=4.4, jobs=0)],
         category=Trade.ELECTRICAL, urgency=Urgency.URGENT,
         expect="light"),
    # 10. Combined penalties: decent-but-dirty record loses to clean average
    dict(name="clean_record_wins",
         bench=[_v("dirty_good", "Dirty Good", rating=4.8, no_shows=3, jobs=2, drive=40),
                _v("clean_avg", "Clean Avg", rating=4.0, no_shows=0, jobs=0, drive=20)],
         category=Trade.PLUMBING, urgency=Urgency.URGENT,
         expect="clean_avg"),
    # 11. Emergency: massive quality gap can overcome missing on-call
    dict(name="quality_gap_emergency",
         bench=[_v("ok_oncall", "OK OnCall", rating=3.6, on_call=True),
                _v("expert_offline", "Expert Offline", rating=4.9, drive=20)],
         category=Trade.ELECTRICAL, urgency=Urgency.EMERGENCY,
         expect="expert_offline"),
    # 12. Cost matters more when ratings are close and job is routine
    dict(name="close_ratings_cost_decides",
         bench=[_v("premium_close", "Premium Close", rating=4.3, rate=130),
                _v("value_close", "Value Close", rating=4.1, rate=70)],
         category=Trade.GENERAL, urgency=Urgency.ROUTINE,
         expect="value_close"),
]


def evaluate(weights: VendorWeights | None = None) -> dict:
    # NOTE: authored-case mode ignores `weights` overrides when tiers are
    # active — tiers come from vendor_policy.WEIGHTS_BY_URGENCY.
    rows = []
    latencies = []
    from handoff.workflow.vendor_policy import weights_for

    for case in CASES:
        t0 = time.perf_counter()
        tier_w = weights_for(case["urgency"])
        ranked = sorted(case["bench"], key=lambda v: score_vendor(v, tier_w, case["urgency"]), reverse=True)
        picked = ranked[0]["id"]
        latencies.append(time.perf_counter() - t0)
        rows.append({
            "case": case["name"],
            "picked": picked,
            "expected": case["expect"],
            "ok": picked == case["expect"],
        })
    n = len(rows)
    return {
        "provider": "VendorWeights(tiered)",
        "n": n,
        "urgency_accuracy": sum(r["ok"] for r in rows) / n,   # policy fidelity
        "category_accuracy": 1.0,                              # placeholder parity with triage schema
        "latency_p50_s": round(statistics.median(latencies), 6) if latencies else 0,
        "latency_max_s": round(max(latencies), 6) if latencies else 0,
        "rows": rows,
    }


def misses(d: dict) -> list[str]:
    return [r["case"] for r in d["rows"] if not r["ok"]]


if __name__ == "__main__":
    d = evaluate()
    print(f"policy fidelity: {d['urgency_accuracy']:.0%} ({d['n']} cases)")
    for r in d["rows"]:
        print(f"  {'✓' if r['ok'] else '✗'} {r['case']}: picked {r['picked']}")
    m = misses(d)
    if m:
        print("misses:", m)


# ---------------------------------------------------------------------------
# Statistical mode: randomized benches vs an explicit lexicographic reference.
#
# Reference policy (the documented intent, applied in strict priority order):
#   EMERGENCY: disqualify vendors with no_show_count >= 3 unless none remain;
#              prefer on-call; then rating; then drive time.
#   URGENT:    prefer low no-show count; then open_jobs <= 1; then rating;
#              then drive.
#   ROUTINE:   best value = rating per dollar-of-rate; then drive; then load.
def reference_pick(bench: list[dict], urgency) -> str | None:
    from handoff.domain.models import Urgency

    if not bench:
        return None

    def key_routine(v):
        return (-(v["rating"] / max(v["hourly_rate"], 1)),
                v["drive_minutes"], v["open_jobs"])

    def key_urgent(v):
        return (v["no_show_count"], 0 if v["open_jobs"] <= 1 else 1,
                -v["rating"], v["drive_minutes"])

    def key_emergency(v):
        clean = [x for x in bench if x["no_show_count"] < 3]
        pool = clean or bench
        oncall = [x for x in pool if x.get("on_call_now")]
        pool = oncall or pool
        return None, pool

    if urgency == Urgency.EMERGENCY:
        _, pool = key_emergency(bench)
        return min(pool, key=lambda v: (-v["rating"], v["drive_minutes"],
                                        v["no_show_count"]))["id"]
    if urgency == Urgency.URGENT:
        return min(bench, key=key_urgent)["id"]
    return min(bench, key=key_routine)["id"]


def generate_random_bench(rng, urgency) -> list[dict]:
    import random

    n = rng.randint(2, 4)
    out = []
    trades = ["Alpha", "Bravo", "Charlie", "Delta"]
    for i in range(n):
        emergency = urgency == Urgency.EMERGENCY
        out.append(_v(
            f"v{i}", f"{trades[i % len(trades)]}{i}",
            rating=round(rng.uniform(3.2, 5.0), 1),
            rate=rng.randint(60, 140),
            trip=rng.choice([0, 30, 50, 75]),
            drive=rng.randint(5, 60),
            jobs=rng.randint(0, 6),
            no_shows=rng.randint(0, 5),
            on_call=(emergency and rng.random() < 0.45) or rng.random() < 0.2,
        ))
    return out


def evaluate_random(weights: VendorWeights | None = None, n_cases: int = 500,
                    seed: int = 20260821) -> dict:
    """Agreement between the linear weighted scorer and the lexicographic
    reference across randomized dispatch decisions."""
    import random

    w = weights or DEFAULTS
    rng = random.Random(seed)
    urgencies = [Urgency.EMERGENCY, Urgency.URGENT, Urgency.ROUTINE,
                 Urgency.ROUTINE, Urgency.URGENT]  # realistic mix
    rows = []
    latencies = []
    for i in range(n_cases):
        urgency = urgencies[i % len(urgencies)]
        bench = generate_random_bench(rng, urgency)
        expected = reference_pick(bench, urgency)
        t0 = time.perf_counter()
        ranked = sorted(bench, key=lambda v: score_vendor(v, w, urgency), reverse=True)
        latencies.append(time.perf_counter() - t0)
        picked = ranked[0]["id"]
        rows.append({"case": f"rand_{i}", "picked": picked,
                     "expected": expected, "ok": picked == expected})
    n = len(rows)
    return {
        "provider": "VendorWeights",
        "n": n,
        "urgency_accuracy": sum(r["ok"] for r in rows) / n,  # fidelity
        "category_accuracy": 1.0,
        "latency_p50_s": round(statistics.median(latencies), 6),
        "latency_max_s": round(max(latencies), 6),
        "rows": rows,
    }
