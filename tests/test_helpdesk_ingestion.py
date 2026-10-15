"""Tests for helpdesk export ingestion, column mapping, and DD/MM/YYYY date formatting."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app, format_display_date, load_tickets


def test_format_display_date_converts_iso_to_day_month_year():
    assert format_display_date("2026-10-05 13:05") == "05/10/2026"
    assert format_display_date("2026-03-02 08:23") == "02/03/2026"
    assert format_display_date("2026-12-31T23:59:59Z") == "31/12/2026"
    assert format_display_date("05/10/2026") == "05/10/2026"
    assert format_display_date("") is None
    assert format_display_date(None) is None


def test_load_tickets_ingests_helpdesk_export_without_key_error():
    export_path = Path("data/helpdesk_export.csv")
    assert export_path.exists(), "helpdesk_export.csv must exist"

    tickets = load_tickets(export_path)
    assert len(tickets) == 120

    first = tickets[0]
    assert first["ticket_id"] == "TCK-5007"
    assert first["customer_email"] == "omar.ali@example.com"
    assert first["requester_email"] == "omar.ali@example.com"
    assert first["labels"] == "escalated"
    assert first["tags"] == "escalated"
    assert first["assigned_to"] == "riya"
    assert first["refund_amount"] == 480.0
    assert first["resolved_at"] is None
    assert first["created"] is not None
    assert first["resolved"] is None


def test_load_tickets_backward_compatible_with_legacy_sample():
    sample_path = Path("data/tickets_sample.csv")
    tickets = load_tickets(sample_path)
    assert len(tickets) == 60

    first = tickets[0]
    assert first["ticket_id"] == "TCK-1001"
    assert first["resolved_at"] == "2026-03-02 17:23"
    assert first["created"] is not None
    assert first["resolved"] is not None


def test_api_tickets_endpoints_with_helpdesk_export(monkeypatch):
    export_path = Path("data/helpdesk_export.csv")
    monkeypatch.setattr("app.main.TICKETS", load_tickets(export_path))

    client = TestClient(app)

    # 1. Page 1 returns 10 tickets with DD/MM/YYYY dates
    resp = client.get("/tickets?page=1&size=10")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 10

    first = data[0]
    assert first["ticket_id"] == "TCK-5007"
    assert first["created_at"] == "05/10/2026"
    assert first["resolved_at"] is None
    assert first["customer_email"] == "omar.ali@example.com"
    assert first["labels"] == "escalated"
    assert first["assigned_to"] == "riya"
    assert first["refund_amount"] == "480.00"

    # 2. Get specific ticket endpoint
    resp_single = client.get("/tickets/TCK-5039")
    assert resp_single.status_code == 200
    single_data = resp_single.json()
    assert single_data["ticket_id"] == "TCK-5039"
    assert single_data["created_at"] == "05/10/2026"
    assert single_data["resolved_at"] is None
    assert single_data["customer_email"] == "hana.ito@example.com"
    assert single_data["labels"] == "ESCALATED"
    assert single_data["refund_amount"] == "45.00"
