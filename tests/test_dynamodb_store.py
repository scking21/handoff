"""DynamoDBStore under moto: full Store-protocol roundtrips plus optimistic concurrency."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from moto import mock_aws

from handoff.domain.models import (
    Actor,
    ApprovalDecision,
    OutboundMessage,
    Property,
    Quote,
    Tenant,
    TicketStatus,
    TimelineEvent,
    Trade,
    Urgency,
    Vendor,
    WorkOrder,
)
from handoff.store.dynamodb import DynamoDBStore, TicketConflictError

TABLE = "handoff-test"


@pytest.fixture()
def store():
    with mock_aws():
        s = DynamoDBStore(table_name=TABLE, region="us-west-2")
        s.ensure_table()
        yield s


def _ticket(stall_count: int = 1) -> WorkOrder:
    return WorkOrder(
        property_id="prop1",
        unit="2B",
        tenant_id="ten1",
        raw_request="disposal hums then trips the breaker",
        status=TicketStatus.TRIAGED,
        category=Trade.ELECTRICAL,
        urgency=Urgency.URGENT,
        triage_rationale="electrical symptom",
        triage_confidence=0.87,
        quotes=[Quote(vendor_id="ven1", amount=180, eta_hours=4)],
        selected_vendor_id=None,
        pending_vendor_id="ven1",
        authorized_scope="diagnose disposal circuit",
        authorized_cost=180,
        scheduled_window="Tue 9-11",
        completion_notes="",
        parts_used=["breaker"],
        invoice_amount=None,
        invoice_discrepancy="",
        approval=ApprovalDecision(decision="approve", note="within budget"),
        idempotency_keys={"wo:triage", "quote:ven1"},
        stall_count=stall_count,
        timeline=[TimelineEvent(actor=Actor.AGENT, kind="triaged", detail="electrical")],
    )


def _vendor() -> Vendor:
    return Vendor(
        company="Amp Electric",
        contact_name="Ray",
        phone="+15551234567",
        trades=[Trade.ELECTRICAL, Trade.GENERAL],
        rating=4.6,
        hourly_rate=95,
        trip_fee=35,
        drive_minutes=18,
        certifications=["C10"],
    )


def test_roundtrip_every_entity_type(store):
    prop = Property(name="Oakwood", address="12 Oak St", units=["2B", "3A"])
    tenant = Tenant(name="Sam", unit="2B", property_id=prop.id, phone="+15550000001", email="s@x.io")
    vendor = _vendor()
    ticket = _ticket()

    store.put_property(prop)
    store.put_tenant(tenant)
    store.put_vendor(vendor)
    store.put_ticket(ticket)

    got_prop = store.list_properties()[0]
    assert (got_prop.id, got_prop.name, got_prop.units) == (prop.id, prop.name, ["2B", "3A"])

    got_tenant = store.get_tenant(tenant.id)
    assert got_tenant == tenant
    assert [t.id for t in store.list_tenants()] == [tenant.id]

    got_vendor = store.list_vendors("electrical")[0]
    assert got_vendor == vendor
    assert got_vendor.rating == pytest.approx(4.6)
    assert store.list_vendors("plumbing") == []

    got_ticket = store.get_ticket(ticket.id)
    assert got_ticket == ticket
    assert got_ticket.triage_confidence == pytest.approx(0.87)
    assert got_ticket.idempotency_keys == {"wo:triage", "quote:ven1"}
    assert got_ticket.approval.note == "within budget"
    assert got_ticket.timeline[0].actor == Actor.AGENT
    assert [t.id for t in store.list_tickets()] == [ticket.id]


def test_update_ticket_bumps_revision_and_returns_result(store):
    ticket = _ticket()
    store.put_ticket(ticket)
    assert ticket.revision == 1

    def mark_dispatched(wo: WorkOrder) -> str:
        wo.status = TicketStatus.DISPATCHED
        wo.timeline.append(TimelineEvent(actor=Actor.AGENT, kind="dispatched", detail="ven1"))
        return "DISPATCHED"

    assert store.update_ticket(ticket.id, mark_dispatched) == "DISPATCHED"
    got = store.get_ticket(ticket.id)
    assert got.revision == 2
    assert got.status == TicketStatus.DISPATCHED
    assert got.timeline[-1].kind == "dispatched"


def test_put_ticket_rebases_stale_writer_like_filestore(store):
    ticket = _ticket()
    store.put_ticket(ticket)
    stale = store.get_ticket(ticket.id)

    fresh = store.get_ticket(ticket.id)
    fresh.timeline.append(TimelineEvent(actor=Actor.VENDOR, kind="accepted", detail="en route"))
    store.put_ticket(fresh)

    stale.timeline.append(TimelineEvent(actor=Actor.PM, kind="approved", detail="ok"))
    store.put_ticket(stale)

    merged = store.get_ticket(ticket.id)
    actor_kinds = {(e.actor.value, e.kind) for e in merged.timeline}
    assert ("vendor", "accepted") in actor_kinds
    assert ("property_manager", "approved") in actor_kinds
    assert len([e for e in merged.timeline if e.kind == "triaged"]) == 1
    assert [e.at for e in merged.timeline] == sorted(e.at for e in merged.timeline)
    assert merged.revision == 3


def test_get_missing_ticket_returns_none_like_filestore(store):
    assert store.get_ticket("wo_nope") is None
    assert store.get_tenant("ten_nope") is None


def test_update_ticket_returns_mutator_result_and_none_when_missing(store):
    assert store.update_ticket("wo_missing", lambda t: "unused") is None

    store.put_ticket(_ticket())
    seen = {}

    def mut(t: WorkOrder) -> str:
        seen["status"] = t.status
        t.stall_count += 1
        return "STALLED"

    assert store.update_ticket(store.list_tickets()[0].id, mut) == "STALLED"
    assert seen["status"] == TicketStatus.TRIAGED
    assert store.get_ticket(store.list_tickets()[0].id).stall_count == 2


def test_sequential_mutators_preserve_both_updates(store):
    t = _ticket()
    store.put_ticket(t)

    store.update_ticket(t.id, lambda w: w.quotes.append(Quote(vendor_id="ven2", amount=200, eta_hours=6)) or "q2")
    store.update_ticket(t.id, lambda w: w.record(Actor.VENDOR, "quote_received", "$200"))

    final = store.get_ticket(t.id)
    assert [q.vendor_id for q in final.quotes] == ["ven1", "ven2"]
    assert [e.kind for e in final.timeline] == ["triaged", "quote_received"]


def test_concurrent_mutators_never_lose_updates(store):
    t = _ticket(stall_count=0)
    store.put_ticket(t)
    n = 24

    def bump(_: int) -> str:
        def mut(w: WorkOrder) -> str:
            w.stall_count += 1
            return "+1"

        return store.update_ticket(t.id, mut)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(bump, range(n)))

    assert results.count("+1") == n
    assert store.get_ticket(t.id).stall_count == n


def test_version_conflict_retries_and_succeeds(store):
    t = _ticket()
    store.put_ticket(t)

    real_put = store.client.put_item
    calls = {"n": 0}

    def flaky_put(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise store.client.exceptions.ConditionalCheckFailedException(
                {"Error": {"Code": "ConditionalCheckFailedException", "Message": "version mismatch"}},
                "PutItem",
            )
        return real_put(**kwargs)

    store.client.put_item = flaky_put
    try:
        out = store.update_ticket(t.id, lambda w: (setattr(w, "stall_count", 7), "OK")[1])
    finally:
        del store.client.put_item

    assert out == "OK"
    assert calls["n"] == 2
    assert store.get_ticket(t.id).stall_count == 7


def test_retry_exhaustion_raises_instead_of_losing_update(store):
    t = _ticket()
    store.put_ticket(t)

    def always_conflict(**kwargs):
        raise store.client.exceptions.ConditionalCheckFailedException(
            {"Error": {"Code": "ConditionalCheckFailedException", "Message": "nope"}}, "PutItem"
        )

    store.client.put_item = always_conflict
    try:
        with pytest.raises(TicketConflictError):
            store.update_ticket(t.id, lambda w: "never")
    finally:
        del store.client.put_item

    assert store.get_ticket(t.id).stall_count == 1


def test_messages_sorted_and_filtered_by_ticket(store):
    early = OutboundMessage(ticket_id="wo_a", to_role=Actor.TENANT, to_id="ten1", body="ack", kind="ack")
    late = OutboundMessage(ticket_id="wo_a", to_role=Actor.TENANT, to_id="ten1", body="done?", kind="closeout_check")
    other = OutboundMessage(ticket_id="wo_b", to_role=Actor.VENDOR, to_id="ven1", body="offer", kind="dispatch_offer")
    late.sent_at = datetime.now(UTC)
    other.sent_at = datetime.now(UTC)
    for m in (late, other, early):
        store.record_message(m)

    assert [m.kind for m in store.list_messages("wo_a")] == ["ack", "closeout_check"]
    assert len(store.list_messages()) == 3


def test_ensure_table_is_idempotent(store):
    store.ensure_table()
    desc = store.client.describe_table(TableName=TABLE)["Table"]
    assert desc["KeySchema"] == [
        {"AttributeName": "pk", "KeyType": "HASH"},
        {"AttributeName": "sk", "KeyType": "RANGE"},
    ]
