"""Decision providers: the judgment layer that feeds the deterministic engine.

``LLMTriageProvider`` runs a Strands Agent with Bedrock and structured output.
``HeuristicTriageProvider`` is the offline fallback used in tests and demos
without credentials — same interface, deterministic rules distilled from
industry emergency definitions (active water, gas, spark, lockout = emergency).
"""

from __future__ import annotations

import json
from typing import Protocol

from handoff.domain.models import Trade, Urgency
from handoff.workflow.engine import TriageDecision

EMERGENCY_HINTS = [
    "pouring", "flooding", "burst", "water everywhere", "ceiling", "gas smell",
    "smell gas", "sparked", "spark", "smoke", "locked out", "sewage", "no water",
]
URGENT_HINTS = [
    "no heat", "freezing", "hasn't worked since yesterday", "no hot water",
    "doesn't work at all", "outlet", "broken window", "leaking",
]
CATEGORY_HINTS: list[tuple[Trade, list[str]]] = [
    (Trade.PLUMBING, ["water", "leak", "faucet", "pipe", "drain", "toilet", "gas"]),
    (Trade.HVAC, ["heat", "heater", "ac ", "air conditioning", "thermostat", "furnace", "rattle"]),
    (Trade.ELECTRICAL, ["outlet", "spark", "power", "light fixture", "breaker", "wiring"]),
    (Trade.APPLIANCE, ["dishwasher", "fridge", "refrigerator", "oven", "washer", "dryer", "garbage disposal"]),
    (Trade.LOCKSMITH, ["locked out", "lock", "key broke", "door won't open"]),
]


class TriageProvider(Protocol):
    def classify(self, raw_request: str, photo_descriptions: list[str]) -> TriageDecision: ...


class HeuristicTriageProvider:
    """Deterministic rules. Confidence reflects evidence strength."""

    def classify(self, raw_request: str, photo_descriptions: list[str]) -> TriageDecision:
        text = (raw_request + " " + " ".join(photo_descriptions)).lower()
        em_hits = [h for h in EMERGENCY_HINTS if h in text]
        ur_hits = [h for h in URGENT_HINTS if h in text]

        category, cat_hits = Trade.GENERAL, 0
        for trade, hints in CATEGORY_HINTS:
            n = sum(1 for h in hints if h in text)
            if n > cat_hits:
                category, cat_hits = trade, n

        if em_hits:
            urgency = Urgency.EMERGENCY
            confidence = min(0.95, 0.7 + 0.1 * len(em_hits))
        elif ur_hits:
            urgency = Urgency.URGENT
            confidence = min(0.85, 0.6 + 0.08 * len(ur_hits))
        else:
            urgency = Urgency.ROUTINE
            confidence = 0.6 if cat_hits else 0.3

        rationale = f"emergency-hints={em_hits or 'none'} urgent-hints={ur_hits or 'none'} category={category.value}({cat_hits})"
        return TriageDecision(urgency=urgency, category=category, confidence=round(confidence, 2), rationale=rationale)


class LLMTriageProvider:
    """Strands Agent + Bedrock structured output. Swaps in when AWS creds exist."""

    SYSTEM_PROMPT = (
        "You are the triage brain for a property-management maintenance coordinator. "
        "Classify each tenant maintenance report.\n"
        "URGENCY — emergency: active water intrusion, gas odor, electrical sparking/burning, "
        "lockout, sewage backup, anything immediately habitability-threatening. "
        "urgent: primary systems down (heat in cold weather, no hot water), safety-adjacent "
        "(dead outlet, broken exterior door/window). routine: everything else.\n"
        "CATEGORY — one of plumbing, hvac, electrical, appliance, general, locksmith.\n"
        "CONFIDENCE — 0..1; below 0.55 the ticket goes to a human instead of you, so be honest "
        "when the description is too vague to judge severity.\n"
        "Respond with the structured classification only."
    )

    def __init__(self, model=None):
        from strands import Agent

        self.agent = Agent(model=model, system_prompt=self.SYSTEM_PROMPT)

    def classify(self, raw_request: str, photo_descriptions: list[str]) -> TriageDecision:
        prompt = raw_request
        if photo_descriptions:
            prompt += "\nPhotos attached showing: " + "; ".join(photo_descriptions)
        result = self.agent.structured_output(TriageDecision, prompt)
        return result


def get_triage_provider(provider_name: str) -> TriageProvider:
    if provider_name == "bedrock":
        from handoff.config import settings
        from strands.models import BedrockModel

        model = BedrockModel(model_id=settings.bedrock_model_id, region_name=settings.aws_region)
        return LLMTriageProvider(model=model)
    return HeuristicTriageProvider()


def decision_to_json(d: TriageDecision) -> str:
    return json.dumps({"urgency": d.urgency.value, "category": d.category.value, "confidence": d.confidence})
