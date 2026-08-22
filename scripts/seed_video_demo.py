"""Seed the dashboard to the exact state the demo video needs.

Run before recording, against a LOCAL dashboard (or fresh deployment):
  .venv/bin/python -m scripts.seed_video_demo --base http://127.0.0.1:8731

Produces: clean world, one flood ticket sitting in AWAITING APPROVAL (the
cold-open shot), one routine ticket DISPATCHED (mid-demo contrast), nothing
else. Board looks alive but uncluttered.
"""

from __future__ import annotations

import argparse
import urllib.error
import urllib.request


def http(base: str, path: str, data: dict | None = None) -> int:
    req = urllib.request.Request(base + path, method="POST" if data else "GET")
    if data:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        req.data = "&".join(f"{k}={v}" for k, v in data.items()).encode()
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=240) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8731")
    args = ap.parse_args()

    print("cold open ticket (after-hours flood -> gate)...")
    s = http(args.base, "/tickets/new", {"scenario": "midnight_flood", "after_hours": "true"})
    print(" ", s)

    print("contrast ticket (routine dispatch)...")
    s = http(args.base, "/tickets/new", {"scenario": "dripping_faucet"})
    print(" ", s)

    board = http(args.base, "/")
    print("board:", board)
    print("ready to record.")


if __name__ == "__main__":
    main()
