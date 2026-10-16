"""Unit and integration tests for real-time helpdesk query ingestion endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Provide a TestClient with an isolated temporary ops tracking sheet."""
    temp_csv = str(tmp_path / "test_ops_tracking.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", temp_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", temp_csv)
    return TestClient(app)


def test_ingest_helpdesk_query_standard(client):
    """Test standard query ingestion populates all 8 columns and returns structured response."""
    payload = {
        "subject": "Cannot log in to web portal",
        "problem": "I keep getting an invalid password error when logging into my account.",
        "customer_email": "alice.smith@example.com",
        "assigned_to": "riya",
        "status": "open",
    }
    resp = client.post("/ops/ingest-helpdesk", json=payload)
    assert resp.status_code == 200, f"Expected 200, got: {resp.text}"
    data = resp.json()

    assert data["status"] == "success"
    assert data["ticket_id"].startswith("TCK-")
    assert data["category"] in ["Login", "Account", "Technical"]
    assert data["priority"] in ["urgent", "high", "normal", "low"]
    assert data["customer_name"] == "Alice Smith"
    assert data["assigned_to"] == "riya"
    assert data["refund_amount"] == 0.0

    # Verify persisted record in spreadsheet
    record = data["record"]
    assert record["ticket_id"] == data["ticket_id"]
    assert record["customer_name"] == "Alice Smith"
    assert record["category"] == data["category"]
    assert record["priority"] == data["priority"]
    assert record["agent"] == "riya"
    assert record["amount"] == "0.00"


def test_ingest_helpdesk_query_extracts_refund_and_escalates(client):
    """Test query mentioning refund amount automatically extracts USD value and escalates if urgent."""
    payload = {
        "subject": "Charged twice for subscription",
        "problem": "I was charged $480.00 twice on invoice #9021. Please issue a refund.",
        "customer_email": "omar.ali@example.com",
        "assigned_to": "sam",
        "labels": "escalated",
    }
    resp = client.post("/ops/ingest-helpdesk", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["refund_amount"] == 480.0
    assert data["priority"] == "urgent"
    assert data["escalated"] is True
    assert data["customer_name"] == "Omar Ali"
    assert data["record"]["amount"] == "480.00"


def test_ingest_helpdesk_query_explicit_ticket_id(client):
    """Test providing a specific helpdesk ticket identifier preserves it."""
    payload = {
        "ticket_id": "TCK-5088",
        "subject": "Shipping delay notification",
        "problem": "My package tracking has not updated in 5 days.",
        "customer_email": "hana.ito@example.com",
        "assigned_to": "lia",
    }
    resp = client.post("/ops/ingest-helpdesk", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticket_id"] == "TCK-5088"
    assert data["record"]["ticket_id"] == "TCK-5088"


def test_ingest_helpdesk_query_validation_error(client):
    """Test that empty subject and empty problem body returns HTTP 422."""
    payload = {
        "subject": "   ",
        "problem": "",
        "customer_email": "test@example.com",
    }
    resp = client.post("/ops/ingest-helpdesk", json=payload)
    assert resp.status_code == 422


def test_get_ingest_helpdesk_status_probe(client):
    """Test GET status probe on /ops/ingest-helpdesk returns HTTP 200 ready status."""
    resp = client.get("/ops/ingest-helpdesk")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["endpoint"] == "/ops/ingest-helpdesk"
    assert data["method"] == "POST"


def test_export_tracking_sheet_csv(client):
    """Test GET /ops/export-tracking-sheet downloads CSV with Help Desk Tracking Sheet filename."""
    resp = client.get("/ops/export-tracking-sheet")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
    assert 'filename="Help Desk Tracking Sheet.csv"' in resp.headers.get(
        "content-disposition", ""
    )
    lines = resp.text.strip().splitlines()
    assert len(lines) >= 1
    assert "ticket_id" in lines[0]
    assert "refund_amount" in lines[0]


def test_ingest_helpdesk_query_auto_escalates_on_urgent_subject(client):
    """Test query with 'Urgent' in subject and $250 refund automatically escalates to manager."""
    payload = {
        "subject": "Urgent: Refund requested for order #9822",
        "problem": "Hello support team, I was charged $250.00 twice on my credit card. Please issue a refund.",
        "customer_email": "sailakshman212005@gmail.com",
    }
    resp = client.post("/ops/ingest-helpdesk", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["priority"] == "urgent"
    assert data["escalated"] is True
    assert data["refund_amount"] == 250.0
    assert "escalated" in data["record"]["labels"].lower()
    assert data["record"]["customer_email"] == "sailakshman212005@gmail.com"


def test_get_tracking_records_and_clear_endpoint(client):
    """Test getting live tracking records and wiping tracking sheet clean."""
    # Ensure newly ingested ticket is present in tracking-records
    res = client.get("/ops/tracking-records")
    assert res.status_code == 200
    records = res.json()
    assert isinstance(records, list)

    # Clear tracking sheet
    clear_res = client.post("/ops/clear-tracking-sheet")
    assert clear_res.status_code == 200
    assert clear_res.json()["status"] == "cleared"

    # Confirm it is empty now
    res_after = client.get("/ops/tracking-records")
    assert res_after.status_code == 200
    assert res_after.json() == []


def test_ingest_helpdesk_query_drops_no_reply_emails(client):
    """Test automated Google security alerts and no-reply messages are cleanly skipped."""
    payload = {
        "subject": "Security alert: Access granted",
        "problem": "Untitled project was granted access to your Google Account.",
        "customer_email": "no-reply@accounts.google.com",
    }
    resp = client.post("/ops/ingest-helpdesk", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "skipped"
    assert data["ticket_id"] == "SKIPPED-SYSTEM"

    # Confirm it was not written to tracking sheet
    records = client.get("/ops/tracking-records").json()
    assert not any(r.get("ticket_id") == "SKIPPED-SYSTEM" for r in records)


def test_ingest_helpdesk_query_routes_unassigned_agent(client):
    """Test that incoming customer query with no agent routes to default lead instead of Unassigned."""
    payload = {
        "subject": "Refund request for defective merchandise",
        "problem": "Please refund $85.00 for my returned item.",
        "customer_email": "customer.john@example.com",
    }
    resp = client.post("/ops/ingest-helpdesk", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["assigned_to"] != "Unassigned"
    assert data["assigned_to"] in ["Sai", "Riya", "Sam", "Ken"]
    assert data["record"]["agent"] in ["Sai", "Riya", "Sam", "Ken"]
