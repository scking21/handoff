"""DynamoDB store: production adapter implementing the same Store protocol as FileStore.

Single-table layout: partition key ``pk`` names the entity collection
(ticket|vendor|property|tenant|message), sort key ``sk`` is the entity id.
Every row carries an integer ``version`` and its payload under ``data``.

Why single-table-with-collection-partitions instead of PK=id/SK=type: every
access pattern in the workflow maps to one collection (get by id, list whole
collection), so a Query per collection mirrors FileStore's per-file layout
with no scans and no GSIs. Multi-tenancy later becomes a prefix inside ``pk``
(``<env>#ticket``) with zero table changes.

Concurrency contract (must match FileStore.update_ticket): atomic
read-modify-write that RETURNS the mutator's result. Here the lock is replaced
by optimistic concurrency — read version, mutate, conditional put requiring
that exact version, retry on conflict. Batched tool calls running concurrently
across processes can queue behind each other but never lose an update.
"""

from __future__ import annotations

import os
import time
from decimal import Decimal
from typing import Any

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

from handoff.domain.models import OutboundMessage, Property, Tenant, Vendor, WorkOrder

_TICKET = "ticket"
_VENDOR = "vendor"
_PROPERTY = "property"
_TENANT = "tenant"
_MESSAGE = "message"


class TicketConflictError(RuntimeError):
    """Raised when an optimistic-concurrency write exhausts its retry budget."""


_SERIALIZER = TypeSerializer()
_DESERIALIZER = TypeDeserializer()


def _to_decimal(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_decimal(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_decimal(v) for v in value]
    return value


class DynamoDBStore:
    """Store protocol backed by one DynamoDB table. boto3 client is injectable
    so moto (or a local endpoint such as DynamoDB Local) can stand in for AWS."""

    def __init__(
        self,
        table_name: str | None = None,
        *,
        region: str | None = None,
        endpoint_url: str | None = None,
        client=None,
        max_attempts: int = 8,
        backoff_seconds: float = 0.05,
    ):
        self.table_name = table_name or os.getenv("HANDOFF_DDB_TABLE", "handoff")
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        if client is None:
            import boto3

            kwargs: dict[str, Any] = {}
            if region:
                kwargs["region_name"] = region
            if endpoint_url:
                kwargs["endpoint_url"] = endpoint_url
            elif env_endpoint := os.getenv("HANDOFF_DDB_ENDPOINT"):
                kwargs["endpoint_url"] = env_endpoint
            client = boto3.client("dynamodb", **kwargs)
        self.client = client

    def ensure_table(self, billing_mode: str = "PAY_PER_REQUEST") -> None:
        """Create the table if missing. Safe to call on every boot."""
        try:
            self.client.describe_table(TableName=self.table_name)
            return
        except self.client.exceptions.ResourceNotFoundException:
            pass
        try:
            self.client.create_table(
                TableName=self.table_name,
                KeySchema=[
                    {"AttributeName": "pk", "KeyType": "HASH"},
                    {"AttributeName": "sk", "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "pk", "AttributeType": "S"},
                    {"AttributeName": "sk", "AttributeType": "S"},
                ],
                BillingMode=billing_mode,
            )
        except self.client.exceptions.ResourceInUseException:
            pass
        waiter = self.client.get_waiter("table_exists")
        waiter.wait(TableName=self.table_name)

    def _query_all(self, pk: str) -> list[dict]:
        items: list[dict] = []
        kwargs: dict[str, Any] = {
            "TableName": self.table_name,
            "KeyConditionExpression": "#p = :v",
            "ExpressionAttributeNames": {"#p": "pk"},
            "ExpressionAttributeValues": {":v": {"S": pk}},
        }
        while True:
            resp = self.client.query(**kwargs)
            for item in resp.get("Items", []):
                items.append(
                    {"version": int(item["version"]["N"]), "data": _DESERIALIZER.deserialize({"M": item["data"]["M"]})}
                )
            if "LastEvaluatedKey" not in resp:
                return items
            kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    def _raw_get(self, pk: str, sk: str) -> dict | None:
        resp = self.client.get_item(
            TableName=self.table_name,
            Key={"pk": {"S": pk}, "sk": {"S": sk}},
            ConsistentRead=True,
        )
        item = resp.get("Item")
        if not item:
            return None
        data = _DESERIALIZER.deserialize({"M": item["data"]["M"]})
        return {"version": int(item["version"]["N"]), "data": data}

    def _conditional_put(self, pk: str, sk: str, data: dict[str, Any]) -> None:
        """Version-bumped upsert; retries while another writer wins the race."""
        payload = {"M": _SERIALIZER.serialize(_to_decimal(data))["M"]}
        for attempt in range(self.max_attempts):
            existing = self._raw_get(pk, sk)
            if existing is None:
                condition = "attribute_not_exists(version)"
                values: dict[str, Any] | None = None
                version = 0
            else:
                version = existing["version"] + 1
                condition = "version = :expected"
                values = {":expected": {"N": str(existing["version"])}}
            request: dict[str, Any] = {
                "TableName": self.table_name,
                "Item": {
                    "pk": {"S": pk},
                    "sk": {"S": sk},
                    "version": {"N": str(version)},
                    "data": payload,
                },
                "ConditionExpression": condition,
            }
            if values:
                request["ExpressionAttributeValues"] = values
            try:
                self.client.put_item(**request)
                return
            except self.client.exceptions.ConditionalCheckFailedException:
                time.sleep(self.backoff_seconds * min(attempt + 1, 5))
        raise TicketConflictError(
            f"write to {pk}/{sk} lost {self.max_attempts} version races; investigate writer skew"
        )

    @staticmethod
    def _validate(model_cls, data: dict[str, Any]):
        return model_cls.model_validate(data)

    # tickets ---------------------------------------------------------------

    def put_ticket(self, ticket: WorkOrder) -> None:
        self._conditional_put(_TICKET, ticket.id, ticket.model_dump(mode="json"))

    def get_ticket(self, ticket_id: str) -> WorkOrder | None:
        raw = self._raw_get(_TICKET, ticket_id)
        return self._validate(WorkOrder, raw["data"]) if raw else None

    def update_ticket(self, ticket_id: str, mutator):
        """Atomic read-modify-write via optimistic version check. Returns the
        mutator's result (typically the tool response string), or None when the
        ticket does not exist — matching FileStore."""
        last_error: Exception | None = None
        for _ in range(self.max_attempts):
            raw = self._raw_get(_TICKET, ticket_id)
            if raw is None:
                return None
            ticket = self._validate(WorkOrder, raw["data"])
            result = mutator(ticket)
            expected = raw["version"]
            try:
                self.client.put_item(
                    TableName=self.table_name,
                    Item={
                        "pk": {"S": _TICKET},
                        "sk": {"S": ticket_id},
                        "version": {"N": str(expected + 1)},
                        "data": {"M": _SERIALIZER.serialize(_to_decimal(ticket.model_dump(mode="json")))["M"]},
                    },
                    ConditionExpression="version = :expected",
                    ExpressionAttributeValues={":expected": {"N": str(expected)}},
                )
                return result
            except self.client.exceptions.ConditionalCheckFailedException as exc:
                last_error = exc
                time.sleep(self.backoff_seconds * min((_ + 1), 5))
        raise TicketConflictError(
            f"update_ticket({ticket_id}) lost {self.max_attempts} version races; investigate writer skew"
        ) from last_error

    def list_tickets(self) -> list[WorkOrder]:
        return [self._validate(WorkOrder, i["data"]) for i in self._query_all(_TICKET)]

    # vendors -----------------------------------------------------------------

    def put_vendor(self, vendor: Vendor) -> None:
        self._conditional_put(_VENDOR, vendor.id, vendor.model_dump(mode="json"))

    def list_vendors(self, trade: str | None = None) -> list[Vendor]:
        vendors = [self._validate(Vendor, i["data"]) for i in self._query_all(_VENDOR)]
        if trade:
            vendors = [v for v in vendors if any(t.value == trade for t in v.trades)]
        return vendors

    # properties --------------------------------------------------------------

    def put_property(self, prop: Property) -> None:
        self._conditional_put(_PROPERTY, prop.id, prop.model_dump(mode="json"))

    def list_properties(self) -> list[Property]:
        return [self._validate(Property, i["data"]) for i in self._query_all(_PROPERTY)]

    # tenants -----------------------------------------------------------------

    def put_tenant(self, tenant: Tenant) -> None:
        self._conditional_put(_TENANT, tenant.id, tenant.model_dump(mode="json"))

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        raw = self._raw_get(_TENANT, tenant_id)
        return self._validate(Tenant, raw["data"]) if raw else None

    def list_tenants(self) -> list[Tenant]:
        return [self._validate(Tenant, i["data"]) for i in self._query_all(_TENANT)]

    # messages ----------------------------------------------------------------

    def record_message(self, msg: OutboundMessage) -> None:
        self._conditional_put(_MESSAGE, msg.id, msg.model_dump(mode="json"))

    def list_messages(self, ticket_id: str | None = None) -> list[OutboundMessage]:
        msgs = [self._validate(OutboundMessage, i["data"]) for i in self._query_all(_MESSAGE)]
        if ticket_id:
            msgs = [m for m in msgs if m.ticket_id == ticket_id]
        return sorted(msgs, key=lambda m: m.sent_at)
