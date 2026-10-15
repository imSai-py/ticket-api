import pytest

from app.tracking_sync import (
    SpreadsheetLockedError,
    extract_amount,
    extract_operational_reason,
    get_next_ticket_id,
    get_pending_approvals,
    sanitize_cell,
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
    assert "notes" in result
    assert result["notes"] == ""

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
    assert result["notes"] == "Needs amount verification"


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
    assert "notes" in header


def test_update_approval_status_persists_notes(temp_csv):
    ticket = {
        "ticket_id": "TCK-NOTE-01",
        "customer_name": "Diana",
        "category": "Billing",
        "priority": "normal",
        "amount": 50.0,
        "reason": "Adjustment",
    }
    sync_ticket_to_spreadsheet(ticket, csv_path=temp_csv)
    updated = update_approval_status(
        "TCK-NOTE-01", "Approved", notes="Approved by manager", csv_path=temp_csv
    )
    assert updated["notes"] == "Approved by manager"


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


def test_extract_amount_comma_formatted():
    text1 = "Customer disputing $1,250.00 charge on enterprise plan."
    amt1, note1 = extract_amount(text1)
    assert amt1 == 1250.00
    assert note1 == ""

    text2 = "Disputed amount is 10,500.50 USD from annual invoice."
    amt2, note2 = extract_amount(text2)
    assert amt2 == 10500.50
    assert note2 == ""

    text3 = "Refund request for $ 3,000 for canceled contract."
    amt3, note3 = extract_amount(text3)
    assert amt3 == 3000.0
    assert note3 == ""


def test_sanitize_cell_removes_newlines_and_normalizes_whitespace():
    assert sanitize_cell("Line 1\r\nLine 2\tLine 3") == "Line 1 Line 2 Line 3"
    assert sanitize_cell("   Multiple    spaces   ") == "Multiple spaces"
    assert sanitize_cell(None) == ""
    assert sanitize_cell(12345) == "12345"


def test_file_lock_raises_spreadsheet_locked_error(temp_csv, monkeypatch):
    import builtins

    real_open = builtins.open

    def locked_open(file, *args, **kwargs):
        mode = kwargs.get("mode", args[0] if args else "r")
        if "w" in str(mode) and str(file) == temp_csv:
            raise PermissionError("[Errno 13] Permission denied (file locked in Excel)")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", locked_open)

    ticket = {
        "ticket_id": "TCK-LOCK-01",
        "customer_name": "Test User",
        "category": "Billing",
        "priority": "normal",
        "amount": 100.0,
    }
    with pytest.raises(SpreadsheetLockedError) as exc_info:
        sync_ticket_to_spreadsheet(ticket, csv_path=temp_csv)

    assert "currently open in Microsoft Excel" in str(exc_info.value)


def test_sync_ticket_aligns_with_helpdesk_export_new_format(temp_csv):
    """Verify operational tracking spreadsheet aligns with Helpdesk Export New Format."""
    import csv

    ticket = {
        "ticket_id": "TCK-5007",
        "category": "Refunds",
        "priority": "urgent",
        "status": "in_progress",
        "assigned_to": "riya",
        "customer_email": "omar.ali@example.com",
        "labels": "escalated",
        "refund_amount": 480.0,
    }
    synced = sync_ticket_to_spreadsheet(ticket, csv_path=temp_csv)

    # All 9 core helpdesk export columns must be present and correctly populated
    assert synced["ticket_id"] == "TCK-5007"
    assert synced["status"] == "in_progress"
    assert synced["priority"] == "urgent"
    assert synced["category"] == "Refunds"
    assert synced["assigned_to"] == "riya"
    assert synced["customer_email"] == "omar.ali@example.com"
    assert synced["labels"] == "escalated"
    assert synced["refund_amount"] == "480.00"
    assert synced["created_at"] != ""

    # Inspect on-disk CSV header ordering
    with open(temp_csv, mode="r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)

    expected_first_nine = [
        "ticket_id",
        "created_at",
        "status",
        "priority",
        "category",
        "assigned_to",
        "customer_email",
        "labels",
        "refund_amount",
    ]
    assert (
        header[:9] == expected_first_nine
    ), f"Expected {expected_first_nine}, got {header[:9]}"
