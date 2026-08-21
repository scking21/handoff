"""Persistence layer.

FileStore is the local/demo adapter; a DynamoDBStore implementing the same
protocol swaps in for deployment. Agents depend on this protocol, never on
storage details — that boundary is what makes the orchestration durable and
the tests fast.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Protocol

from handoff.domain.models import Actor, OutboundMessage, Property, Tenant, Vendor, WorkOrder


class Store(Protocol):
    def put_ticket(self, ticket: WorkOrder) -> None: ...
    def get_ticket(self, ticket_id: str) -> WorkOrder | None: ...
    def update_ticket(self, ticket_id: str, mutator):
        """Atomic read-modify-write. Returns the mutator's result value.
        LLMs batch tool calls and executors may run them concurrently;
        without this, parallel tools lose updates."""
        ...
    def list_tickets(self) -> list[WorkOrder]: ...
    def put_vendor(self, vendor: Vendor) -> None: ...
    def list_vendors(self, trade: str | None = None) -> list[Vendor]: ...
    def put_property(self, prop: Property) -> None: ...
    def list_properties(self) -> list[Property]: ...
    def put_tenant(self, tenant: Tenant) -> None: ...
    def get_tenant(self, tenant_id: str) -> Tenant | None: ...
    def list_tenants(self) -> list[Tenant]: ...
    def record_message(self, msg: OutboundMessage) -> None: ...
    def list_messages(self, ticket_id: str | None = None) -> list[OutboundMessage]: ...


class FileStore:
    """Thread-safe JSON-file-backed store for local dev and demos."""

    def __init__(self, root: str | Path = "data/runtime"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _read(self, name: str) -> dict:
        path = self.root / f"{name}.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text())

    def _write(self, name: str, data: dict) -> None:
        path = self.root / f"{name}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str))
        tmp.replace(path)

    def put_ticket(self, ticket: WorkOrder) -> None:
        with self._lock:
            data = self._read("tickets")
            data[ticket.id] = ticket.model_dump(mode="json")
            self._write("tickets", data)

    def get_ticket(self, ticket_id: str) -> WorkOrder | None:
        with self._lock:
            raw = self._read("tickets").get(ticket_id)
        return WorkOrder.model_validate(raw) if raw else None

    def update_ticket(self, ticket_id: str, mutator):
        """Atomic read-modify-write under the store lock; returns whatever the
        mutator returns (typically the tool's response string).

        Serializes concurrent tool calls within this process. The production
        DynamoDBStore implements the same guarantee with conditional writes
        (attribute_not_exists/versions), so agents that batch tool calls can
        never lose an update."""
        with self._lock:
            raw = self._read("tickets").get(ticket_id)
            if not raw:
                return None
            ticket = WorkOrder.model_validate(raw)
            result = mutator(ticket)
            self.put_ticket(ticket)
            return result

    def list_tickets(self) -> list[WorkOrder]:
        with self._lock:
            rows = list(self._read("tickets").values())
        return [WorkOrder.model_validate(r) for r in rows]

    def put_vendor(self, vendor: Vendor) -> None:
        with self._lock:
            data = self._read("vendors")
            data[vendor.id] = vendor.model_dump(mode="json")
            self._write("vendors", data)

    def list_vendors(self, trade: str | None = None) -> list[Vendor]:
        with self._lock:
            rows = list(self._read("vendors").values())
        vendors = [Vendor.model_validate(r) for r in rows]
        if trade:
            vendors = [v for v in vendors if any(t.value == trade for t in v.trades)]
        return vendors

    def put_property(self, prop: Property) -> None:
        with self._lock:
            data = self._read("properties")
            data[prop.id] = prop.model_dump(mode="json")
            self._write("properties", data)

    def list_properties(self) -> list[Property]:
        with self._lock:
            rows = list(self._read("properties").values())
        return [Property.model_validate(r) for r in rows]

    def put_tenant(self, tenant: Tenant) -> None:
        with self._lock:
            data = self._read("tenants")
            data[tenant.id] = tenant.model_dump(mode="json")
            self._write("tenants", data)

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        with self._lock:
            raw = self._read("tenants").get(tenant_id)
        return Tenant.model_validate(raw) if raw else None

    def list_tenants(self) -> list[Tenant]:
        with self._lock:
            rows = list(self._read("tenants").values())
        return [Tenant.model_validate(r) for r in rows]

    def record_message(self, msg: OutboundMessage) -> None:
        with self._lock:
            data = self._read("messages")
            data[msg.id] = msg.model_dump(mode="json")
            self._write("messages", data)

    def list_messages(self, ticket_id: str | None = None) -> list[OutboundMessage]:
        with self._lock:
            rows = list(self._read("messages").values())
        msgs = [OutboundMessage.model_validate(r) for r in rows]
        if ticket_id:
            msgs = [m for m in msgs if m.ticket_id == ticket_id]
        return sorted(msgs, key=lambda m: m.sent_at)
