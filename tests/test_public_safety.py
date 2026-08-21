"""Public-endpoint abuse tests: rate limiting, capacity cap, XSS safety."""

from __future__ import annotations

from fastapi.testclient import TestClient

import handoff.web.app as webapp


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("HANDOFF_DATA_DIR", str(tmp_path / "runtime"))
    monkeypatch.setattr(webapp.settings, "data_dir", str(tmp_path / "runtime"))
    monkeypatch.setattr(webapp.settings, "model_provider", "heuristic")
    # rebuild module state against the tmp store
    monkeypatch.setattr(webapp, "state", webapp.DashboardState())
    monkeypatch.setattr(webapp, "limiter", webapp.RateLimiter())
    return TestClient(webapp.app)


def test_rate_limit_blocks_flood_of_submissions(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    codes = []
    for _ in range(webapp.RATE_LIMIT + 2):
        r = client.post("/tickets/new", data={"scenario": "dripping_faucet"},
                        headers={"x-forwarded-for": "1.2.3.4"}, follow_redirects=False)
        codes.append(r.status_code)
    assert codes[:webapp.RATE_LIMIT].count(303) == webapp.RATE_LIMIT
    assert 429 in codes[webapp.RATE_LIMIT:], "submissions beyond the limit must be refused"


def test_capacity_cap_refuses_when_demo_full(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    from handoff.domain.models import TicketStatus, WorkOrder

    for i in range(webapp.MAX_OPEN_TICKETS + 1):
        t = WorkOrder(property_id="p", unit="1A", tenant_id="t", raw_request=f"issue {i}")
        t.status = TicketStatus.TRIAGED
        webapp.state.store.put_ticket(t)
    r = client.post("/tickets/new", data={"scenario": "dripping_faucet"}, follow_redirects=False)
    assert r.status_code in (503, 303) and r.status_code != 200


def test_tenant_text_is_html_escaped_on_board(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    r = client.post(
        "/tickets/new",
        data={"scenario": "dripping_faucet"},
        headers={"x-forwarded-for": "9.9.9.9"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    # inject an XSS attempt directly into the store and re-render the board
    tickets = webapp.state.store.list_tickets()
    t = tickets[-1]
    t.raw_request = "<script>alert('xss')</script>"
    webapp.state.store.put_ticket(t)

    board = client.get("/")
    assert "<script>alert" not in board.text
    assert "&lt;script&gt;" in board.text
