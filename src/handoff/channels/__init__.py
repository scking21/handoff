"""Tenant-facing channel transports.

The interface is deliberately transport-shaped only: given a phone number and
a body, deliver it and return a provider message id. Message composition,
audience selection, and store recording stay in the tools layer, so an SNS
backend drops in later with zero interface change.
"""

from __future__ import annotations

import os
from typing import Callable, Protocol, runtime_checkable

from handoff.channels.sms import ConsoleSmsChannel, FileSmsChannel, SmsChannel

_BACKENDS: dict[str, Callable[[], SmsChannel]] = {
    "console": ConsoleSmsChannel,
    "file": FileSmsChannel,
}


def register_channel(name: str, factory: Callable[[], SmsChannel]) -> None:
    """Add a backend (e.g. an SnsSmsChannel) without touching built-ins."""
    _BACKENDS[name] = factory


def available_channels() -> list[str]:
    return sorted(_BACKENDS)


def build_channel(name: str | None = None, **kwargs) -> SmsChannel:
    """Instantiate a backend by name; defaults to $HANDOFF_SMS_CHANNEL or console."""
    chosen = (name or os.getenv("HANDOFF_SMS_CHANNEL", "") or "console").strip().lower()
    if chosen not in _BACKENDS:
        raise ValueError(f"unknown SMS channel {chosen!r}; available: {', '.join(sorted(_BACKENDS))}")
    return _BACKENDS[chosen](**kwargs)
