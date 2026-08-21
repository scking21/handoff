# Stream B — Tooling Research: verdicts + effort estimates

Access dates: all sources fetched and read **2026-08-21** by two independent
research passes (the first pass's full source list survived in its session
transcript and was re-verified by a second pass; deliverable assembled by Agent 2).
Scope: keep Strands as the agent SDK (hackathon requirement); solo-dev estimates;
~3 weeks of runway remain. Adopt/drop table at the bottom.

---

## 1. Amazon Bedrock AgentCore — REAL, and the single biggest Technical-Implementation lever

Every pillar has live AWS documentation today (no vaporware risk detected):

| Pillar | Status | Evidence |
|---|---|---|
| **Runtime** | Real, CLI-first | [Get started with AgentCore Runtime](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-getting-started.html), [AgentCore CLI tutorial](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html). CLI lives at github.com/aws/agentcore-cli. |
| **Gateway (MCP tool hosting)** | Real | [MCP servers as targets](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-target-MCPservers.html): DYNAMIC-mode capability discovery, Gateway forwards to upstream MCP servers. Our `HandoffTools` could be hosted here later; not required for submission. |
| **Identity** | Real, cheap | [Credential/resource providers](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/resource-providers.html) act as intermediaries for API keys and workload identity. Third-party pricing notes ~$0.010 per 1k non-AWS token/API-key requests, no extra charge when used through Runtime/Gateway ([aiarch.dev overview](https://aiarch.dev/amazon-bedrock-agentcore)). |
| **Memory** | Real, Strands-integrated | Starter-toolkit memory quickstart on GitHub ([aws/bedrock-agentcore-starter-toolkit](https://github.com/aws/bedrock-agentcore-starter-toolkit/blob/main/documentation/docs/user-guide/memory/quickstart.md)). Optional stretch, not core. |
| **Observability** | Real, OTel-based | [Get started with AgentCore Observability](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-get-started.html): OpenTelemetry ingestion (non-runtime agents add the OTel library). Aligns 1:1 with our Stream E OTel flag — one wiring serves both. |

Pricing model is pay-for-active-consumption, not pre-allocated hosting
([official pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)) — fits
inside the $50 credits Corby secured.

⚠️ **Drift found:** the Devpost resources page links
`aws.github.io/bedrock-agentcore-starter-toolkit/user-guide/runtime/quickstart.html`,
which now **redirects** to the AWS-docs URL above. Use the AWS-docs links; the
GitHub-pages toolkit docs are legacy.

**Effort:** Runtime deploy of our Strands coordinator ≈ **0.5–1 day** (`src/handoff/deploy/agentcore.py` is already scaffolded). Gateway exposure of existing tools ≈ 1–2 days extra — skip unless time is abundant.

## 2. Step Functions durable orchestration (task-token approval gates)

The aws-samples repo exists and does exactly what we'd want demonstrated:
[`sample-durable-multi-agent-step-functions-agentcore`](https://github.com/aws-samples/sample-durable-multi-agent-step-functions-agentcore)
("Product Discovery Assistant": Step Functions + AgentCore Runtime + Strands).
The generic pattern is the documented
[`waitForTaskToken` human-approval callback](https://oneuptime.com/blog/post/2026-02-12-build-human-approval-workflows-with-step-functions/view).

**Verdict: WATCH, don't build this cycle.** Handoff *already* implements durable
gates in-process — the gate persists the exact intended dispatch before pausing,
and any store backend (FileStore today, DynamoDBStore in review) resumes it. An
SFN port would duplicate that guarantee across process boundaries at an estimated
**3–5 solo-days** including IAM/state-machine debugging, for a property judges
can't inspect in a 5-minute video. Position it in the Devpost write-up as the
production scaling path; cite the sample repo.

## 3. Guardrails & PII — cheapest credible hardening win

- Official: [sensitive-information (PII) filters](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-sensitive-filters.html) in Amazon Bedrock Guardrails.
- Strands documents its Guardrails integration: [strandsagents.com safety-security/guardrails](https://strandsagents.com/docs/user-guide/safety-security/guardrails/).
- Pricing: charged per filter configured, same for standard/classic tiers ([Bedrock pricing](https://aws.amazon.com/bedrock/pricing/)) — pennies at demo scale.
- Production rollout reference: [cipherprojects.com 2026 guide](https://cipherprojects.com/blog/posts/bedrock-guardrails-production-guide-2026).

**Verdict: ADOPT.** Configure one Guardrail with PII entities (address, phone,
email) + content filters, and apply it to tenant text **at intake**, before it
reaches the LLM brief or the vendor job card. This directly mitigates redteam
finding **F2** (unfenced tenant text flowing into prompt + job card) and gives
judges a concrete "we handle tenant PII" answer. Offline development path: stub
the guardrail call behind the same provider flag used for heuristic/bedrock.
**Effort: 0.5–1 day.**

## 4. Model choice — Claude Sonnet for the agent loop, Nova as the cheap lane

- Price (us-east-1, per M tokens): Claude Sonnet 4.5 **$3 in / $15 out** vs Nova Pro **$0.8 / $3.2** ([comparison](https://aws-bedrock-explorer.com/compare/claude-sonnet-4-5-20250929-v1-0-vs-nova-pro-v1-0)).
- Structured-output reliability: AWS's own guidance for Nova structured outputs exists ([AWS ML blog](https://aws.amazon.com/blogs/machine-learning/structured-outputs-with-amazon-nova-a-guide-for-builders/)), but independent agentic testing favors Claude on JSON-parse/required-field consistency at volume ([builder.aws.com: 6 models × 1000 documents](https://builder.aws.com/content/3DaJtoXYG3IXRYvEo7WLY2gp2WI/i-tested-6-ai-models-on-1000-documents-the-results-surprised-everyone-including-me)).

**Recommendation: Claude Sonnet** for triage/coordinator — our whole pitch is
deterministic enforcement around probabilistic decisions, so malformed tool calls
are the failure mode we care about most, and ~4× token cost is irrelevant at
hackathon scale inside $50 credits. **Nova Pro** is the documented fallback lane
for high-volume cheap paths (e.g., draft-message generation) if we ever need one.
Keep both behind `HANDOFF_MODEL_PROVIDER`.

## 5. Comms channel realism — SMS sandbox wins, email via credits

- ⚠️ **SES free tier is dead for us:** accounts created after Jul 15 2025 get **no permanent free tier** — they burn promo credits then pay standard rates ([cost breakdown](https://costgoat.com/pricing/amazon-ses); corroborated by [emercury.net](https://www.emercury.net/blog/email-marketing-tips/amazon-ses-pricing), which still advertises the legacy tier to older accounts).
- **SNS SMS sandbox:** no stated expiry; sends restricted to **verified destination numbers** ([AWS re:Post](https://repost.aws/questions/QUnvQUnBOyR42GVqfSKQ1C1A/how-long-can-you-continue-to-use-sms-sandbox-for-sns)) — verify Corby's phone + 2–3 teammates and every demo text is real, $0, and leak-proof (no secrets beyond the AWS creds we already hold).

**Verdict: ADOPT SNS-sandbox SMS** behind the `channels/sms.py` interface Stream E
is building right now (console/file backends offline, SNS drops in when creds
land). Email demo path: SES paid from remaining credits if needed; otherwise
Resend's free tier stays the off-AWS backup. No secrets in the repo — channel
config reads env vars only.

---

## Adopt / watch / drop

| Decision | Item | Why | Effort |
|---|---|---|---|
| **ADOPT** | AgentCore Runtime deploy of coordinator | Biggest Technical-Implementation score; docs+CLI mature; scaffold exists | 0.5–1 d |
| **ADOPT** | AgentCore Observability (OTel) | Same wiring as Stream E flag; judge-visible traces | 0.5 d |
| **ADOPT** | Bedrock Guardrails PII filter at intake | Mitigates redteam F2; cheap; Strands-documented | 0.5–1 d |
| **ADOPT** | SNS SMS sandbox demo path | Real SMS, $0, verified-numbers-only | 0.5 d once channels/ lands |
| **ADOPT** | Claude Sonnet as primary model | Structured-output reliability > 4× cost at this scale | config change |
| **WATCH** | AgentCore Memory | Real but optional; adds demo surface late | 1–2 d |
| **WATCH** | SFN task-token gates (aws-samples sample) | Duplicates our in-repo durable gates; cite as roadmap | 3–5 d |
| **DROP** | SES free-tier assumption | Dead for post-Jul-2025 accounts | — |
