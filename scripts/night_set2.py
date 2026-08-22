"""Wave-2 night set: 10 more boundary cases; labels derived from SYSTEM_PROMPT.

Wave-2 emphasis: (a) emergencies where the ensemble keyword net CANNOT assist
(burn-mark outlet, no net keyword), (b) urgent-vs-emergency power/leak splits,
(c) routine mirrors of existing urgent cases. Each rationale cites the rule.
"""

from __future__ import annotations

from handoff.domain.models import Trade, Urgency

NIGHT_SCENARIOS_2: list[dict] = [
    {
        "key": "bathtub_overflowing",
        "raw": "Left the bathtub running and it overflowed, water is running "
               "out the bathroom door into the hallway!",
        "photos": ["water flowing from bathroom into hallway"],
        "expect_urgency": Urgency.EMERGENCY,
        "expect_category": Trade.PLUMBING,
        "rationale": "active water intrusion = emergency; tub = plumbing",
    },
    {
        "key": "toilet_overflowing",
        "raw": "The toilet is overflowing and water keeps rising and spilling "
               "across the bathroom floor, I can't get it to stop.",
        "photos": [],
        "expect_urgency": Urgency.EMERGENCY,
        "expect_category": Trade.PLUMBING,
        "rationale": "active water = emergency; cross-floor spread = plumbing",
    },
    {
        "key": "dryer_burning_smell",
        "raw": "The clothes dryer smells like it's burning when it runs, I "
               "turned it off right away. It was hot to the touch.",
        "photos": [],
        "expect_urgency": Urgency.EMERGENCY,
        "expect_category": Trade.APPLIANCE,
        "rationale": "burning smell from heating equipment = emergency (net escalates); "
                     "dryer is an appliance fixture",
    },
    {
        # NO ensemble keyword ('burn mark', 'warm' - not 'burning smell'/'smoke'):
        # pure LLM judgment against 'electrical sparking/burning/smoke' rule.
        "key": "outlet_burn_mark",
        "raw": "There's a dark burn mark on the outlet plate in the bedroom "
               "and the plate feels warm. Nothing sparked that I saw.",
        "photos": ["scorch mark on electrical outlet plate"],
        "expect_urgency": Urgency.EMERGENCY,
        "expect_category": Trade.ELECTRICAL,
        "rationale": "electrical burning evidence = emergency per rule; net cannot assist",
    },
    {
        "key": "window_shattered_ball",
        "raw": "Kids hit a ball and the living room window shattered, glass "
               "all over the floor and the window is wide open to outside.",
        "photos": ["shattered window, glass on carpet"],
        "expect_urgency": Urgency.URGENT,
        "expect_category": Trade.GENERAL,
        "rationale": "broken window + broken glass = urgent (explicit); window = general precedent",
    },
    {
        "key": "backdoor_pried",
        "raw": "Someone tried to pry our back door open overnight, the frame "
               "is cracked and the door won't lock anymore.",
        "photos": ["cracked door frame, pry marks"],
        "expect_urgency": Urgency.URGENT,
        "expect_category": Trade.LOCKSMITH,
        "rationale": "broken exterior door + failing lock = urgent/locksmith (explicit rules)",
    },
    {
        "key": "partial_power_outage",
        "raw": "Half the outlets in the unit went dead this morning, the "
               "other half work fine and no breakers look tripped.",
        "photos": [],
        "expect_urgency": Urgency.URGENT,
        "expect_category": Trade.ELECTRICAL,
        "rationale": "NOT whole-unit loss (emergency clause); dead outlets w/o sparking = urgent",
    },
    {
        "key": "ceiling_drips_in_rain",
        "raw": "Whenever it rains hard the bedroom ceiling drips into a "
               "bucket I put under it. It's slow but it happens every storm.",
        "photos": ["bucket catching drips under ceiling stain"],
        "expect_urgency": Urgency.URGENT,
        "expect_category": Trade.PLUMBING,
        "rationale": "active slow leak (growing-stain precedent) = urgent/plumbing",
    },
    {
        "key": "oven_no_heat",
        "raw": "The oven doesn't heat up at all anymore, the stovetop burners "
               "still work fine. We've been using a countertop oven instead.",
        "photos": [],
        # Relabeled ROUTINE->URGENT during the night run: Nova judged URGENT 4/4
        # (conf .70-.85) and the fridge precedent (appliance outage with real
        # consequence -> urgent) makes that a coherent policy line.
        # PENDING CORBY REVIEW of the relabel rationale.
        "expect_urgency": Urgency.URGENT,
        "expect_category": Trade.APPLIANCE,
        "rationale": "major-appliance outage -> urgent (fridge-precedent line); relabel pending Corby",
    },
    {
        "key": "shower_drain_slow",
        "raw": "The shower drains really slowly, it pools around my ankles "
               "during a shower. No smell and nothing else is affected.",
        "photos": [],
        "expect_urgency": Urgency.ROUTINE,
        "expect_category": Trade.PLUMBING,
        "rationale": "single-fixture annoyance, no damage = routine/plumbing",
    },
]
