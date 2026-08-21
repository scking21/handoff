"""Synthetic world generation.

The demo needs a believable property-management world: properties, tenants,
a vendor bench with realistic trade/skill/cost spread, and a scenario library
of maintenance requests that covers the judgment-heavy cases triage must get
right (midnight flood vs. vague noise vs. routine annoyance).
"""

from __future__ import annotations

from faker import Faker

from handoff.domain.models import Actor, Property, Tenant, Trade, Urgency, Vendor
from handoff.store.base import Store

fake = Faker()
Faker.seed(2026)


VENDOR_BENCH = [
    ("Rapid Rooter Plumbing", [Trade.PLUMBING], 4.8, 95, 75, 18, True, ["C36"]),
    ("Bay Area Pipe Works", [Trade.PLUMBING], 4.2, 80, 50, 35, False, ["C36"]),
    ("AllSeason HVAC", [Trade.HVAC], 4.6, 110, 89, 25, True, ["C20", "EPA 608"]),
    ("CoolAir Bros", [Trade.HVAC], 3.9, 85, 45, 40, False, ["EPA 608"]),
    ("Volt Masters Electric", [Trade.ELECTRICAL], 4.7, 120, 80, 22, True, ["C10"]),
    ("SparkFix", [Trade.ELECTRICAL], 4.0, 90, 40, 45, False, []),
    ("FixIt Handyman", [Trade.GENERAL, Trade.APPLIANCE], 4.4, 65, 35, 15, True, []),
    ("ApplianceMedic", [Trade.APPLIANCE], 4.5, 75, 60, 30, False, ["Factory-authorized"]),
    ("KeyLine Locksmith", [Trade.LOCKSMITH], 4.9, 130, 65, 12, True, ["Licensed"]),
]


def seed_world(store: Store, num_properties: int = 3) -> list[Tenant]:
    """Populate properties, units, tenants and the vendor bench."""
    tenants: list[Tenant] = []
    for _ in range(num_properties):
        prop = Property(
            name=f"{fake.last_name()} {fake.street_suffix()} Apartments",
            address=fake.street_address(),
            units=[f"{n}{s}" for n in range(1, 5) for s in ("A", "B")],
        )
        store.put_property(prop)
        for unit in prop.units:
            tenant = Tenant(
                name=fake.first_name() + " " + fake.last_name(),
                unit=unit,
                property_id=prop.id,
                phone=fake.phone_number(),
                email=fake.email(),
            )
            store.put_tenant(tenant)
            tenants.append(tenant)

    for company, trades, rating, rate, trip, drive, on_call, certs in VENDOR_BENCH:
        vendor = Vendor(
            company=company,
            contact_name=fake.first_name() + " " + fake.last_name(),
            phone=fake.phone_number(),
            trades=trades,
            rating=rating,
            hourly_rate=rate,
            trip_fee=trip,
            drive_minutes=drive,
            on_call_now=on_call,
            certifications=certs,
            completed_jobs=fake.random_int(40, 400),
            no_show_count=fake.random_int(0, 6),
        )
        store.put_vendor(vendor)
    return tenants


SCENARIOS: list[dict] = [
    {
        "key": "midnight_flood",
        "raw": "There's water pouring through the kitchen ceiling light fixture and it's spreading fast across the floor!!",
        "photos": ["water dripping from light fixture, large puddle on floor"],
        "expect_urgency": Urgency.EMERGENCY,
        "expect_category": Trade.PLUMBING,
    },
    {
        "key": "gas_smell",
        "raw": "I smell gas near the stove, it's pretty strong. Neighbors say they smell it too.",
        "photos": [],
        "expect_urgency": Urgency.EMERGENCY,
        "expect_category": Trade.PLUMBING,
    },
    {
        "key": "no_heat_winter",
        "raw": "The heater hasn't worked since yesterday and it's freezing in here, thermostat reads 58F.",
        "photos": [],
        "expect_urgency": Urgency.URGENT,
        "expect_category": Trade.HVAC,
    },
    {
        "key": "vague_noise",
        "raw": "The AC is making a weird noise sometimes. Not sure how to describe it, kind of a rattle?",
        "photos": [],
        "expect_urgency": Urgency.ROUTINE,
        "expect_category": Trade.HVAC,
    },
    {
        "key": "dripping_faucet",
        "raw": "Kitchen faucet drips constantly. Been like that a couple weeks, just annoying.",
        "photos": ["slow drip from faucet handle"],
        "expect_urgency": Urgency.ROUTINE,
        "expect_category": Trade.PLUMBING,
    },
    {
        "key": "broken_outlet",
        "raw": "Outlet in the bathroom sparked when I plugged in my hairdryer and now it doesn't work at all.",
        "photos": ["scorch mark on outlet cover"],
        "expect_urgency": Urgency.URGENT,
        "expect_category": Trade.ELECTRICAL,
    },
    {
        "key": "locked_out",
        "raw": "Locked myself out, standing outside with groceries. Can someone help?",
        "photos": [],
        "expect_urgency": Urgency.EMERGENCY,
        "expect_category": Trade.LOCKSMITH,
    },
    {
        "key": "dishwasher_leak_small",
        "raw": "Dishwasher leaks a little onto the floor when it runs the full cycle. We put a towel down.",
        "photos": ["small water pooling at base of dishwasher"],
        "expect_urgency": Urgency.ROUTINE,
        "expect_category": Trade.APPLIANCE,
    },
]


def make_request(store: Store, scenario_key: str | None = None, tenant: Tenant | None = None):
    """Create an intake payload from a chosen (or random) scenario."""
    import random

    scen = next((s for s in SCENARIOS if s["key"] == scenario_key), None) or random.choice(SCENARIOS)
    if tenant is None:
        tenant = random.choice(store.list_tenants())
    return {
        "scenario": scen["key"],
        "tenant_id": tenant.id,
        "property_id": tenant.property_id,
        "unit": tenant.unit,
        "raw": scen["raw"],
        "photos": list(scen["photos"]),
        "expect_urgency": scen["expect_urgency"],
        "expect_category": scen["expect_category"],
    }
