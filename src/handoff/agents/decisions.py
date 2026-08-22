"""Decision providers: the judgment layer that feeds the deterministic engine.

``LLMTriageProvider`` runs a Strands Agent with Bedrock and structured output.
``HeuristicTriageProvider`` is the offline fallback used in tests and demos
without credentials — same interface, deterministic rules distilled from
industry emergency definitions (active water, gas, spark, lockout = emergency).
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from handoff.domain.models import Trade, Urgency
from handoff.workflow.engine import TriageDecision

EMERGENCY_HINTS = [
    "pouring", "flooding", "burst", "water everywhere", "ceiling", "gas smell",
    "smell gas", "sparked", "spark", "smoke", "locked out", "locked myself out",
    "standing outside", "sewage", "no water",
]
URGENT_HINTS = [
    "no heat", "freezing", "hasn't worked since yesterday", "no hot water",
    "doesn't work at all", "outlet", "broken window", "leaking",
]
# (trade, [(hint, weight)]) — specific fixtures outrank generic symptoms
CATEGORY_HINTS: list[tuple[Trade, list[tuple[str, int]]]] = [
    (Trade.APPLIANCE, [("dishwasher", 3), ("fridge", 3), ("refrigerator", 3), ("oven", 3),
                        ("garbage disposal", 3), ("washer", 2), ("dryer", 2)]),
    (Trade.LOCKSMITH, [("locked out", 3), ("locked myself out", 3), ("key broke", 3), ("door won't open", 2)]),
    (Trade.ELECTRICAL, [("outlet", 2), ("spark", 2), ("power", 1), ("light fixture", 1),
                         ("breaker", 2), ("wiring", 2)]),
    (Trade.HVAC, [("heat", 2), ("heater", 2), ("ac ", 2), ("air conditioning", 2),
                   ("thermostat", 2), ("furnace", 2), ("rattle", 1)]),
    (Trade.PLUMBING, [("pouring", 3), ("ceiling", 2), ("water", 1), ("leak", 1),
                       ("faucet", 1), ("pipe", 1), ("drain", 1), ("toilet", 1), ("gas", 1)]),
    (Trade.GENERAL, []),
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
            n = sum(w for h, w in hints if h in text)
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
        "You are the triage brain for a property-management maintenance coordinator. Classify each tenant maintenance report.\nURGENCY \u00e2\u0080\u0094 emergency: active water intrusion (pouring/flooding/ceiling water), gas odor, electrical sparking/burning/smoke from fixtures or switches, ANY burning smell from heating/cooling equipment (even if it still runs and even if it is brief or recurring \u00e2\u0080\u0094 this is not normal dust burn-off when reported by a tenant), smoke or carbon-monoxide detector activation, whole-unit power loss, lockout, sewage backup, anything immediately habitability-threatening. urgent: primary systems down (heat in cold weather, no hot water anywhere in the unit), safety-adjacent hazards (dead outlet WITHOUT sparking, broken exterior door/window, broken glass on premises, loose/failing door locks), active slow leaks (growing ceiling stains, drain backups crossing fixtures). routine: cosmetic issues, pests, single-fixture annoyances that cause no damage or hazard.\nCATEGORY \u00e2\u0080\u0094 one of plumbing, hvac, electrical, appliance, general, locksmith. Appliance fixtures (dishwasher, fridge, oven, washer) are appliance, NOT plumbing, even when they leak. Lockouts AND failing door locks are locksmith. Detector/safety-device issues with no single trade are general.\nCONFIDENCE \u00e2\u0080\u0094 0..1; below 0.55 the ticket goes to a human instead of you, so be honest when the description is too vague to judge severity.\nExamples:\n- 'Water pouring through the kitchen ceiling light fixture' -> emergency/plumbing\n- 'I smell gas near the stove' -> emergency/plumbing\n- 'Outlet sparked when I plugged in my hairdryer' -> emergency/electrical\n- 'Locked myself out, standing outside' -> emergency/locksmith\n- 'Smoke coming out of my bedroom light switch' -> emergency/electrical\n- 'Carbon monoxide detector keeps beeping' -> emergency/general\n- 'Whole apartment lost power after the storm' -> emergency/electrical\n- 'Heater works but there is a burning smell at startup' -> emergency/hvac\n- 'Clothes dryer smells like burning when it runs' -> emergency/appliance\n- 'Brown ceiling stain getting bigger over the week' -> urgent/plumbing\n- 'Dirty water backs into the kitchen sink when the washer drains' -> urgent/plumbing\n- 'Shower only runs cold, other taps get hot water' -> urgent/plumbing\n- 'Front door lock is loose and does not always latch' -> urgent/locksmith\n- 'Broken glass shelf shattered into the hallway carpet' -> urgent/general\n- 'Fridge stopped cooling but interior light works' -> urgent/appliance\n- 'AC making a weird rattle sometimes' -> routine/hvac\n- 'Dishwasher leaks onto the floor when it runs' -> routine/appliance\n- 'The washing machine is flooding the laundry closet' -> emergency/appliance\n- 'Toilet keeps running unless you jiggle the handle' -> routine/plumbing\n- 'Wasp nest forming above the front door' -> routine/general\nRespond with the structured classification only."
    )

    def __init__(self, model=None):
        from strands import Agent

        # callback_handler=None silences the default tool-call printer —
        # required for programmatic (--json) eval output.
        self.agent = Agent(model=model, system_prompt=self.SYSTEM_PROMPT, callback_handler=None)

    def classify(self, raw_request: str, photo_descriptions: list[str]) -> TriageDecision:
        prompt = raw_request
        if photo_descriptions:
            prompt += "\nPhotos attached showing: " + "; ".join(photo_descriptions)
        result = self.agent.structured_output(TriageDecision, prompt)
        return result


class SafetyEnsembleProvider:
    """LLM judgment + deterministic hazard-keyword escalation.

    The model handles nuance; a fixed keyword net guarantees that reports
    matching catastrophic-hazard patterns are never undertriaged, regardless
    of sampling noise. Defense in depth at the decision layer."""

    HAZARD_KEYWORDS = [
        "burning smell", "smoke", "gas smell", "smell gas", "carbon monoxide",
        "sparked", "sparking", "pouring", "flooding", "sewage",
    ]
    # Narrow guard for detector-device phrases: when the device noun phrase is
    # present, the "smoke" keyword is device talk, not fire evidence — REGARDLESS
    # of whether a malfunction keyword appears (wave-3 finding: synonyms like
    # "making noise"/"blinking red" slipped past a malfunction-word requirement,
    # re-exposing the seam). Real fire always carries an activation cue
    # (went off / blaring / smell/see smoke / fire), which still escalates.
    # CO detectors are deliberately NOT guarded (odorless/invisible hazard;
    # any CO-detector phrase still escalates unconditionally).
    _SMOKE_DETECTOR_RE = re.compile(r"smoke detectors?", re.IGNORECASE)
    _DETECTOR_ACTIVATION_RE = re.compile(
        r"went off|going off|won't stop|blaring|sounding|smell\w* smoke|see smoke|"
        r"smoke everywhere|visible smoke|smoke (coming|rising|drifting|pouring|billowing)|"
        r"smoke (in|from|filling)\b|\bfire\b")

    def __init__(self, inner: TriageProvider):
        self.inner = inner

    def classify(self, raw_request: str, photo_descriptions: list[str]) -> TriageDecision:
        text = (raw_request + " " + " ".join(photo_descriptions)).lower()
        chatter = self._smoke_detector_chatter(text)
        # The mask exists to stop DETERMINISTIC keyword scanners from seeing
        # "smoke" inside the device noun phrase. It must cover the PHOTO text
        # too: a device named only in a photo description is still device
        # maintenance talk, not fire evidence. (Wave-3 finding: pre-fix, a
        # photo-only mention force-escalated emergency through the heuristic
        # inner's bare-"smoke" hint.)
        mask = lambda t: self._SMOKE_DETECTOR_RE.sub("detector", t) if chatter else t
        # The inner provider gets the mask ONLY when it is itself a keyword
        # scanner (HeuristicTriageProvider has bare "smoke" in its hints). An
        # LLM inner keeps FULL context — masking "smoke detector" to bare
        # "detector" makes the device type ambiguous (could read as CO) and
        # degrades its judgment.
        if isinstance(self.inner, HeuristicTriageProvider):
            d = self.inner.classify(mask(raw_request), [mask(p) for p in photo_descriptions])
            scan_text = mask(text)
        else:
            d = self.inner.classify(raw_request, photo_descriptions)
            scan_text = mask(text)
        hit = next((k for k in self.HAZARD_KEYWORDS if k in scan_text), None)
        if hit and d.urgency != Urgency.EMERGENCY:
            return TriageDecision(
                urgency=Urgency.EMERGENCY,
                category=d.category,
                confidence=max(d.confidence, 0.9),
                rationale=f"{d.rationale} | escalated: safety keyword '{hit}'",
            )
        return d

    def _smoke_detector_chatter(self, text: str) -> bool:
        """True when the ONLY 'smoke' evidence is the device noun phrase and no
        activation cue is present. Dropping the malfunction-word requirement
        (wave-3): synonyms like 'making noise'/'blinking red' describe the
        device without a canonical trouble keyword; a device simply named with
        no activation signal is maintenance talk, not fire. Anything ambiguous
        (any activation/real-smoke cue) keeps full escalation."""
        if not self._SMOKE_DETECTOR_RE.search(text):
            return False
        if self._DETECTOR_ACTIVATION_RE.search(text):
            return False
        return True


def get_triage_provider(provider_name: str) -> TriageProvider:
    if provider_name == "bedrock":
        from strands.models import BedrockModel

        from handoff.config import settings


        model = BedrockModel(
            model_id=settings.bedrock_model_id,
            region_name=settings.aws_region,
            temperature=settings.bedrock_temperature,
        )
        return SafetyEnsembleProvider(LLMTriageProvider(model=model))
    return HeuristicTriageProvider()


def build_bedrock_model():
    """Single source of truth for the deployed triage model config."""
    from strands.models import BedrockModel

    from handoff.config import settings

    return BedrockModel(
        model_id=settings.bedrock_model_id,
        region_name=settings.aws_region,
        temperature=settings.bedrock_temperature,
    )


def decision_to_json(d: TriageDecision) -> str:
    return json.dumps({"urgency": d.urgency.value, "category": d.category.value, "confidence": d.confidence})
