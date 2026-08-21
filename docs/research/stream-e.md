# Stream E — DynamoDBStore, OTel flag, SMS channels

Branch `build/dynamo-channels`. Three commits: `b372f6d` (store), `885a42c` (tracing), `dd1e63f` (channels).
No owned files touched; no dependency changes committed.

## E.1 DynamoDBStore — `src/handoff/store/dynamodb.py`

**Layout: single table, `pk` = entity collection (`ticket|vendor|property|tenant|message`), `sk` = entity id.**
Chosen over `PK=id, SK=type` because every access pattern in the workflow is "get by id" or "list a
collection" — one Query per collection, zero Scans, zero GSIs, and it mirrors FileStore's per-file
layout 1:1. Rows carry an integer `version` and the payload under a `data` map (keeps us clear of
DynamoDB reserved words like `STATUS`/`NAME`). Multi-tenancy later = prefix inside `pk`
(`<env>#ticket`), no table change. `list_vendors(trade)` / `list_messages(ticket_id)` filter
client-side exactly like FileStore; a GSI on `data.ticket_id` is the upgrade path if message volume
ever matters.

**Contract parity with `FileStore.update_ticket`:** atomic read-modify-write that RETURNS the
mutator's result; returns `None` when the ticket is missing. The in-process lock is replaced by
optimistic concurrency: read `version` → run mutator → conditional put requiring that exact version
→ on `ConditionalCheckFailedException`, back off and retry (`max_attempts=8`, linear-ish backoff).
Exhaustion raises `TicketConflictError` — a loud failure beats a silently lost update. `put_ticket`
uses the same versioned conditional write, so even the create path is race-safe cross-process.
Existence checks use `attribute_not_exists(version)` (every written row has `version`; `sk` alone
can't be used since it's a key attribute).

**Serialization:** `model_dump(mode="json")` → floats recursively converted to `Decimal` (DynamoDB
rejects floats) → `TypeSerializer`. On read, `TypeDeserializer` → pydantic coerces `Decimal`→float,
ISO strings→datetimes, lists→`idempotency_keys` set. Verified by roundtrip tests on every entity
type. Queries paginate via `LastEvaluatedKey`; gets use `ConsistentRead=True`.

**Config surface:** `DynamoDBStore(table_name, region, endpoint_url, client, max_attempts,
backoff_seconds)` — boto3 client is injectable (moto / DynamoDB Local / AWS all drive it); env
fallbacks `HANDOFF_DDB_TABLE`, `HANDOFF_DDB_ENDPOINT`. `store.ensure_table()` is idempotent
(PAY_PER_REQUEST, waiter) and safe to call on every boot.

### moto coverage (tests/test_dynamodb_store.py, 9 tests)

Covered against real DynamoDB API semantics emulated by moto 5: conditional writes (both the
conflict and the retry-success path — a flaky `put_item` spy raises `ConditionalCheckFailedException`
once and the store recovers), Query + pagination shape, waiters. Cases: roundtrip of all five entity
types incl. float/set/datetime/nested-model fields; missing ticket/tenant → `None`; mutator result
returned verbatim; sequential mutators preserving both updates (the batched-tool-call scenario);
**24 concurrent mutators across 8 threads with zero lost updates** (stable across repeated runs);
injected version-conflict retry; retry exhaustion raising instead of losing the write; message
ordering + ticket filter; idempotent `ensure_table`.

Not covered by moto (say it plainly in demos): IAM/encryption/TTL, true eventual consistency
(moto is immediately consistent, so `ConsistentRead` behavior isn't really exercised), throttling
backoff beyond our own loop.

### ⚠️ One thing Agent 1 must do in pyproject.toml

`tests/test_dynamodb_store.py` imports `moto`, which is installed in this worktree's venv but is
**not** in the committed dev extras. Suggested diff:

```toml
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.5",
+   "moto[dynamodb]>=5.0",
]
```

(`boto3` already rides in via strands and the existing `aws` extra — no change needed there.)

## E.2 OTel tracing — `src/handoff/tracing.py`

`configure_tracing()` is the only entry point. `HANDOFF_OTEL` unset/falsy ⇒ returns `None` and the
module has imported nothing beyond stdlib — proven by a subprocess test asserting zero
`opentelemetry.*` modules in `sys.modules`. Flag on ⇒ installs a **global** `TracerProvider`; that is
the entire Strands integration because `strands.telemetry.tracer` calls
`trace_api.get_tracer_provider()` (verified in the installed SDK) and emits agent/tool spans through
it — zero strands-side code needed. Missing SDK ⇒ `UserWarning`, returns `None` (never crashes).
Exporter: tries OTLP gRPC, then OTLP HTTP, then falls back to `ConsoleSpanExporter` with a warning —
so `HANDOFF_OTEL=1 HANDOFF_OTEL_EXPORTER=console` gives visible spans with **no** new installs (the
SDK already ships transitively with strands; only the exporter is an extra). Env: `HANDOFF_OTEL`,
`HANDOFF_OTEL_EXPORTER=otlp|console`, `HANDOFF_OTEL_SERVICE_NAME`, plus the standard
`OTEL_EXPORTER_OTLP_ENDPOINT` honored by the exporter itself.

If you'd rather use Strands' own setup instead of ours, the equivalent is:

```python
from strands.telemetry.tracer import get_tracer  # honors OTEL_EXPORTER_OTLP_ENDPOINT etc.
get_tracer()
```

Suggested optional extra for real OTLP export (your call, pyproject is yours):

```toml
[project.optional-dependencies]
+ otel = ["opentelemetry-exporter-otlp-proto-grpc>=1.25"]
```

## E.3 Channels — `src/handoff/channels/`

`SmsChannel` is a `@runtime_checkable` Protocol with one method: `send(to_phone, body, *,
ticket_id=None, kind="update") -> provider_message_id`. Deliberately transport-shaped: composition,
audience selection, and `store.record_message` stay in the tools layer, so backends never duplicate
the audit trail. Built-ins: `ConsoleSmsChannel` (stdout, offline demos) and `FileSmsChannel`
(thread-safe JSONL outbox at `$HANDOFF_DATA_DIR/sms_outbox.jsonl`). `build_channel()` resolves
`$HANDOFF_SMS_CHANNEL` (default `console`); `register_channel(name, factory)` is the drop-in seam —
the test suite registers a fake `SnsSmsChannel` through exactly the path a real one would take
(`boto3.client("sns").publish(PhoneNumber=..., Message=...)`), with no interface change.

## Proposed integration diffs (Agent 1 applies — I did not touch owned files)

1. **`src/handoff/config.py`** — new fields on `Settings`:

```python
store_backend: str = field(default_factory=lambda: os.getenv("HANDOFF_STORE", "file"))  # file|dynamodb
dynamodb_table: str = field(default_factory=lambda: os.getenv("HANDOFF_DDB_TABLE", "handoff"))
sms_channel: str = field(default_factory=lambda: os.getenv("HANDOFF_SMS_CHANNEL", "console"))
```

2. **`src/handoff/web/app.py`** — `DashboardState.__init__`, store selection + tracing (tracing must
be configured before `CoordinatorAgent`/`BedrockModel` are constructed so spans attach):

```python
-        self.store = FileStore(root=settings.data_dir)
+        if settings.store_backend == "dynamodb":
+            from handoff.store.dynamodb import DynamoDBStore
+
+            self.store = DynamoDBStore(table_name=settings.dynamodb_table)
+            self.store.ensure_table()
+        else:
+            self.store = FileStore(root=settings.data_dir)
+        from handoff.tracing import configure_tracing
+
+        configure_tracing()
```

`demo.py` should stay FileStore (offline by design). `seed_world`/`ensure_table` ordering: seed only
when `not self.store.list_properties()` already handles the empty-table case.

3. **`src/handoff/tools/toolkit.py`** (optional, when real SMS is wanted) — optional channel on
`HandoffTools`; next to each `self.store.record_message(...)` add a best-effort transport send:

```python
         self.tools = HandoffTools(self.store, approval_threshold=settings.approval_threshold)
+        from handoff.channels import build_channel
+
+        self.channel = build_channel(settings.sms_channel)
```

```python
         self.store.record_message(OutboundMessage(...))
+        if self.channel is not None and msg.channel == "sms":
+            self.channel.send(tenant.phone, msg.body, ticket_id=msg.ticket_id, kind=msg.kind)
```

Keep it best-effort (`try/except` log-and-continue) so an SMS outage never blocks coordination.

## Verification

`.venv/bin/python -m pytest tests -q` → **33 passed** (11 baseline + 9 store + 5 tracing + 8 channels).
