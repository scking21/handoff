"""Deploy the CoordinatorAgent to Amazon Bedrock AgentCore Runtime.

Prereqs: AWS credentials with AgentCore/Bedrock permissions, and
`pip install bedrock-agentcore-starter-toolkit`.

Official recipe (Resources page):
https://aws.github.io/bedrock-agentcore-starter-toolkit/user-guide/runtime/quickstart.html

Usage: .venv/bin/python -m handoff.deploy.agentcore [--launch]
"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch", action="store_true", help="actually build+deploy; default prints plan")
    args = parser.parse_args()

    from handoff.config import settings

    steps = [
        "agentcore configure -e handler: handoff.deploy.agentcore_app.app  (entrypoint exposing FastAPI)",
        f"agentcore launch   (builds container, creates runtime in {settings.aws_region})",
        "agentcore invoke   (smoke test invocation)",
        "EventBridge Scheduler rule -> invoke runtime every 5 min (sweep heartbeat)",
        "Point dashboard AGENTCORE_ARN at runtime for live demo link",
    ]
    print("AgentCore deploy plan:")
    for s in steps:
        print(f"  - {s}")
    if not args.launch:
        print("\n(dry run — pass --launch after AWS credentials are configured)")
        return

    from bedrock_agentcore_starter_toolkit import BedrockAgentCoreApp  # noqa: F401

    raise SystemExit(
        "Live deploy wired once AWS credentials exist. See deploy/README for the "
        "exact command sequence; keep this module as the entrypoint map."
    )


if __name__ == "__main__":
    main()
