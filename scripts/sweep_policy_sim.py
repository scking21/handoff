"""Sweep-policy simulator: tune stall thresholds against a cost model.

Simulates ticket lifecycles under vendor-response latency distributions and
scores each policy configuration by total cost:

  cost = delay_cost (hours unresolved × tenant-dissatisfaction weight)
       + human_burden (each escalation costs PM attention)
       + stall_risk  (tickets stuck too long risk habitability/retention)

Sweeps: max_nudges before escalation, triaged-stall hours, approval-age hours.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics

from handoff.domain.models import Actor, TicketStatus, Trade, Urgency, WorkOrder


def simulate(config: dict, tickets: list[dict], rng: random.Random) -> dict:
    """Replay pre-generated vendor-latency draws through the policy.

    Each simulated ticket: {urgency, vendor_responds_after_h (or None = never),
    pm_response_h}. Policy: nudge every SWEEP_INTERVAL until max_nudges reached,
    then escalate. Escalation adds ESCALATE_DELAY_H to resolution.
    """
    max_nudges = config["max_nudges"]
    interval = config["sweep_interval_h"]

    delays = []
    escalations = 0
    never_resolved = 0

    for t in tickets:
        responds_after = t["vendor_responds_after_h"]
        if responds_after is None:
            # vendor never accepts: policy keeps nudging for max_nudges sweeps
            # then escalates; human re-dispatch takes REDISPATCH_H more hours.
            escalations += 1
            delays.append(max_nudges * interval + config["redispatch_h"])
            continue

        # vendor accepts after `responds_after` hours IF still being worked;
        # sweeps happen every `interval`; acceptance is noticed at next sweep
        notices = 0
        elapsed = 0.0
        resolved = False
        while elapsed < responds_after + config["redispatch_h"] * 0:
            notices += 1
            elapsed += interval
            if elapsed >= responds_after:
                # vendor accepted within this window
                resolved = True
                break
            if notices > max_nudges * 3:  # safety bound
                break
        if not resolved:
            escalations += 1
            never_resolved += 1
        delays.append(elapsed)

    mean_delay = statistics.mean(delays) if delays else 0
    cost = (
        mean_delay * config["delay_weight"]
        + escalations * config["escalation_weight"]
        + never_resolved * config["stall_weight"]
    )
    return {
        "mean_delay_h": round(mean_delay, 2),
        "escalations": escalations,
        "never_resolved": never_resolved,
        "cost": round(cost, 2),
    }


def gen_tickets(n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        r = rng.random()
        if r < 0.12:
            responds = None          # vendor ghosted entirely
        else:
            responds = round(rng.uniform(0.2, 30.0), 2)
        out.append({"vendor_responds_after_h": responds})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickets", type=int, default=400)
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()

    tickets = gen_tickets(args.tickets, args.seed)

    base = {
        "delay_weight": 10.0,     # per hour unresolved
        "escalation_weight": 15.0,# per PM interruption (real decision cost)
        "stall_weight": 200.0,    # never-resolved penalty
        "redispatch_h": 6.0,
    }

    print(f"{'nudges':>7} {'interval':>9} {'delay_h':>8} {'esc':>5} {'cost':>9}")
    results = []
    for max_nudges in [1, 2, 3, 4, 5]:
        for interval in [2, 4, 6, 8]:
            cfg = {**base, "max_nudges": max_nudges, "sweep_interval_h": interval}
            r = simulate(cfg, tickets, random.Random(args.seed))
            results.append((r["cost"], max_nudges, interval, r))
            print(f"{max_nudges:>7} {interval:>9} {r['mean_delay_h']:>8} "
                  f"{r['escalations']:>5} {r['cost']:>9}")

    results.sort(key=lambda x: x[0])
    best = results[0]
    print(f"\nBEST: max_nudges={best[1]} interval={best[2]}h cost={best[0]}")
    json.dump({"config": {"max_nudges": best[1], "sweep_interval_h": best[2]},
               "results": [{"cost": c, "max_nudges": m, "interval": i, **r}
                           for c, m, i, r in results]},
              open("/tmp/sweep_study.json", "w"), indent=2)


if __name__ == "__main__":
    main()
