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
