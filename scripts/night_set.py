"""Night-set: 10 adversarial triage scenarios + 1 flagged keyword-net probe.

Labels are DERIVED from LLMTriageProvider.SYSTEM_PROMPT's own written rules
(agents/decisions.py), not intuition — each rationale cites the governing rule.
The 10 headline cases fill decision boundaries the 22-case library leaves
uncovered; `smoke_detector_chirp` is a deliberately contested probe of
SafetyEnsembleProvider keyword over-breadth and is excluded from headline
accuracy when NIGHT_HEADLINE_ONLY is set.
"""

from __future__ import annotations

from handoff.domain.models import Trade, Urgency

NIGHT_SCENARIOS: list[dict] = [
    {
        # Rule: "appliance fixtures ... are appliance, NOT plumbing, even when
        # they leak" x "active water intrusion (pouring/flooding)" = emergency.
        "key": "washing_machine_flooding",
        "raw": "The washing machine is flooding our laundry closet, water is "
               "spreading into the hallway really fast!",
        "photos": ["water spreading across laundry room floor"],
        "expect_urgency": Urgency.EMERGENCY,
        "expect_category": Trade.APPLIANCE,
        "rationale": "flooding=emergency + appliance-fixture rule overrides plumbing",
    },
    {
        # Rule: "sewage backup" listed under emergency; ensemble keyword "sewage".
        "key": "sewage_into_tub",
        "raw": "The toilet is backing up and sewage is coming up into the "
               "bathtub, the smell is horrible.",
        "photos": [],
        "expect_urgency": Urgency.EMERGENCY,
        "expect_category": Trade.PLUMBING,
        "rationale": "sewage backup = emergency verbatim; cross-fixture = plumbing",
    },
    {
        # Rule: "safety-adjacent hazards (dead outlet WITHOUT sparking ...)"
        # = urgent; repeated breaker trips, no spark/smoke anywhere.
        "key": "breaker_trips_daily",
        "raw": "The bedroom breaker trips every single time we run the space "
               "heater, I have to go reset it in the panel once or twice a day.",
        "photos": [],
        "expect_urgency": Urgency.URGENT,
        "expect_category": Trade.ELECTRICAL,
        "rationale": "electrical hazard without sparking = urgent, not emergency",
    },
    {
        # Rule: "Lockouts AND failing door locks are locksmith"; lockout=
        # emergency but "loose/failing door locks"=urgent. Tenant is INSIDE.
        "key": "key_snapped_in_lock",
        "raw": "My key snapped off inside the front door lock and now I can't "
               "lock the door when I leave for work.",
        "photos": [],
        "expect_urgency": Urgency.URGENT,
        "expect_category": Trade.LOCKSMITH,
        "rationale": "failing lock = urgent/locksmith; not a lockout (tenant inside)",
    },
    {
        # Rule: "primary systems down (... no hot water anywhere in the unit)"
        # = urgent — verbatim phrase.
        "key": "no_hot_water_anywhere",
        "raw": "There has been no hot water at all anywhere in the unit since "
               "yesterday morning, every faucet and the shower all run cold.",
        "photos": [],
        "expect_urgency": Urgency.URGENT,
        "expect_category": Trade.PLUMBING,
        "rationale": "'no hot water anywhere in the unit' = urgent verbatim",
    },
    {
        # Rule: "active slow leaks" = urgent; water heater is a plumbing
        # fixture — NOT in the appliance fixture list.
        "key": "water_heater_leaking",
        "raw": "The water heater in the hallway closet is leaking from the "
               "bottom, there's a slow-growing puddle around the base.",
        "photos": ["puddle at base of water heater"],
        "expect_urgency": Urgency.URGENT,
        "expect_category": Trade.PLUMBING,
        "rationale": "slow leak = urgent; heater outside appliance fixture list = plumbing",
    },
    {
        # Rules: "broken exterior door/window" + "failing door locks" = urgent;
        # "Lockouts AND failing door locks are locksmith". Ground floor raises
        # stakes but no forced entry in progress.
        "key": "patio_slider_wont_lock",
        "raw": "Our ground-floor patio slider won't lock at all, we don't feel "
               "safe leaving it unlocked overnight.",
        "photos": [],
        "expect_urgency": Urgency.URGENT,
        "expect_category": Trade.LOCKSMITH,
        "rationale": "broken exterior door security = urgent; failing lock = locksmith",
    },
    {
        # Analogy to labeled dishwasher_leak_small -> routine/appliance:
        # contained, recurring, single-fixture, no hazard.
        "key": "fridge_puddle_daily",
        "raw": "There's a small puddle forming under the fridge that I end up "
               "wiping up twice a day. Food is still cold.",
        "photos": ["small puddle under refrigerator"],
        "expect_urgency": Urgency.ROUTINE,
        "expect_category": Trade.APPLIANCE,
        "rationale": "single-fixture annoyance, contained = routine (dishwasher precedent)",
    },
    {
        # Rule: routine = "single-fixture annoyances that cause no damage or
        # hazard"; standing water INSIDE the tub is not active intrusion;
        # no ensemble keyword hits.
        "key": "dishwasher_standing_water",
        "raw": "The dishwasher isn't draining so there's standing water in the "
               "bottom after a cycle, and it's starting to smell a bit stale.",
        "photos": [],
        "expect_urgency": Urgency.ROUTINE,
        "expect_category": Trade.APPLIANCE,
        "rationale": "single-fixture annoyance = routine; appliance-not-plumbing",
    },
    {
        # Rule: routine = cosmetic/single-fixture annoyances; fills the empty
        # routine/electrical cell of the urgency-x-category grid.
        "key": "hallway_light_flickers",
        "raw": "The hallway light flickers now and then. I already swapped the "
               "bulb and it didn't help, but everything else in the unit works fine.",
        "photos": [],
        "expect_urgency": Urgency.ROUTINE,
        "expect_category": Trade.ELECTRICAL,
        "rationale": "cosmetic single-fixture = routine; no spark/smoke = not emergency",
    },
]

# Flagged probe — deliberately contested. SYSTEM_PROMPT reserves "emergency"
# for "smoke or carbon-monoxide detector ACTIVATION"; a low-battery chirp is a
# trouble signal, not activation. Probe outcome (2026-08-21 night run): with
# the keyword-net guard in place, Nova judges the chirp URGENT (conf ~0.65,
# "needs attention") — accepted as correct per Corby; label updated from the
# original ROUTINE hypothesis. The probe's permanent job is to pin that the
# ensemble does NOT force EMERGENCY on detector-maintenance talk.
CHIRP_PROBE: dict = {
    "key": "smoke_detector_chirp",
    "raw": "The smoke detector in the hallway keeps chirping every 30 seconds. "
           "Pretty sure it just needs a new battery, it's driving us crazy.",
    "photos": [],
    # Live reps show Nova genuinely wavers urgent(conf .65) <-> routine(.60-.70)
    # here (sampling noise; eval path runs without temperature pinning - see
    # notes), so the STABLE invariant is asserted instead of the exact label:
    # the ensemble must NOT force EMERGENCY on detector-maintenance talk.
    # Corby accepted 'urgent' as a reasonable judgment when it occurs.
    "assert_not_urgency": Urgency.EMERGENCY,
    "label_note": "wavers urgent<->routine live; must never be emergency",
    "expect_category": Trade.GENERAL,
    "rationale": "chirp != activation; net must not escalate; exact label unstable by measurement",
}
