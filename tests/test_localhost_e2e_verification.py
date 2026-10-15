import io

from fastapi.testclient import TestClient

from app.main import app
from app.tracking_sync import FIELDNAMES

client = TestClient(app)

TARGET_9_COLUMNS = [
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


def test_e2e_system_health():
    """Verify system diagnostics and all subsystem connections."""
    assert list(FIELDNAMES) == TARGET_9_COLUMNS
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["storage"] == "accessible"
    assert data["tickets_data"] == "loaded"
    assert data["knowledge_base"] == "indexed"


def test_e2e_single_query_ingestion_and_spreadsheet_sync(tmp_path, monkeypatch):
    """Verify single query ingestion parses, classifies, and syncs 9-column record."""
    test_csv = str(tmp_path / "e2e_ops_sheet.csv")
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)

    payload = {
        "subject": "Charged twice on invoice #INV-9021",
        "problem": "I was billed $480.00 twice for my annual subscription. Please refund the duplicate $480.00 charge immediately.",
        "customer_email": "omar.ali@example.com",
        "customer_name": "Omar Ali",
        "assigned_to": "Riya",
        "labels": "escalated",
        "refund_amount": 480.0,
    }

    res = client.post("/ops/ingest-helpdesk", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert body["ticket_id"].startswith("TCK-")
    assert body["category"] in ["Refunds", "Billing"]
    assert body["priority"] == "urgent"
    assert body["refund_amount"] == 480.0
    assert body["escalated"] is True
    assert len(body["suggested_reply"]) > 10

    # Verify on-disk CSV header strictly matches the 9 columns
    with open(test_csv, "r", encoding="utf-8") as f:
        header_line = f.readline().strip()
        record_line = f.readline().strip()

    assert header_line.split(",") == TARGET_9_COLUMNS
    cols = record_line.split(",")
    assert len(cols) == 9
    assert cols[0] == body["ticket_id"]
    assert cols[2] == "open"
    assert cols[3] == "urgent"
    assert cols[5] == "Riya"
    assert cols[6] == "omar.ali@example.com"
    assert "escalated" in cols[7]
    assert cols[8] == "480.00"


def test_e2e_batch_csv_ingestion_and_spreadsheet_sync(tmp_path, monkeypatch):
    """Verify bulk CSV file upload parses all rows and persists strictly to 9 columns."""
    test_csv = str(tmp_path / "e2e_batch_sheet.csv")
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)

    csv_data = (
        "ticket_id,created_at,status,priority,category,assigned_to,customer_email,labels,refund_amount\n"
        "TCK-5007,2026-10-05 13:05,in_progress,urgent,Refunds,riya,omar.ali@example.com,escalated,480.00\n"
        "TCK-5084,2026-10-05 13:21,in_progress,normal,Login,riya,jo.marsh@example.com,,0.00\n"
        "TCK-5041,2026-10-05 13:25,open,normal,Refunds,lia,max.obi@example.com,esc,80.00\n"
        "TCK-5052,2026-10-05 13:55,open,normal,Refunds,sam,hana.ito@example.com,esc,250.00\n"
        "TCK-5043,2026-10-05 14:02,resolved,normal,Technical,riya,ava.stone@example.com,,0.00\n"
    )

    files = {
        "file": (
            "helpdesk_export.csv",
            io.BytesIO(csv_data.encode("utf-8")),
            "text/csv",
        )
    }
    res = client.post("/ops/ingest-batch?refund_threshold=200.0", files=files)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert body["processed_count"] == 5
    assert len(body["records"]) == 5
    assert (
        body["escalated_count"] >= 3
    )  # TCK-5007 (urgent), TCK-5041 (esc), TCK-5052 (esc & $250 >= $200)

    # Verify on-disk file
    with open(test_csv, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    assert len(lines) == 6  # 1 header + 5 records
    assert lines[0].split(",") == TARGET_9_COLUMNS
    for row in lines[1:]:
        assert len(row.split(",")) == 9


def test_e2e_ticket_dashboard_and_summary_metrics():
    """Verify ticket listing and summary resilience endpoints."""
    # 1. Summary metrics
    summary_res = client.get("/summary")
    assert summary_res.status_code == 200
    metrics = summary_res.json()
    assert metrics["total"] > 0
    assert "by_category" in metrics
    assert "average_resolution_hours" in metrics

    # 2. Tickets list pagination and search
    tickets_res = client.get("/tickets?page=1&size=10")
    assert tickets_res.status_code == 200
    tickets_data = tickets_res.json()
    assert isinstance(tickets_data, list)
    assert len(tickets_data) <= 10
    if tickets_data:
        assert "ticket_id" in tickets_data[0]
        assert "category" in tickets_data[0]
