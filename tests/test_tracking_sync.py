import pytest

from app.tracking_sync import (
    extract_amount,
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
    assert result["notes"] == ""

    pending = get_pending_approvals(csv_path=temp_csv)
    assert len(pending) == 1
    assert pending[0]["ticket_id"] == "TCK-1001"


def test_sync_ticket_missing_amount_sets_verification_flag(temp_csv):
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
    assert "Needs amount verification" in result["notes"]


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

    updated = update_approval_status(
        "TCK-1004", "Approved", notes="Approved by ops", csv_path=temp_csv
    )
    assert updated["status"] == "Approved"
    assert updated["notes"] == "Approved by ops"

    pending = get_pending_approvals(csv_path=temp_csv)
    assert len(pending) == 0
