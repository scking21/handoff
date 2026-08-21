# Official hackathon resources — curated

From https://agentsforhumans.devpost.com/resources (accessed Aug 21, 2026).
Only what's relevant to Handoff, with why it matters.

## Setup & required tools

| Item | Link | Status / why |
|------|------|--------------|
| AWS account | https://signin.aws.amazon.com/signup?request_type=register | ⏳ pending — blocks Bedrock wiring + AgentCore deploy |
| Strands SDK quickstart | https://strandsagents.com/docs/user-guide/quickstart/overview/ | ✅ installed (Python) |
| Strands examples | https://strandsagents.com/docs/examples/ | mine for patterns judges will recognize |
| **$50 AWS credits** | https://forms.gle/Ssr8zLw4afKg114M7 | ⚠️ Corby submitted — verify this is the form used; deadline **Sep 11, 12pm PT** |

> ⚠️ **Discrepancy:** the Rules page lists `https://forms.gle/6sjzKiX6bKUMA5NEA` for
> credits; the Resources page lists `https://forms.gle/Ssr8zLw4afKg114M7`. If the
> submitted form doesn't match one of these, re-submit via the Resources link before
> Sep 11. Credits expire Oct 31 — fine for our timeline.

## Learning resources (official)

- [Getting Started with Strands Agents: Step-by-Step Guide](https://builder.aws.com/content/2xCUnoqntk2PnWDwyb9JJvMjxKA/getting-started-with-strands-agents-a-step-by-step-guide) — baseline vocabulary; also a model for our own builder.aws.com posts' tone.
- [Strands Agents SDK: Technical Deep Dive](https://aws.amazon.com/blogs/machine-learning/strands-agents-sdk-a-technical-deep-dive-into-agent-architectures-and-observability/) — architecture patterns + observability framing; align our README language with theirs so judges see fluency.
- [Introducing Strands Agents](https://aws.amazon.com/blogs/opensource/introducing-strands-agents-an-open-source-ai-agents-sdk/) — origin story; citable in blog post 1.
- [Strands video playlist](https://www.youtube.com/watch?v=ZpXWGjISMs8&list=PLDzwjhH-4yhU%5C) — 14 videos; skim for feature demos we should mirror.

## AgentCore (deploy path)

- [AgentCore documentation](https://docs.aws.amazon.com/bedrock-agentcore/)
- [AgentCore CLI quickstart](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-get-started-cli.html)
- [Deploy a Strands Agent to AgentCore Runtime](https://aws.github.io/bedrock-agentcore-starter-toolkit/user-guide/runtime/quickstart.html) ← **the exact recipe for our live-demo deploy** (`bedrock-agentcore-starter-toolkit`; our `src/handoff/deploy/agentcore.py` maps to this).

## Track description notes (Professional Agents)

Official framing worth mirroring in submission copy:
- "Every profession has work that only a person can judge and a pile of repetitive
  tasks around it that shouldn't need one."
- "A great Pro Agent clears the runway by drafting, checking, organizing, and
  following up so the expert can spend their time on the part that needs them."
- Cross-track emphasis: agents that "work in the background, make the safe calls on
  their own and surface only when a human actually needs to weigh in."

Handoff's pitch already matches all three — keep this language echoed (not copied)
in the Devpost description and video script.
