"""Fuzz regressions: malformed public input never 500s or silently misroutes."""

from __future__ import annotations

from fastapi.testclient import TestClient

import handoff.web.app as webapp


def make_client(tmp_path, monkeypatch):
    monkeypatch.setattr(webapp.settings, "data_dir", str(tmp_path / "runtime"))
    monkeypatch.setattr(webapp.settings, "model_provider", "heuristic")
    monkeypatch.setattr(webapp, "state", webapp.DashboardState())
    monkeypatch.setattr(webapp, "limiter", webapp.RateLimiter())
    return TestClient(webapp.app)


def test_unknown_scenario_returns_400_not_random_ticket(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    r = client.post("/tickets/new", data={"scenario": "../../etc/passwd"}, follow_redirects=False)
    assert r.status_code == 400
    r = client.post("/tickets/new", data={"scenario": "<script>x</script>"}, follow_redirects=False)
    assert r.status_code == 400
    # valid scenario still works
    r = client.post("/tickets/new", data={"scenario": "dripping_faucet"}, follow_redirects=False)
    assert r.status_code == 303


def test_garbage_ticket_id_never_500s(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    for path, data in [
        ("/tickets/wo_fake/decision", {"decision": "approve"}),
        ("/tickets/wo_fake/vendor", {"action": "accept"}),
        ("/tickets/wo_fake/verify", {"ok": "true"}),
    ]:
        r = client.post(path, data=data, follow_redirects=False)
        assert r.status_code in (303, 404), f"{path} -> {r.status_code}"


def test_invalid_decision_value_is_ignored_not_applied(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    r = client.post("/tickets/new", data={"scenario": "midnight_flood", "after_hours": "true"},
                    follow_redirects=False)
    assert r.status_code == 303
    tickets = webapp.state.store.list_tickets()
    gated = [t for t in tickets if t.status.value == "awaiting_approval"]
    assert gated, "flood should gate"
    tid = gated[-1].id

    # 'maybe' must not be treated as a reject
    client.post(f"/tickets/{tid}/decision", data={"decision": "maybe"})
    t = webapp.state.store.get_ticket(tid)
    assert t.status.value == "awaiting_approval" and t.approval is None
