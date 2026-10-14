import pytest

from app.tracking_sync import (
    extract_amount,
    extract_operational_reason,
    get_next_ticket_id,
    get_pending_approvals,
    sync_ticket_to_spreadsheet,
    update_approval_status,
)


@pytest.fixture
def temp_csv(tmp_path):
    return str(tmp_path / "test_tracking.csv")


def test_extract_amount_present():
    text = "Please refund my subscription charge of $49.99 immediately."
    amount, note = extract_amount(text)
    assert amount == 49.99
    assert note == ""


def test_extract_amount_missing():
    text = "I was billed twice but I cannot find my receipt."
    amount, note = extract_amount(text)
    assert amount == 0.0
    assert note == "Needs amount verification"


def test_sync_ticket_creates_and_queries_pending(temp_csv):
    ticket = {
        "ticket_id": "TCK-1001",
        "customer_name": "Jane Doe",
        "category": "Billing",
        "priority": "normal",
        "reason": "Charged $75.00 for service renewal",
        "agent": "Alex",
    }
    result = sync_ticket_to_spreadsheet(ticket, csv_path=temp_csv)
    assert result["ticket_id"] == "TCK-1001"
    assert result["status"] == "Pending"
    assert float(result["amount"]) == 75.00
    assert "notes" not in result

    pending = get_pending_approvals(csv_path=temp_csv)
    assert len(pending) == 1
    assert pending[0]["ticket_id"] == "TCK-1001"


def test_sync_ticket_missing_amount_defaults_to_zero(temp_csv):
    ticket = {
        "ticket_id": "TCK-1002",
        "customer_name": "Bob Smith",
        "category": "Billing",
        "priority": "urgent",
        "reason": "Account overcharged without receipt",
        "agent": "Alex",
    }
    result = sync_ticket_to_spreadsheet(ticket, csv_path=temp_csv)
    assert float(result["amount"]) == 0.00
    assert "notes" not in result


def test_sync_ticket_updates_existing_record(temp_csv):
    ticket = {
        "ticket_id": "TCK-1003",
        "customer_name": "Alice",
        "category": "Billing",
        "priority": "normal",
        "reason": "Initial query",
        "agent": "Dan",
    }
    sync_ticket_to_spreadsheet(ticket, csv_path=temp_csv)

    updated_ticket = {
        "ticket_id": "TCK-1003",
        "customer_name": "Alice Cooper",
        "category": "Billing",
        "priority": "urgent",
        "reason": "Update with $30.00 dispute",
        "agent": "Dan",
    }
    result = sync_ticket_to_spreadsheet(updated_ticket, csv_path=temp_csv)
    assert result["customer_name"] == "Alice Cooper"
    assert float(result["amount"]) == 30.00

    pending = get_pending_approvals(csv_path=temp_csv)
    assert len(pending) == 1
    assert pending[0]["customer_name"] == "Alice Cooper"


def test_update_approval_status(temp_csv):
    ticket = {
        "ticket_id": "TCK-1004",
        "customer_name": "Charlie",
        "category": "Billing",
        "priority": "normal",
        "reason": "Refund requested $20.00",
        "agent": "Dan",
    }
    sync_ticket_to_spreadsheet(ticket, csv_path=temp_csv)

    updated = update_approval_status("TCK-1004", "Approved", csv_path=temp_csv)
    assert updated["status"] == "Approved"

    pending = get_pending_approvals(csv_path=temp_csv)
    assert len(pending) == 0


def test_sync_ticket_preserves_existing_approval_status(temp_csv):
    ticket = {
        "ticket_id": "TCK-STATUS-01",
        "customer_name": "Test Customer",
        "category": "Billing",
        "priority": "normal",
        "amount": 100.0,
        "reason": "Initial query",
    }
    sync_ticket_to_spreadsheet(ticket, csv_path=temp_csv)
    update_approval_status("TCK-STATUS-01", "Approved", csv_path=temp_csv)

    # Re-sync without explicit status in payload
    update_payload = {
        "ticket_id": "TCK-STATUS-01",
        "customer_name": "Test Customer Updated",
        "category": "Billing",
        "priority": "normal",
        "reason": "Customer updated details",
    }
    result = sync_ticket_to_spreadsheet(update_payload, csv_path=temp_csv)
    assert result["status"] == "Approved"


def test_sync_ticket_sanitizes_newlines_in_cells(temp_csv):
    ticket = {
        "ticket_id": "TCK-MULTI-01",
        "customer_name": "Acme\nCorp",
        "category": "Billing",
        "priority": "normal",
        "amount": 100.0,
        "reason": "Line 1\nLine 2\n   Line 3",
    }
    result = sync_ticket_to_spreadsheet(ticket, csv_path=temp_csv)
    assert result["customer_name"] == "Acme Corp"
    assert result["reason"] == "Line 1 Line 2 Line 3"

    with open(temp_csv, mode="r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    # Exactly header + 1 row
    assert len(lines) == 2
    header = lines[0].split(",")
    assert "notes" not in header


def test_get_next_ticket_id_sequential(temp_csv):
    ticket_id = get_next_ticket_id(csv_path=temp_csv)
    assert ticket_id.startswith("TCK-")
    num = int(ticket_id.split("-")[1])
    assert num >= 1020


def test_extract_operational_reason():
    reason = extract_operational_reason(
        "Dispute on annual subscription renewal",
        "Hi, I was billed $250.00 twice on my credit card for invoice #9401. Please issue a refund for the duplicate charge.",
    )
    assert "Duplicate charge refund" in reason
    assert "9401" in reason
