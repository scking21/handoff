"""Runtime configuration, environment-driven."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    # "bedrock" | "scripted" | "heuristic" — bedrock requires AWS credentials
    # + model access; heuristic keeps local dev/tests credential-free.
    model_provider: str = field(default_factory=lambda: os.getenv("HANDOFF_MODEL_PROVIDER", "heuristic"))
    # Project region (new AWS experience): all regional resources MUST live here.
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-2"))
    bedrock_model_id: str = field(
        default_factory=lambda: os.getenv("HANDOFF_BEDROCK_MODEL_ID", "us.amazon.nova-lite-v1:0")
    )
    # Triage is classification: deterministic decoding is both faster and
    # reproducible. Creativity has no value here.
    bedrock_temperature: float = field(default_factory=lambda: float(os.getenv("HANDOFF_BEDROCK_TEMPERATURE", "0")))
    approval_threshold: int = field(default_factory=lambda: int(os.getenv("HANDOFF_APPROVAL_THRESHOLD", "400")))
    data_dir: str = field(default_factory=lambda: os.getenv("HANDOFF_DATA_DIR", "data/runtime"))
    store_backend: str = field(default_factory=lambda: os.getenv("HANDOFF_STORE", "file"))  # file|dynamodb
    dynamodb_table: str = field(default_factory=lambda: os.getenv("HANDOFF_DDB_TABLE", "handoff"))
    sms_channel: str = field(default_factory=lambda: os.getenv("HANDOFF_SMS_CHANNEL", "console"))


def in_agentcore_container() -> bool:
    """True inside a Bedrock AgentCore runtime instance."""
    import os

    return os.path.exists("/.dockerenv") or os.path.isdir("/opt/aws/agentcore-runtime")


settings = Settings()
