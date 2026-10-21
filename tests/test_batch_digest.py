import csv
import io

from fastapi.testclient import TestClient

from app.batch_digest import generate_batch_digest
from app.main import app
from app.tracking_sync import sync_ticket_to_spreadsheet

client = TestClient(app)


def test_generate_batch_digest_with_pending_tickets(tmp_path, monkeypatch):
    test_csv = str(tmp_path / "digest_test.csv")
    monkeypatch.setenv("DIGEST_MANAGER_EMAIL", "ops-lead@company.com")

    sync_ticket_to_spreadsheet(
        {
            "ticket_id": "TCK-B101",
            "customer_name": "Alice Brown",
            "category": "Billing",
            "priority": "normal",
            "amount": 35.50,
            "reason": "Promotional coupon refund",
            "agent": "SupportBot",
        },
        csv_path=test_csv,
    )
    sync_ticket_to_spreadsheet(
        {
            "ticket_id": "TCK-B102",
            "customer_name": "Bob Green",
            "category": "Billing",
            "priority": "high",
            "amount": 120.00,
            "reason": "Duplicate renewal charge",
            "agent": "Sarah",
        },
        csv_path=test_csv,
    )

    digest = generate_batch_digest(csv_path=test_csv)

    assert digest["has_pending"] is True
    assert digest["dispatched"] is True
    assert digest["pending_count"] == 2
    assert digest["recipient"] == "ops-lead@company.com"
    assert "TCK-B101" in digest["body_table"]
    assert "TCK-B102" in digest["body_table"]
    assert "Category" in digest["body_table"]
    assert "Billing" in digest["body_table"]
    assert "<th>Category</th>" in digest["html_body"]
    assert "$35.50" in digest["body_table"]
    assert "$120.00" in digest["body_table"]
    assert "ops_tracking_sheet.csv" in digest["spreadsheet_link"]

    # Verify attached CSV payload is valid
    csv_reader = list(csv.DictReader(io.StringIO(digest["csv_payload"])))
    assert len(csv_reader) == 2
    assert csv_reader[0]["ticket_id"] == "TCK-B101"
    assert csv_reader[1]["ticket_id"] == "TCK-B102"


def test_generate_batch_digest_empty_queue_suppressed(tmp_path):
    empty_csv = str(tmp_path / "empty_tracking.csv")
    digest = generate_batch_digest(csv_path=empty_csv)

    assert digest["has_pending"] is False
    assert digest["dispatched"] is False
    assert digest["pending_count"] == 0
    assert digest["csv_payload"] == ""
    assert "No pending billing approvals" in digest["body_table"]


def test_post_ops_send_digest_endpoint():
    # Sync a ticket first using API
    sync_res = client.post(
        "/ops/sync-ticket",
        json={
            "ticket_id": "TCK-API-DIGEST",
            "customer_name": "Emma Watson",
            "category": "Billing",
            "priority": "normal",
            "amount": 89.99,
            "reason": "Annual subscription review",
            "agent": "OpsAgent",
        },
    )
    assert sync_res.status_code == 200

    digest_res = client.post("/ops/approvals/send-digest")
    assert digest_res.status_code == 200
    data = digest_res.json()
    assert data["has_pending"] is True
    assert data["dispatched"] is True
    assert any("TCK-API-DIGEST" in line for line in data["body_table"].splitlines())


def test_post_ops_send_digest_empty(tmp_path, monkeypatch):
    empty_csv = str(tmp_path / "isolated_empty.csv")
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", empty_csv)

    digest_res = client.post("/ops/approvals/send-digest")
    assert digest_res.status_code == 200
    data = digest_res.json()
    assert data["has_pending"] is False
    assert data["dispatched"] is False
    assert data["pending_count"] == 0


def test_generate_batch_digest_excludes_needs_info_tickets():
    """Spec L39: Tickets marked as needs_info must be excluded from pending approval digests."""
    tickets = [
        {
            "ticket_id": "TCK-P1",
            "category": "Billing",
            "status": "open",
            "amount": 100.0,
            "customer_name": "Active User",
        },
        {
            "ticket_id": "TCK-NI1",
            "category": "Billing",
            "status": "needs_info",
            "amount": 200.0,
            "customer_name": "Needs Info User",
        },
        {
            "ticket_id": "TCK-AP1",
            "category": "Billing",
            "status": "Approved",
            "amount": 300.0,
            "customer_name": "Approved User",
        },
    ]
    digest = generate_batch_digest(tickets=tickets, send_email=False)
    assert digest["has_pending"] is True
    assert digest["pending_count"] == 1
    assert "TCK-P1" in digest["body_table"]
    assert "TCK-NI1" not in digest["body_table"]
    assert "TCK-AP1" not in digest["body_table"]


def test_batch_digest_multi_category_non_urgent():
    tickets = [
        {
            "ticket_id": "TCK-T1",
            "category": "Technical",
            "priority": "normal",
            "amount": 0.0,
            "customer_name": "Tech User",
            "status": "open",
        },
        {
            "ticket_id": "TCK-L1",
            "category": "Login",
            "priority": "high",
            "amount": 0.0,
            "customer_name": "Login User",
            "status": "pending",
        },
        {
            "ticket_id": "TCK-S1",
            "category": "Shipping",
            "priority": "low",
            "amount": 15.0,
            "customer_name": "Ship User",
            "status": "in-progress",
        },
        {
            "ticket_id": "TCK-A1",
            "category": "Account",
            "priority": "normal",
            "amount": 0.0,
            "customer_name": "Account User",
            "status": "open",
        },
        {
            "ticket_id": "TCK-B1",
            "category": "Billing",
            "priority": "normal",
            "amount": 50.0,
            "customer_name": "Bill User",
            "status": "pending",
        },
    ]
    digest = generate_batch_digest(
        tickets=tickets, send_email=False, slot_label="9:00 AM"
    )
    assert digest["has_pending"] is True
    assert digest["pending_count"] == 5
    assert "[Batch Digest - 9:00 AM] 5 Tickets" in digest["subject"]
    assert "Priority" in digest["body_table"]
    assert "<th>Priority</th>" in digest["html_body"]
    assert "TCK-T1" in digest["body_table"]
    assert "TCK-L1" in digest["body_table"]
    assert "TCK-S1" in digest["body_table"]
    assert "TCK-A1" in digest["body_table"]
    assert "TCK-B1" in digest["body_table"]
    assert "-" in digest["body_table"]  # for 0 amount tickets


def test_batch_digest_excludes_urgent_tickets():
    tickets = [
        {
            "ticket_id": "TCK-NORMAL",
            "category": "Technical",
            "priority": "normal",
            "customer_name": "Normal User",
            "status": "open",
        },
        {
            "ticket_id": "TCK-URGENT",
            "category": "Billing",
            "priority": "urgent",
            "customer_name": "Urgent User",
            "status": "open",
        },
        {
            "ticket_id": "TCK-ESC",
            "category": "Login",
            "priority": "high",
            "escalated": "True",
            "customer_name": "Esc User",
            "status": "open",
        },
    ]
    digest = generate_batch_digest(tickets=tickets, send_email=False)
    assert digest["pending_count"] == 1
    assert "TCK-NORMAL" in digest["body_table"]
    assert "TCK-URGENT" not in digest["body_table"]
    assert "TCK-ESC" not in digest["body_table"]


def test_batch_digest_excludes_closed_and_resolved():
    tickets = [
        {
            "ticket_id": "TCK-OPEN",
            "category": "Shipping",
            "priority": "normal",
            "status": "open",
        },
        {
            "ticket_id": "TCK-PENDING",
            "category": "Account",
            "priority": "normal",
            "status": "pending",
        },
        {
            "ticket_id": "TCK-PROG",
            "category": "Technical",
            "priority": "normal",
            "status": "in-progress",
        },
        {
            "ticket_id": "TCK-CLOSED",
            "category": "Billing",
            "priority": "normal",
            "status": "closed",
        },
        {
            "ticket_id": "TCK-RESOLVED",
            "category": "Login",
            "priority": "normal",
            "status": "resolved",
        },
    ]
    digest = generate_batch_digest(tickets=tickets, send_email=False)
    assert digest["pending_count"] == 3
    assert "TCK-OPEN" in digest["body_table"]
    assert "TCK-PENDING" in digest["body_table"]
    assert "TCK-PROG" in digest["body_table"]
    assert "TCK-CLOSED" not in digest["body_table"]
    assert "TCK-RESOLVED" not in digest["body_table"]


def test_batch_digest_time_window_filtering():
    tickets = [
        {
            "ticket_id": "TCK-OVERNIGHT-1",
            "created_at": "2026-10-20 16:30:00",
            "category": "Technical",
            "priority": "normal",
            "status": "open",
        },
        {
            "ticket_id": "TCK-EARLY-2",
            "created_at": "2026-10-21 07:45:00",
            "category": "Login",
            "priority": "high",
            "status": "open",
        },
        {
            "ticket_id": "TCK-MIDDAY-3",
            "created_at": "2026-10-21 11:15:00",
            "category": "Shipping",
            "priority": "normal",
            "status": "open",
        },
        {
            "ticket_id": "TCK-AFTERNOON-4",
            "created_at": "2026-10-21 14:00:00",
            "category": "Account",
            "priority": "low",
            "status": "open",
        },
        {
            "ticket_id": "TCK-LATE-5",
            "created_at": "2026-10-21 17:00:00",
            "category": "Billing",
            "priority": "normal",
            "status": "open",
        },
    ]
    # 9:00 AM slot: 2026-10-20 15:00:00 to 2026-10-21 09:00:00
    digest_9am = generate_batch_digest(
        tickets=tickets,
        start_time="2026-10-20 15:00:00",
        end_time="2026-10-21 09:00:00",
        slot_label="9:00 AM",
        send_email=False,
    )
    assert digest_9am["pending_count"] == 2
    assert "TCK-OVERNIGHT-1" in digest_9am["body_table"]
    assert "TCK-EARLY-2" in digest_9am["body_table"]
    assert "TCK-MIDDAY-3" not in digest_9am["body_table"]
    assert "[Batch Digest - 9:00 AM] 2 Tickets" in digest_9am["subject"]

    # 3:00 PM slot: 2026-10-21 09:00:00 to 2026-10-21 15:00:00
    digest_3pm = generate_batch_digest(
        tickets=tickets,
        start_time="2026-10-21 09:00:00",
        end_time="2026-10-21 15:00:00",
        slot_label="3:00 PM",
        send_email=False,
    )
    assert digest_3pm["pending_count"] == 2
    assert "TCK-MIDDAY-3" in digest_3pm["body_table"]
    assert "TCK-AFTERNOON-4" in digest_3pm["body_table"]
    assert "TCK-OVERNIGHT-1" not in digest_3pm["body_table"]
    assert "TCK-LATE-5" not in digest_3pm["body_table"]
    assert "[Batch Digest - 3:00 PM] 2 Tickets" in digest_3pm["subject"]


def test_post_ops_send_digest_endpoint_with_slot(tmp_path, monkeypatch):
    test_csv = str(tmp_path / "slot_api_test.csv")
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)

    sync_ticket_to_spreadsheet(
        {
            "ticket_id": "TCK-SLOT-9AM",
            "customer_name": "Morning User",
            "category": "Technical",
            "priority": "normal",
            "amount": 0.0,
            "created_at": "2026-10-21 07:30:00",
            "status": "open",
        },
        csv_path=test_csv,
    )

    digest_res = client.post("/ops/approvals/send-digest?slot=9am")
    assert digest_res.status_code == 200
    data = digest_res.json()
    assert "9:00 AM" in data["subject"]
