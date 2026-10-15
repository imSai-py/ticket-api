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
