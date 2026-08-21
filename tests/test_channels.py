"""Channel abstraction: narrow transport interface, offline backends, registry
that lets an SNS backend drop in later without touching the interface."""

from __future__ import annotations

import json
import threading

import pytest

from handoff.channels import (
    ConsoleSmsChannel,
    FileSmsChannel,
    SmsChannel,
    available_channels,
    build_channel,
    register_channel,
)


def test_both_backends_satisfy_the_protocol():
    assert isinstance(ConsoleSmsChannel(), SmsChannel)
    assert isinstance(FileSmsChannel(path="out.jsonl"), SmsChannel)


def test_console_channel_prints_and_returns_id(capsys):
    msg_id = ConsoleSmsChannel().send("+15551230000", "window Tue 9-11", ticket_id="wo_1", kind="schedule_offer")
    assert msg_id.startswith("console_")
    out = capsys.readouterr().out
    assert "[SMS ticket=wo_1 kind=schedule_offer to=+15551230000] window Tue 9-11" in out


def test_file_channel_appends_jsonl_records(tmp_path):
    path = tmp_path / "sms_outbox.jsonl"
    ch = FileSmsChannel(path=path)
    id1 = ch.send("+15551230000", "ack: plumber coming", ticket_id="wo_1", kind="ack")
    id2 = ch.send("+15551231111", "offer $180", ticket_id="wo_1", kind="dispatch_offer")

    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert [r["id"] for r in lines] == [id1, id2]
    assert lines[0]["body"] == "ack: plumber coming"
    assert lines[0]["kind"] == "ack"
    assert lines[1]["to_phone"] == "+15551231111"
    assert all(r["sent_at"] for r in lines)


def test_file_channel_is_thread_safe(tmp_path):
    path = tmp_path / "sms_outbox.jsonl"
    ch = FileSmsChannel(path=path)
    ids = []
    lock = threading.Lock()

    def blast(n: int) -> None:
        for i in range(5):
            msg_id = ch.send(f"+1555000000{n}", f"msg {i}", ticket_id="wo_x")
            with lock:
                ids.append(msg_id)

    threads = [threading.Thread(target=blast, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    lines = path.read_text().splitlines()
    assert len(lines) == 40
    assert len({json.loads(line)["id"] for line in lines}) == 40
    assert len(set(ids)) == 40


def test_build_channel_defaults_to_console(monkeypatch):
    monkeypatch.delenv("HANDOFF_SMS_CHANNEL", raising=False)
    assert isinstance(build_channel(), ConsoleSmsChannel)
    assert isinstance(build_channel("file", path="out.jsonl"), FileSmsChannel)


def test_unknown_channel_names_the_available_backends(monkeypatch):
    monkeypatch.delenv("HANDOFF_SMS_CHANNEL", raising=False)
    with pytest.raises(ValueError, match="console"):
        build_channel("pager_duty")


def test_custom_backend_registers_without_interface_change(monkeypatch):
    class SnsSmsChannel:
        def __init__(self):
            self.sent = []

        def send(self, to_phone, body, *, ticket_id=None, kind="update"):
            self.sent.append((to_phone, body))
            return "sns_123"

    sns = SnsSmsChannel()
    register_channel("sns", lambda: sns)
    monkeypatch.setenv("HANDOFF_SMS_CHANNEL", "sns")

    channel = build_channel()
    assert isinstance(channel, SnsSmsChannel)
    assert isinstance(channel, SmsChannel)
    assert channel.send("+15551234567", "hi", ticket_id="wo_9") == "sns_123"
    assert channel.sent == [("+15551234567", "hi")]
    assert "sns" in available_channels()


def test_env_selects_backend(monkeypatch, tmp_path):
    monkeypatch.setenv("HANDOFF_SMS_CHANNEL", "file")
    ch = build_channel(path=tmp_path / "o.jsonl")
    assert isinstance(ch, FileSmsChannel)
