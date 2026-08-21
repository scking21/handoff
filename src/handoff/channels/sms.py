"""SMS channel interface plus offline backends (console, JSONL file).

Shaped for a future SnsSmsChannel: send() takes an E.164 phone and a body,
returns the provider message id, and never touches the store — the tools
layer already records OutboundMessages for the audit trail.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class SmsChannel(Protocol):
    def send(self, to_phone: str, body: str, *, ticket_id: str | None = None, kind: str = "update") -> str:
        """Deliver body to to_phone; return a provider message id."""
        ...


class ConsoleSmsChannel:
    """Renders sends to stdout — the demo/offline transport."""

    def send(self, to_phone: str, body: str, *, ticket_id: str | None = None, kind: str = "update") -> str:
        msg_id = f"console_{uuid.uuid4().hex[:12]}"
        scope = f" ticket={ticket_id}" if ticket_id else ""
        print(f"[SMS{scope} kind={kind} to={to_phone}] {body}")
        return msg_id


class FileSmsChannel:
    """Appends one JSON line per send — an inspectable outbox for local runs."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or Path(os.getenv("HANDOFF_DATA_DIR", "data/runtime")) / "sms_outbox.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def send(self, to_phone: str, body: str, *, ticket_id: str | None = None, kind: str = "update") -> str:
        msg_id = f"file_{uuid.uuid4().hex[:12]}"
        record = {
            "id": msg_id,
            "sent_at": datetime.now(UTC).isoformat(),
            "to_phone": to_phone,
            "ticket_id": ticket_id,
            "kind": kind,
            "body": body,
        }
        with self._lock:
            with self.path.open("a", encoding="utf-8") as out:
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
        return msg_id
