"""Wave-3: multimodal, understatement, multi-issue, time-scale phrasing.

Labels derived from SYSTEM_PROMPT rules (cited per-case). Photo descriptions
flow through the same 'Photos attached showing:' seam the dashboard uses.
"""

from __future__ import annotations

from handoff.domain.models import Trade, Urgency

NIGHT_SCENARIOS_3: list[dict] = [
    {
        "key": "photo_ceiling_bulge",
        "raw": "Can someone look at our bedroom ceiling? There's a weird bump "
               "that wasn't there last week.",
        "photos": ["large sagging bulge in ceiling, brown ring, drywall visibly straining"],
        "expect_urgency": Urgency.URGENT,
        "expect_category": Trade.PLUMBING,
        "rationale": "understated text; photo shows active slow leak (growing-stain rule) = urgent/plumbing",
    },
    {
        "key": "photo_scorch_closeup",
        "raw": "This outlet looks a little discolored, should I be worried? "
               "Everything still works.",
        "photos": ["close-up of outlet plate with black scorch marks and melting plastic"],
        "expect_urgency": Urgency.EMERGENCY,
        "expect_category": Trade.ELECTRICAL,
        "rationale": "understated text; photo shows electrical burning evidence = emergency (no net keyword)",
    },
    {
        "key": "photo_water_at_furnace",
        "raw": "There's some water on the floor near the furnace, might be "
               "nothing but thought I'd mention it.",
        "photos": ["pool of water spreading from base of furnace unit"],
        "expect_urgency": Urgency.EMERGENCY,
        "expect_category": Trade.HVAC,
        "rationale": "'might be nothing' + photo of spreading pool at HVAC equipment: "
                     "burning-smell rule covers HVAC hazards; active water at furnace = emergency/hvac",
    },
    {
        "key": "photo_cracked_glass_door",
        "raw": "The glass on our patio door has a crack in it, been like that "
               "a few days.",
        "photos": ["floor-to-ceiling patio door glass with long diagonal crack, glass separating"],
        "expect_urgency": Urgency.URGENT,
        "expect_category": Trade.GENERAL,
        "rationale": "broken exterior glass door = urgent (safety-adjacent clause)",
    },
    {
        "key": "multi_gas_and_power",
        "raw": "We smell gas faintly near the kitchen AND half the outlets "
               "stopped working after the lightning storm last night.",
        "photos": [],
        "expect_urgency": Urgency.EMERGENCY,
        "expect_category": Trade.PLUMBING,
        "rationale": "gas odor = emergency (net assists); gas outranks electrical for category",
    },
    {
        "key": "multi_leak_plus_lock",
        "raw": "Our sink has been leaking under the cabinet for a week and "
               "also the front door lock stopped latching, can both be fixed?",
        "photos": [],
        "expect_urgency": Urgency.URGENT,
        "expect_category": Trade.PLUMBING,
        "rationale": "slow leak (urgent) + failing lock (urgent); leak = active damage -> plumbing primary",
    },
    {
        "key": "timescale_week_old_spill",
        "raw": "Some water spilled under the bathroom sink last week, I dried "
               "it up and there's just a small stain now, no smell.",
        "photos": [],
        "expect_urgency": Urgency.ROUTINE,
        "expect_category": Trade.PLUMBING,
        "rationale": "resolved incident, no active leak = cosmetic = routine",
    },
    {
        "key": "timescale_months_drip",
        "raw": "Our shower faucet has dripped forever, like since we moved in "
               "eight months ago. Annoying at night but whatever.",
        "photos": [],
        "expect_urgency": Urgency.ROUTINE,
        "expect_category": Trade.PLUMBING,
        "rationale": "long-standing single-fixture annoyance = routine",
    },
    {
        "key": "photo_detector_on_ceiling",
        "raw": "This thing on our ceiling keeps making noise, what even is it?",
        "photos": ["round ceiling-mounted smoke detector with red blinking light"],
        "expect_urgency": Urgency.URGENT,
        "expect_category": Trade.GENERAL,
        "rationale": "photo identifies smoke DETECTOR + 'making noise' = malfunction cue; "
                     "guard should hold escalation off; urgent accepted per Corby precedent",
    },
    {
        "key": "photo_fridge_frost_fire",
        "raw": "The freezer is building up crazy ice inside and the motor "
               "runs constantly now.",
        "photos": ["freezer interior caked in thick frost, ice blocking vents"],
        "expect_urgency": Urgency.URGENT,
        "expect_category": Trade.APPLIANCE,
        "rationale": "appliance outage-with-consequence line (fridge precedent) = urgent/appliance",
    },
]
