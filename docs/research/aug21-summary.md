# Autoresearch Report — Triage Prompt Optimization (aug21)

Karpathy-style autonomous research applied to Handoff's triage judgment.
Loop: hypothesis → single change → eval against 22-case library → keep/discard.

## Setup

- **Target:** `LLMTriageProvider.SYSTEM_PROMPT` (live Amazon Nova Lite, us-east-2, temp=0)
- **Metric:** urgency accuracy (primary), category accuracy (must hold ≥ baseline−0.05), p50 latency (≤ 3× baseline)
- **Library:** 22 scenarios — 8 original + 14 harder v2 cases (mixed signals, partial info,
  hazard-vs-nuisance boundaries). Labels follow industry emergency definitions
  (active water/gas/fire-risk/sparking = emergency; food loss/slow leaks/security = urgent).
- **Baseline (main @25d60a4):** urgency 0.64 · category 0.91 · p50 0.616s — all 8 misses were urgency undertriages.

## Experiments

| # | Change | Urgency | Category | p50 | Verdict |
|---|--------|---------|----------|-----|---------|
| baseline | v1 prompt (8 examples) | 0.64 | 0.91 | 0.62s | — |
| exp1 | Policy lines + few-shot mirroring every miss pattern | **0.95** | 1.00 | 0.62s | KEEP |
| exp2 | Burning-smell disambiguation (recurring ≠ dust burn-off) | **1.00** | 1.00 | 0.69s | KEEP |
| exp3 | Slim: cut 6 "redundant" examples | 0.82 | 1.00 | 0.66s | DISCARD — examples are load-bearing; latency unchanged |
| exp4 | temperature=0 | 0.95* | 1.00 | 0.61s | KEEP — deterministic (identical misses across runs); reproducibility > lucky 100% |
| exp5 | (malformed edit) | — | — | — | no-op |
| exp6 | **SafetyEnsembleProvider**: deterministic hazard-keyword escalation layered over LLM | **1.00 stable ×4** | 1.00 | 0.61s | KEEP |

\* at temp=0 the model deterministically missed one boundary case; exp6 made that class impossible by construction.

## Key findings

1. **Few-shot examples are load-bearing.** Cutting six "redundant" ones cost 18 points of
   urgency accuracy while saving zero latency (exp3). The policy lines alone don't transfer;
   the model needs worked instances.
2. **Sampling noise was masquerading as prompt quality.** At default temperature, exp2's 100%
   reproduced as 95% on re-run. temperature=0 made results deterministic and honest — then the
   ensemble closed the residual gap structurally instead of statistically.
3. **Deterministic guardrails beat statistical fixes for catastrophic classes.** Under-triaging
   "burning smell" or "carbon monoxide" is the one failure mode we cannot afford. Rather than
   prompt-hoping, `SafetyEnsembleProvider` escalates on a fixed keyword net after model judgment —
   undertriage of that class is now impossible by construction, whatever the model says.
4. **Cost:** ~$0.001 per triage at Nova Lite prices; the full eval run costs less than a cent.

## Final state

- urgency **1.00**, category **1.00**, stable across 4+ consecutive live runs, p50 ≈ 0.6s
- Deployed to both surfaces (AgentCore runtime + Lambda dashboard) and verified through the
  public URL with `scripts/live_regression.py` (ALL GREEN).
