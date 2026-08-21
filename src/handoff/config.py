"""Runtime configuration, environment-driven."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    # "bedrock" | "heuristic" — bedrock requires AWS credentials + model access
    model_provider: str = field(default_factory=lambda: os.getenv("HANDOFF_MODEL_PROVIDER", "heuristic"))
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "us-west-2"))
    bedrock_model_id: str = field(
        default_factory=lambda: os.getenv("HANDOFF_BEDROCK_MODEL_ID", "us.amazon.nova-lite-v1:0")
    )
    approval_threshold: int = field(default_factory=lambda: int(os.getenv("HANDOFF_APPROVAL_THRESHOLD", "400")))
    data_dir: str = field(default_factory=lambda: os.getenv("HANDOFF_DATA_DIR", "data/runtime"))


settings = Settings()
