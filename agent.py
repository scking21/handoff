"""AgentCore Runtime launcher (thin wrapper).

Bootstraps the src/ layout so the container build needs no editable install,
then exposes the BedrockAgentCoreApp instance the platform expects.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent / "src"))

from handoff.deploy.runtime import agent_app  # noqa: E402,F401

# Platform harnesses look for the conventional name
app = agent_app

if __name__ == "__main__":
    app.run()
