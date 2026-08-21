# Devpost Resources Digest — Agents for Humans Hackathon

Source: https://agentsforhumans.devpost.com/resources (fetched 2026-08-21)
Cross-referenced against `AGENT-TASKS.md`. Items marked ★ are action items.

## Hard deadlines

| What | When | Notes |
|------|------|-------|
| ✅ **AWS credits request — APPLIED (Corby, 2026-08-21)** | Sep 11, 2026, 12:00pm PT | Deadline was NOT in AGENT-TASKS.md — 3 days before the hackathon deadline. Form: https://forms.gle/Ssr8zLw4afKg114M7 — $50 AWS promotional credits for registered participants, while supplies last. Subject to https://aws.amazon.com/awscredits/ terms. |
| Submission deadline | Sep 14, 2026, 5:00pm PDT | Matches AGENT-TASKS.md. |
| AWS account signup | ASAP | AGENT-TASKS notes AWS credentials don't exist yet; everything runs offline via the heuristic provider until they land. Credits request requires a registered participant account. |

## Setup & required tools

1. **AWS account** — free signup: https://signin.aws.amazon.com/signup?request_type=register
2. **Strands Agents SDK** (required) — Python + TypeScript, "working agent in under 20 min."
   - Quickstart: https://strandsagents.com/docs/user-guide/quickstart/overview/
   - Examples: https://strandsagents.com/docs/examples/
   - Handoff already uses Strands (Python) — requirement satisfied; keep it as the agent SDK per ground rules.
3. **★ AWS credits** — see deadline table. Do this first; it gates all Bedrock/AgentCore work.

## Learning resources (mapped to AGENT-TASKS streams)

| Resource | URL | Use it for |
|----------|-----|-----------|
| Getting Started with Strands (builder.aws.com) | https://builder.aws.com/content/2xCUnoqntk2PnWDwyb9JJvMjxKA/getting-started-with-strands-agents-a-step-by-step-guide | Baseline reference. Note: builder.aws.com posts earn up to **+0.6 bonus** on the rubric — publishing there is double-dipping. |
| Strands SDK Technical Deep Dive (AWS ML blog) | https://aws.amazon.com/blogs/machine-learning/strands-agents-sdk-a-technical-deep-dive-into-agent-architectures-and-observability/ | **Stream E #2** (OTel tracing wiring) — covers observability patterns. |
| Introducing Strands (AWS OSS blog) | https://aws.amazon.com/blogs/opensource/introducing-strands-agents-an-open-source-ai-agents-sdk/ | Background / video-script talking points (Stream D). |
| Strands YouTube playlist (14 videos) | https://youtube.com/watch?v=ZpXWGjISMs8&list=PLDzwjhH-4yhU\ | Demo material study + quick API orientation. |
| Bedrock AgentCore docs | https://docs.aws.amazon.com/bedrock-agentcore/ | **Stream B #1** — Gateway/Identity/Memory/Observability reality check. |
| AgentCore CLI quickstart | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-get-started-cli.html | **Stream B #1** + Technical Implementation score (live deploy). |
| Deploy Strands → AgentCore Runtime | https://aws.github.io/bedrock-agentcore-starter-toolkit/user-guide/runtime/quickstart.html | The exact deploy path for Handoff's Strands agent — shortest route to a live AgentCore demo. |

## Track fit (from the Inspiration section)

Handoff = maintenance coordination for property managers → **Professional Agents** track (already assumed in AGENT-TASKS.md — confirmed correct).

Track language worth echoing in the Devpost description and video (Stream D):

> "A great Pro Agent clears the runway by drafting, checking, organizing, and
> following up so the expert can spend their time on the part that needs them."

Handoff's loop (triage → policy gate → dispatch with job cards → schedule →
verify closeout → invoice match → nightly sweep) is a literal implementation of
"drafting, checking, organizing, and following up." The Everyday-Agents line
"work in the background, make the safe calls on their own and surface only when
a human actually needs to weigh in" also describes Handoff's approval-gate
design — usable framing even from the Pro track.

## Ordered action items

1. ~~Request AWS credits before Sep 11, 12:00pm PT~~ — ✅ APPLIED 2026-08-21; watch for the credits landing in the AWS account, then wire credentials behind `HANDOFF_MODEL_PROVIDER=bedrock`.
2. Create AWS account → wire real credentials behind `HANDOFF_MODEL_PROVIDER=bedrock`.
3. Follow the Strands→AgentCore Runtime quickstart to get a live deploy for the demo.
4. Feed the observability deep dive into Stream E #2 (OTel flag).
5. Queue a builder.aws.com post (rubric bonus +0.6) once the AgentCore deploy story exists.
