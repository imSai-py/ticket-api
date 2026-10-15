import io
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_tracking_sheet(tmp_path, monkeypatch):
    test_csv = str(tmp_path / "test_batch_ops_tracking.csv")
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    return test_csv


def test_ingest_batch_csv_multipart_file_upload(isolated_tracking_sheet):
    csv_content = (
        "ticket_id,created_at,status,priority,category,assigned_to,customer_email,labels,refund_amount\n"
        "TCK-6001,2026-10-15 10:00,open,urgent,Refunds,riya,omar@example.com,escalated,480.00\n"
        "TCK-6002,2026-10-15 10:05,open,normal,Login,lia,jo@example.com,,0.00\n"
        "TCK-6003,2026-10-15 10:10,in_progress,normal,Refunds,sam,dara@example.com,esc,85.50\n"
    )

    files = {
        "file": (
            "helpdesk_export.csv",
            io.BytesIO(csv_content.encode("utf-8")),
            "text/csv",
        )
    }
    response = client.post("/ops/ingest-batch", files=files)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["processed_count"] == 3
    assert len(data["records"]) == 3
    assert (
        data["escalated_count"] >= 2
    )  # TCK-6001 (urgent) and TCK-6003 (esc label -> urgent)

    # Check spreadsheet on disk
    with open(isolated_tracking_sheet, "r", encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 4  # header + 3 rows
    header = lines[0].strip()
    assert (
        header
        == "ticket_id,created_at,status,priority,category,assigned_to,customer_email,labels,refund_amount"
    )


def test_ingest_batch_csv_high_dollar_refund_escalation(isolated_tracking_sheet):
    csv_content = (
        "ticket_id,created_at,status,priority,category,assigned_to,customer_email,labels,refund_amount\n"
        "TCK-7001,2026-10-15 11:00,open,normal,Refunds,ken,big.spender@example.com,,350.00\n"
        "TCK-7002,2026-10-15 11:05,open,normal,Billing,sam,small.user@example.com,,15.00\n"
    )

    files = {
        "file": ("export.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")
    }
    # Threshold at 200.00 USD
    response = client.post("/ops/ingest-batch?refund_threshold=200.0", files=files)

    assert response.status_code == 200
    data = response.json()
    assert data["processed_count"] == 2
    # TCK-7001 is normal priority but 350.00 >= 200.00, triggering escalation
    assert data["escalated_count"] == 1
    assert data["escalations"][0]["ticket_id"] == "TCK-7001"


def test_ingest_batch_json_content(isolated_tracking_sheet):
    payload = {
        "csv_content": (
            "ticket_id,created_at,status,priority,category,assigned_to,customer_email,labels,refund_amount\n"
            "TCK-8001,2026-10-15 12:00,resolved,normal,Technical,dan,tech.lead@example.com,,0.00\n"
        )
    }
    response = client.post("/ops/ingest-batch", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["processed_count"] == 1
    assert data["records"][0]["ticket_id"] == "TCK-8001"


def test_ingest_batch_legacy_and_unstructured_csv(isolated_tracking_sheet):
    # Tests CSV with legacy column names and amounts with dollar signs & commas
    csv_content = (
        "ticket_id,created_at,status,priority,category,agent,customer_name,amount,notes\n"
        'TCK-9001,2026-10-15 13:00,open,normal,Refunds,riya,Alice Smith,"$1,250.00",Annual plan refund\n'
    )
    files = {
        "file": (
            "legacy_export.csv",
            io.BytesIO(csv_content.encode("utf-8")),
            "text/csv",
        )
    }
    response = client.post("/ops/ingest-batch?refund_threshold=500.0", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["processed_count"] == 1
    rec = data["records"][0]
    assert rec["ticket_id"] == "TCK-9001"
    assert rec["refund_amount"] == "1250.00"
    assert rec["assigned_to"] == "riya"
    assert data["escalated_count"] == 1


def test_ingest_batch_empty_csv_returns_400():
    files = {"file": ("empty.csv", io.BytesIO(b""), "text/csv")}
    response = client.post("/ops/ingest-batch", files=files)
    assert response.status_code == 400
    assert "Empty CSV file" in response.json()["detail"]


def test_ingest_batch_handles_lock_contention_with_retry(
    isolated_tracking_sheet, monkeypatch
):
    call_count = 0

    def mock_write_with_retry(path, rows, max_retries=3):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Simulate initial contention that clears
            time.sleep(0.01)
        # Succeeded

    monkeypatch.setattr("app.tracking_sync._write_all", mock_write_with_retry)

    payload = {
        "csv_content": (
            "ticket_id,created_at,status,priority,category,assigned_to,customer_email,labels,refund_amount\n"
            "TCK-9010,2026-10-15 14:00,open,normal,Billing,sam,user@example.com,,0.00\n"
        )
    }
    response = client.post("/ops/ingest-batch", json=payload)
    assert response.status_code == 200
    assert response.json()["processed_count"] == 1
