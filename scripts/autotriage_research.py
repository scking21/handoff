"""Autoresearch loop for Handoff triage prompts.

Karpathy-style: the model proposes its own prompt mutations, the eval harness
scores them on the live scenario library, and a hill-climber keeps wins.
State lives in results.tsv; each iteration is one git commit (kept) or a
checkout (discarded).

Usage:
  .venv/bin/python -m scripts.autotriage_research --iterations 6
Requires AWS creds (runs the real Bedrock model for both proposals and evals).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ROOT / "src" / "handoff" / "agents" / "decisions.py"
RESULTS = ROOT / "results.tsv"

MUTATOR_PROMPT = """You are optimizing a classification system prompt for a property-maintenance
triage agent. The prompt classifies tenant reports into urgency (emergency/urgent/routine),
category (plumbing/hvac/electrical/appliance/general/locksmith), and confidence.

Current accuracy issues to consider: {context}

{goal}

Rules:
- Change ONE thing per edit: add/remove/reword at most two lines (policy statement or example).
- Never weaken emergency coverage.
- If asked to simplify: merge or drop redundant examples while keeping one worked example
  per decision boundary (water intrusion, gas, electrical hazard, lockout, CO/smoke detector,
  slow leak, partial hot water, lock integrity, appliance-vs-plumbing boundary).
- Output ONLY the full rewritten system prompt inside <PROMPT> tags."""


def read_prompt() -> str:
    src = DECISIONS.read_text()
    m = re.search(r'SYSTEM_PROMPT = \(\n(.*?)\n    \)', src, re.S)
    assert m, "SYSTEM_PROMPT not found"
    # join the implicit-concatenated strings and strip quotes/newlines-escapes
    raw = m.group(1)
    parts = re.findall(r'"((?:[^"\\]|\\.)*)"', raw)
    return "".join(p.encode().decode("unicode_escape") for p in parts)


def write_prompt(new_prompt: str) -> None:
    """Single long literal — never chunk (splitting escapes corrupts the
    string). Validate the file compiles before committing to disk state."""
    src = DECISIONS.read_text()
    m = re.search(r'SYSTEM_PROMPT = \(\n.*?\n    \)', src, re.S)
    assert m, "SYSTEM_PROMPT block not found"
    escaped = json.dumps(new_prompt)  # includes surrounding quotes, safe escapes
    replacement = f"SYSTEM_PROMPT = (\n        {escaped}\n    )"
    candidate = src[:m.start()] + replacement + src[m.end():]
    compile(candidate, str(DECISIONS), "exec")  # raises on malformed output
    DECISIONS.write_text(candidate)


def run_eval() -> dict:
    import os

    env = dict(os.environ)
    env.update({"AWS_PROFILE": "handoff", "AWS_REGION": "us-east-2",
                "HANDOFF_MODEL_PROVIDER": "bedrock"})
    out = subprocess.run(
        [".venv/bin/python", "-m", "handoff.evals.triage_evals", "--json"],
        capture_output=True, text=True, cwd=ROOT, env=env,
    ).stdout
    return json.loads(out.strip().splitlines()[-1])


MUTATOR_PROMPT = """You are optimizing a classification system prompt for a property-maintenance
triage agent. The prompt classifies tenant reports into urgency (emergency/urgent/routine),
category (plumbing/hvac/electrical/appliance/general/locksmith), and confidence.

Current accuracy issues to consider: {context}

{goal}

Rules:
- Change ONE thing per edit: add/remove/reword at most two lines (policy statement or example).
- Never weaken emergency coverage.
- If asked to simplify: merge or drop redundant examples while keeping at least one worked
  example per decision boundary (water intrusion, gas odor, electrical hazard, lockout,
  CO/smoke detector, slow leak, partial hot water loss, lock integrity, appliance vs plumbing).
- Output ONLY the full rewritten system prompt inside <PROMPT> tags."""


def propose(prompt: str, misses: list[str], model, simplify: bool) -> str:
    from strands import Agent

    ctx = "; ".join(misses) if misses else "none"
    goal = (
        "GOAL: fix these misses with a minimal targeted edit."
        if not simplify else
        "GOAL: accuracy is perfect — SHORTEN the prompt by ~30% without losing any decision boundary."
    )
    agent = Agent(model=model, callback_handler=None,
                  system_prompt=MUTATOR_PROMPT.replace("{context}", ctx).replace("{goal}", goal))
    result = agent(f"<PROMPT>\n{prompt}\n</PROMPT>")
    text = str(result)
    m = re.search(r"<PROMPT>(.*?)</PROMPT>", text, re.S)
    candidate = m.group(1).strip() if m else text.strip()
    return candidate if candidate != prompt else ""


def score(d: dict) -> float:
    return d["urgency_accuracy"] + d["category_accuracy"]


def log_row(commit: str, d: dict, status: str, desc: str) -> None:
    with RESULTS.open("a") as f:
        f.write(f"{commit}\t{d['urgency_accuracy']:.2f}\t{d['category_accuracy']:.2f}\t"
                f"{d['latency_p50_s']:.3f}\t{status}\t{desc}\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=4)
    args = ap.parse_args()

    baseline = run_eval()
    base_score = score(baseline)
    misses = [r["scenario"] for r in baseline["rows"]
              if not (r["urgency_ok"] and r["category_ok"])]
    print(f"baseline score={base_score:.2f} urgency={baseline['urgency_accuracy']:.2f} "
          f"category={baseline['category_accuracy']:.2f} misses={misses}")

    from handoff.agents.decisions import build_bedrock_model
    model = build_bedrock_model()

    for i in range(args.iterations):
        prompt = read_prompt()
        mutation = propose(prompt, misses, model, simplify=(base_score >= 2.0))
        if not mutation or mutation == prompt:
            print(f"[{i}] mutator returned no usable change — skipping")
            continue

        write_prompt(mutation)
        try:
            d = run_eval()
        except Exception:
            print(f"[{i}] eval crashed on mutation — discarding")
            subprocess.run(["git", "checkout", "--", str(DECISIONS.relative_to(ROOT))], cwd=ROOT)
            continue

        s = score(d)
        new_misses = [r["scenario"] for r in d["rows"]
                      if not (r["urgency_ok"] and r["category_ok"])]

        keep = s > base_score or (s == base_score and len(json.dumps(mutation)) < len(json.dumps(prompt)))
        commit = ""
        if keep:
            c = subprocess.run(["git", "add", "-A"], cwd=ROOT)
            c = subprocess.run(["git", "commit", "-q", "-m", f"autoresearch iter{i}: score {s:.2f}"],
                               cwd=ROOT, capture_output=True, text=True)
            commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                    capture_output=True, text=True).stdout.strip()
            base_score = s
            misses = new_misses
        else:
            subprocess.run(["git", "checkout", "--", str(DECISIONS.relative_to(ROOT))], cwd=ROOT)

        status = ("keep" if keep and commit else
                  "keep-simplified" if keep else "discard")
        desc = f"iter{i}: len={len(mutation)}"
        if commit:
            log_row(commit, d, status, desc)
        else:
            with RESULTS.open("a") as f:
                f.write(f"uncommitted\t{d['urgency_accuracy']:.2f}\t{d['category_accuracy']:.2f}\t"
                        f"{d['latency_p50_s']:.3f}\tdiscard\t{desc}\n")
        print(f"[{i}] score={s:.2f} urgency={d['urgency_accuracy']:.2f} "
              f"category={d['category_accuracy']:.2f} -> {status}")

    print("\ndone. results.tsv:")
    print(RESULTS.read_text())


if __name__ == "__main__":
    main()
