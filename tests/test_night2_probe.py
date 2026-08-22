"""Identify the recurring night2 miss under guard v4."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from night_set2 import NIGHT_SCENARIOS_2  # noqa: E402
from night_run import run  # noqa: E402


import os
import pytest


@pytest.mark.skipif(
    not os.getenv("AWS_PROFILE"),
    reason="live Bedrock probe — requires AWS credentials",
)
def test_show_misses():
    from handoff.agents.decisions import get_triage_provider

    r = run(NIGHT_SCENARIOS_2, get_triage_provider("bedrock"))
    for row in r["rows"]:
        if not (row["u_ok"] and row["c_ok"]):
            print(f"MISS: {row['key']} want={row['want']} got={row['got']} conf={row['conf']}")
    assert True