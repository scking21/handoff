# Quality Findings — Stream C (code quality pass)

Branch: `review/quality` @ `f5d1b14` · Reviewer: Stream C · REVIEW-ONLY (no src/tests edits)

**Baseline:** `pytest tests -q` → **9 passed**. Lint: ruff 0.16.4 → **65 findings** (all triaged below).

Priority key: **P0** verified bug / judge-visible failure · **P1** robustness or design smell · **P2** style/lint.

---

## P0 — Verified bugs

### Q1. `scheduler.run_sweep` crashes with ImportError whenever a TRIAGED ticket exists
`src/handoff/scheduler/service.py:32` imports `utcnow` from `handoff.tools.toolkit`, but `utcnow` is defined in `handoff.domain.models`. **Reproduced:** any sweep that reaches the SLA block raises
`ImportError: cannot import name 'utcnow' from 'handoff.tools.toolkit'`.
Inside `SchedulerService._loop` it's swallowed into history (`sweep error: ...`) so SLA enforcement silently never runs; via the dashboard `/sweep` route (`tick_once` → `run_sweep`) it's an unhandled 500. No test covers `run_sweep`, which is why 9/9 still pass.

```diff
--- a/src/handoff/scheduler/service.py
+++ b/src/handoff/scheduler/service.py
@@
-from handoff.domain.models import TicketStatus, Urgency
+from handoff.domain.models import TicketStatus, utcnow
@@
         if t.status == TicketStatus.TRIAGED and t.urgency and t.created_at:
             deadline = sla_deadline(t.created_at, t.urgency)
-            from handoff.tools.toolkit import utcnow
-
             if utcnow() > deadline:
```
(This also resolves two of the six F401s: unused `Callable`, unused `Urgency`.)

### Q2. `nightly_sweep` computes approval age with clock-hour modulo, not elapsed time
`src/handoff/workflow/engine.py:210`: `(t.updated_at.hour - t.created_at.hour) % 24` compares *hours-of-day*, not duration. A request created Mon 10:00 and still pending Thu 11:00 reads as "1 hour old" and never triggers the ≥12h reminder.

```diff
--- a/src/handoff/workflow/engine.py
+++ b/src/handoff/workflow/engine.py
@@
         elif t.status == TicketStatus.AWAITING_APPROVAL:
-            age_hours = (t.updated_at.hour - t.created_at.hour) % 24
+            age_hours = (t.updated_at - t.created_at).total_seconds() / 3600
```

### Q3. Result-string protocol misclassifies failures — and `REPLAYED` means opposite things at the two call sites
Tools return human-readable strings; the engine sniffs substrings.
- `_dispatch` (engine.py:139): only `"REPLAYED"` is special. A `"ERROR: no vendor …"` result falls through and the tenant is told *"Good news — we've assigned a vendor"* for a dispatch that never happened.
- `vendor_response` (engine.py:164): `if "REPLAYED" not in res: return REROUTED` — a replayed offer to an alternate (crash-retry after a prior successful dispatch) is treated as *failure* and the loop keeps offering to further vendors down the bench, breaching exactly-once intent; meanwhile an `ERROR` result counts as a successful reroute.

```diff
--- a/src/handoff/workflow/engine.py
+++ b/src/handoff/workflow/engine.py
@@
 def _dispatch(tools: HandoffTools, ticket_id: str, choice: VendorChoice) -> str:
     t = _must(tools, ticket_id)
     scope = f"{t.category.value if t.category else 'general'} repair: {t.raw_request[:100]}"
     result = tools.dispatch_work_order(ticket_id, choice.vendor_id, scope, choice.estimated_cost, idem_key=f"{t.id}:dispatch:{choice.vendor_id}")
+    if result.startswith("ERROR"):
+        return result
     if "REPLAYED" in result:
         return result
@@
     for alt in alternates or []:
         res = tools.dispatch_work_order(
             t.id, alt, t.authorized_scope, t.authorized_cost or 0, idem_key=f"{t.id}:dispatch:{alt}"
         )
-        if "REPLAYED" not in res:
-            return f"REROUTED: {alt}"
+        if res.startswith("ERROR"):
+            continue  # bench entry invalid; try the next alternate
+        return f"REROUTED: {alt}"  # fresh dispatch or replay both mean: routed
```
(Longer term: have tools raise or return typed results instead of prose-parsing — noted, not diffed.)

---

## P1 — Design / robustness

### Q4. `select_vendor` accepts `category` and ignores it
engine.py:76 — the signature promises trade-aware ranking; `score()` never touches it. Second developer assumes skill-fit scoring happens here (it happens implicitly upstream via `list_vendors(trade)`). Remove the param, or actually use it (e.g., certification match bonus).

```diff
-def select_vendor(candidates: list[dict], category: Trade, urgency: Urgency) -> VendorChoice | None:
+def select_vendor(candidates: list[dict], urgency: Urgency) -> VendorChoice | None:
```
Update the 7 call sites: `pipeline.py:31` and `tests/test_workflow.py:40,62,82,104,121,149`.

### Q5. `escalate_to_human` breaks the module's own idempotency contract
toolkit.py docstring: *"Every side-effecting action is idempotent"* — escalation has no idem guard, re-increments `stall_count`, and spams the PM outbox on retries (e.g., `apply_triage` replayed at low confidence).

```diff
--- a/src/handoff/tools/toolkit.py
+++ b/src/handoff/tools/toolkit.py
@@
-    def escalate_to_human(self, ticket_id: str, reason: str) -> str:
+    def escalate_to_human(self, ticket_id: str, reason: str, idem_key: str = "") -> str:
         """Park a ticket in the human queue: low triage confidence, repeated
         failure, invoice discrepancy. Escalation is a capability, not an error."""
         t = self.store.get_ticket(ticket_id)
         if not t:
             return f"ERROR: no ticket {ticket_id}"
+        if idem_key:
+            replayed = self._check_idem(t, idem_key)
+            if replayed:
+                return replayed
         t.status = TicketStatus.EXCEPTION
```
Back-compat: optional key, callers opt in (`f"{t.id}:escalate:{reason[:20]}"` style).

### Q6. Invoice discrepancy is detected but never recorded; three model fields have no writer
`complete_and_verify` escalates on >110% but leaves `WorkOrder.invoice_discrepancy` empty — the field exists precisely for this dispute trail. Related dead weight: `scheduled_window`, `completion_photos` are never written anywhere; `Actor.SYSTEM` never used.

```diff
--- a/src/handoff/workflow/engine.py
+++ b/src/handoff/workflow/engine.py
@@
     authorized = t.authorized_cost or 0
     if invoice_amount > authorized * 1.1:  # >10% over authorization is a discrepancy
+        t.invoice_discrepancy = f"${invoice_amount} exceeds authorized ${authorized}"
+        tools.store.put_ticket(t)
         return tools.escalate_to_human(
```
Either wire up or delete `scheduled_window` / `completion_photos` / `Actor.SYSTEM`.

### Q7. Engine transitions have no status preconditions
Only `resolve_approval` guards status. `complete_and_verify` happily runs from `INTAKE` (undispatched ticket → CLOSED), `vendor_response(accept=True)` schedules anything. One guard pattern applied consistently:

```diff
 def complete_and_verify(tools: HandoffTools, ticket_id: str, notes: str, parts: list[str], invoice_amount: int) -> str:
     t = _must(tools, ticket_id)
+    if t.status not in (TicketStatus.DISPATCHED, TicketStatus.SCHEDULED):
+        return f"IGNORED: ticket {t.id} not open for closeout (status={t.status.value})"
```

### Q8. `resolve_approval`: unvalidated decision string + needless function-local import
toolkit.py:146 — any string becomes `ApprovalDecision.decision`; the lazy `from handoff.domain.models import ApprovalDecision` has no circular-import justification.

```diff
--- a/src/handoff/tools/toolkit.py
+++ b/src/handoff/tools/toolkit.py
@@
-from handoff.domain.models import Actor, OutboundMessage, Quote, TicketStatus, Trade, Urgency, WorkOrder
+from handoff.domain.models import (
+    Actor,
+    ApprovalDecision,
+    OutboundMessage,
+    Quote,
+    TicketStatus,
+    Trade,
+    Urgency,
+    WorkOrder,
+)
@@
         if t.status != TicketStatus.AWAITING_APPROVAL:
             return f"IGNORED: ticket {t.id} not awaiting approval (status={t.status.value})"
-        from handoff.domain.models import ApprovalDecision
-
+        if decision not in ("approve", "reject"):
+            return f"ERROR: decision must be 'approve' or 'reject', got {decision!r}"
         t.approval = ApprovalDecision(decision=decision, note=note)
```

### Q9. Inconsistent tool error protocol: `request_quote` raises where siblings return strings
toolkit.py:111 — `Urgency(urgency)` raises ValueError/KeyError on bad input straight into the agent loop, while every other tool returns `"ERROR: …"`. Guard first:

```diff
         v = next((x for x in self.store.list_vendors() if x.id == vendor_id), None)
         if not v:
             return f"ERROR: no vendor {vendor_id}"
+        if urgency not in URGENCY_MULTIPLIER:
+            return f"ERROR: unknown urgency {urgency!r}"
```

### Q10. Unused `strands.tools.tool` import hints at a lost `@tool` decoration
toolkit.py:15 imports `tool`, decorates nothing; tools are registered as bound methods via `HandoffTools.all()`. If plain-callable registration is intentional (it appears to work), delete the import — but confirm the Strands agent path once, since a dropped decorator would change schema generation. Docstring-worthy either way: one line in `all()` saying how these bind to a Strands agent would stop the second developer wondering.

### Readability flags (brief item 2 — docstrings/naming, no behavior change)
- `select_vendor.score()` magic weights (`12.0 / 0.15 / 3.0 / 5.0 / 0.05`) and `request_quote`'s ETA formula (`drive_minutes / 30 * 2 + …`) need one line each explaining intent — judges read elegance, and these read like tuning folklore.
- `HandoffTools.all()` shadows builtin `all`; `as_list()` or `registry()` reads cleaner.
- `intake_request(store, tools, payload)` breaks the module's `tools`-first convention and leaves `store` untyped; annotate `store: Store`.
- Tenant-facing typo, engine.py:144: *"they're confirming a arrival window"* → **an arrival window**.

---

## Lint triage (ruff 0.16.4, all 65 findings)

| Rule | Count | Disposition |
|---|---|---|
| E501 line-too-long | 49 | Wrap code/f-string lines; for pure-string lines use targeted `# noqa: E501`. The 12 worst (>120 chars) are toolkit.py:73,84 · engine.py:138 · app.py:85 · decisions.py:30,69,70 · generate.py:76,111 · test_workflow.py:47. Representative wrap: |
| F401 unused-import | 6 | Fix via Q1/Q8/Q10 diffs + drop `Actor` in `data/synth/generate.py:13` and `store/base.py:16`. |
| I001 unsorted-imports | 4 | `decisions.py:104`, `toolkit.py:9`, `web/app.py:9,46` — `ruff check --fix --select I001`. |
| UP042 str-enum | 4 | `Trade/Urgency/TicketStatus/Actor` → `enum.StrEnum` (floor is py3.12, safe with Pydantic; `.value` unchanged): |
| B905 zip-strict | 1 | tests/test_evals.py:22 — lengths are provably equal: `zip(report["rows"], SCENARIOS, strict=True)`. |
| F841 unused-var | 1 | web/app.py:156 — `state.scheduler.tick_once()` bare call. |

```diff
--- a/src/handoff/domain/models.py
+++ b/src/handoff/domain/models.py
@@
-class Trade(str, enum.Enum):
+class Trade(enum.StrEnum):
```
(same for `Urgency`, `TicketStatus`, `Actor`; delete now-unneeded `str(...)` casts opportunistically)

```diff
--- a/src/handoff/web/app.py
+++ b/src/handoff/web/app.py
@@
 def sweep():
-    actions = state.scheduler.tick_once()
+    state.scheduler.tick_once()
     return RedirectResponse("/", status_code=303)
```

Note on the repo's "no comments unless asked" claim: models.py:36-37, engine.py:34,110-111, config.py:11, models.py:169 already carry inline comments. Either honor the claim or drop it from the pitch — inconsistency is what a hostile judge notices.

## Dead-code answers (explicitly asked)
- `sla_deadline` is **not dead**: used by `scheduler/service.py:31` (once Q1 lands, actually reachable).
- `WorkOrder` import in engine.py is used (annotations + constructor). Real unused imports are the six F401s above.
- Dead states: `IN_PROGRESS`, `DECLINED_BY_TENANT` are defined in `TicketStatus` but no code path ever assigns them. Dead fields: `scheduled_window`, `completion_photos` (see Q6). Delete or wire.

---

## Test coverage gaps (brief item 3)

State machine today: INTAKE→TRIAGED→{AWAITING_APPROVAL⇄DISPATCHED}→SCHEDULED→COMPLETED→CLOSED, side exits →EXCEPTION. Tested transitions: apply_triage (both exits), gate→AWAITING_APPROVAL, resume→DISPATCHED (approve), accept→SCHEDULED, decline→reroute, closeout→CLOSED, invoice>110%→EXCEPTION, low-conf→EXCEPTION, sweep nudges/stall-escalation.

Untested, concretely:

| # | Gap | Where |
|---|---|---|
| G1 | PM **rejection** path: `resolve_approval(decision="reject")` → EXCEPTION | toolkit.py:156 |
| G2 | `resume_after_approval` defensive branch: approved but `pending_vendor_id` missing → ESCALATED | engine.py:129-130 |
| G3 | `resolve_approval` IGNORED branch (ticket not awaiting approval) | toolkit.py:151 |
| G4 | All-vendors-declined → ESCALATED deterministically (current test asserts `startswith(("REROUTED","ESCALATED"))`, data-dependent) | engine.py:166 |
| G5 | Sweep reminder branch for approvals pending ≥12h (currently unreachable due to Q2 math bug) | engine.py:209-212 |
| G6 | `run_sweep` SLA-breach escalation — zero coverage, and broken per Q1 | scheduler/service.py:29-37 |
| G7 | Closeout precondition abuse: `complete_and_verify` from INTAKE/TRIAGED closes an undispatched ticket (bug per Q7 + missing negative test) | engine.py:169 |
| G8 | VERIFIED transition — only writer is the web verify route; zero web/route tests exist | web/app.py:148 |
| G9 | Dead states `IN_PROGRESS`, `DECLINED_BY_TENANT`: no producer anywhere — decide: wire or remove | domain/models.py:47,52 |
| G10 | `select_vendor([])` → None and pipeline's "no vendor covers trade" escalation branch | engine.py:78, pipeline.py:32 |

Cheapest high-value additions: a `run_sweep` test with one TRIAGED ticket (would have caught Q1), a rejection-path test (G1), and a closeout-from-INTAKE negative test (G7).

---

## pyproject.toml hygiene (brief item 4)

1. **Floor-only pins on fast-moving deps.** Installed-and-verified versions differ wildly from floors (`strands-agents>=0.2` vs installed **1.52.0** — major-version drift across a Strands API that changed shape). Raise floors to the verified set and cap the volatile ones:

```diff
--- a/pyproject.toml
+++ b/pyproject.toml
@@
 dependencies = [
-    "strands-agents>=0.2",
-    "strands-agents-tools>=0.2",
-    "pydantic>=2.7",
-    "fastapi>=0.111",
-    "uvicorn[standard]>=0.30",
-    "jinja2>=3.1",
-    "python-multipart>=0.0.9",
-    "faker>=25.0",
+    "strands-agents>=1.52,<2",
+    "strands-agents-tools>=0.8,<0.9",
+    "pydantic>=2.13,<3",
+    "fastapi>=0.141,<1",
+    "uvicorn[standard]>=0.52,<1",
+    "jinja2>=3.1,<4",
+    "python-multipart>=0.0.20",
+    "faker>=25",
 ]
```
(Better still: commit a lockfile so judges reproduce the demo exactly.)

2. **`pytest-asyncio` is configured but unused** — `asyncio_mode = "auto"` with zero async tests. Drop the dev dep and the ini option, or keep deliberately if web-route async tests are coming (coordinate with other streams).

3. **Extras are correct** (`aws` → boto3 matches the Bedrock path; nothing missing), but consider `[project.scripts]` — `demo`, `evals`, and `deploy` each ship a `main()` behind `__main__` blocks:

```diff
+[project.scripts]
+handoff-demo = "handoff.demo:main"
+handoff-evals = "handoff.evals.triage_evals:main"
```

4. `requires-python = ">=3.12"` vs target-version py312 is consistent (UP042's `StrEnum` needs only 3.11+); README's "Python 3.13" is fine as the tested floor. No change required.

---

## Suggested application order
Q1 + Q2 + Q3 (correctness) → lint auto-fixes (`ruff check --fix`) + UP042/B905/F841 → Q4-Q9 → coverage G1/G6/G7 → pyproject pins.
