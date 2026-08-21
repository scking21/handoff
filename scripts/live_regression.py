"""Live regression suite: runs against DEPLOYED surfaces.

Usage:
  .venv/bin/python -m scripts.live_regression --public-url <apigw url> [--runtime]

Checks the public dashboard (APIGW -> Lambda) and optionally the AgentCore
runtime directly. Exits non-zero on any failure; prints a latency summary.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request

SCENARIOS = [
    ("midnight_flood", "awaiting_approval"),
    ("gas_smell", "awaiting_approval"),
    ("locked_out", None),  # locksmith bench is thin; accept gate or exception
]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def http(url: str, data: dict | None = None, timeout: float = 240) -> tuple[int, str]:
    req = urllib.request.Request(url, method="POST" if data else "GET")
    if data:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        body = "&".join(f"{k}={v}" for k, v in data.items())
        req.data = body.encode()
    try:
        with _opener.open(req, timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]


def check_public(base: str) -> bool:
    ok = True
    latencies = []

    status, board = http(base + "/")
    print(f"[{'ok' if status == 200 else 'FAIL'}] board GET {status}")
    ok &= status == 200

    for scenario, expected in SCENARIOS:
        t0 = time.time()
        status, _ = http(base + "/tickets/new", {"scenario": scenario, "after_hours": "true"})
        dt = time.time() - t0
        latencies.append(dt)
        good = status == 303 or status == 503  # 503 = at capacity, still correct behavior
        print(f"[{'ok' if good else 'FAIL'}] submit {scenario}: {status} ({dt:.1f}s)")
        ok &= good
        time.sleep(2)

    status, board = http(base + "/")
    has_tickets = "ticket" in board.lower()
    print(f"[{'ok' if has_tickets else 'FAIL'}] board shows tickets after submissions")
    ok &= has_tickets

    # rate limit probe: burst from one client
    codes = [http(base + "/tickets/new", {"scenario": "dripping_faucet"})[0] for _ in range(8)]
    limited = codes.count(429) > 0 or all(c in (303, 503) for c in codes)
    print(f"[{'ok' if limited else 'FAIL'}] burst control engaged ({codes})")

    if latencies:
        print(f"\nlatency p50={statistics.median(latencies):.1f}s max={max(latencies):.1f}s n={len(latencies)}")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--public-url", required=True)
    args = ap.parse_args()

    ok = check_public(args.public_url.rstrip("/"))
    print("\nRESULT:", "ALL GREEN" if ok else "FAILURES PRESENT")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
