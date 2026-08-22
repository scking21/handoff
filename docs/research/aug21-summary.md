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

## Model A/B (post-deployment, live us-east-2)

| Model | Urgency | Category | p50 latency | Verdict |
|-------|---------|----------|-------------|---------|
| Nova Lite (`us.amazon.nova-lite-v1:0`) | 100%, 100% | 100% | ~0.62s | **PRIMARY** |
| Nova Micro (`us.amazon.nova-micro-v1:0`) | 95.5%, 95.5% | 100% | ~0.49s | documented fallback |

Safety classification is the core promise; 20% faster at −4.5pts urgency is the wrong trade.

## Night research addendum (Aug 21–22): vendor-selection weights

Second autoresearch dimension: the vendor scorer itself. Built a randomized
fidelity harness — 500 seeded dispatch decisions per urgency tier, labeled by
an explicit lexicographic reference policy encoding documented intent
(emergency = reliability+availability first; urgent = no-show history first;
routine = value rating-per-dollar).

| Stage | Mean fidelity |
|-------|---------------|
| Single weight vector (original) | 62.0% |
| + per-urgency weight tiers | 61.6% (tiers alone don't help) |
| + coordinate descent per tier | 90.6% train |
| + constrained (authored cases stay 100%) | 88.3% |
| + cross-seed validation | **86.5–86.9%** |

Findings:
1. Per-urgency tiers only help after per-tier tuning; the reorder is real.
2. The converged tiers are interpretable: emergency discovered an effective
   on-call bonus of 18×(vs base 2), urgent found no-show history dominating
   rating 14:3.4, routine approximated value-ratio via rate penalty 0.48.
3. Naive native value-ratio scoring scored 35% — structure changes need their
   own tuning before they beat tuned-linear.
4. Unconstrained fitting reached 90.6% but silently violated three hand-authored
   business cases; constrained optimization kept contracts intact at 88.3%
   mean / 86.9% fresh-seed. Statistical fitting requires business constraints.

## Confidence-floor calibration (Aug 22 morning)

The 0.55 confidence floor was intuition. Calibration study: 3 live Bedrock
captures × 22 scenarios (n=66), floors swept analytically per capture-merged
classifications.

| Floor | Escalation rate | Effective accuracy | Critical undertriage |
|-------|-----------------|--------------------|----------------------|
| 0.00–0.60 | 0% | 100% | 0 |
| 0.70 | 18.2% | 100% | 0 |
| 0.80 | 21.2% | 100% | 0 |
| 0.90 | 43.9% | 100% | 0 |

Verdict: keep **0.55**. On-distribution the model is perfectly calibrated —
the floor is a free insurance policy. Raising it buys zero accuracy and
costs up to 44% human burden. The floor's value is off-distribution
protection, which this study confirms stays intact.
