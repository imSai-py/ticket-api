import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.tracking_sync import (
    FIELDNAMES,
    sync_ticket_to_spreadsheet,
    update_approval_status,
)

client = TestClient(app)


@pytest.fixture
def temp_csv(tmp_path):
    return str(tmp_path / "test_review_tracking.csv")


def test_notes_column_in_fieldnames_and_verification_flag(temp_csv):
    """Spec line 48-49 & 52: notes column in schema and Needs amount verification flag."""
    assert "notes" in FIELDNAMES

    ticket = {
        "ticket_id": "TCK-2001",
        "customer_name": "Test User",
        "category": "Billing",
        "priority": "normal",
        "reason": "Unspecified billing issue with no dollar amount",
        "agent": "Mara",
    }
    result = sync_ticket_to_spreadsheet(ticket, csv_path=temp_csv)
    assert result.get("notes") == "Needs amount verification"
    assert result.get("amount") == "0.00"

    # Test update_approval_status preserves/updates notes
    updated = update_approval_status(
        "TCK-2001", "Approved", notes="Approved per policy", csv_path=temp_csv
    )
    assert updated.get("notes") == "Approved per policy"


def test_verification_note_appends_to_existing_notes(temp_csv):
    """Spec line 52: notes appends 'Needs amount verification'."""
    ticket = {
        "ticket_id": "TCK-2003",
        "customer_name": "Test User",
        "category": "Billing",
        "priority": "normal",
        "reason": "Customer inquiry without dollar figure",
        "agent": "Mara",
        "notes": "VIP customer",
    }
    result = sync_ticket_to_spreadsheet(ticket, csv_path=temp_csv)
    assert "VIP customer" in result["notes"]
    assert "Needs amount verification" in result["notes"]


def test_one_click_approval_minimal_html_contract(temp_csv, monkeypatch):
    """Spec line 62: minimal HTML response."""
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", temp_csv)
    sync_ticket_to_spreadsheet(
        {
            "ticket_id": "TCK-2002",
            "customer_name": "Test User",
            "category": "Billing",
            "priority": "normal",
            "amount": "100.00",
            "reason": "Refund request",
            "agent": "Mara",
        },
        csv_path=temp_csv,
    )

    response = client.get("/ops/approvals/TCK-2002/action?status=Approved")
    assert response.status_code == 200
    expected_html = "<html><body><h3>✓ Ticket TCK-2002 marked Approved. You may close this tab.</h3></body></html>"
    assert response.text.strip() == expected_html
