from fastapi.testclient import TestClient

from app.batch_digest import generate_batch_digest
from app.escalation import send_agent_info_request_email
from app.main import app
from app.schemas import ApprovalStatusEnum, SyncTicketRequest
from app.tracking_sync import sync_ticket_to_spreadsheet

client = TestClient(app)


def test_pending_endpoint_returns_distinct_needs_info_count(tmp_path, monkeypatch):
    """Spec L46: GET /ops/approvals/pending returns distinct counts for pending vs needs_info."""
    test_csv = str(tmp_path / "counts_test.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)

    sync_ticket_to_spreadsheet(
        {"ticket_id": "TCK-CNT-01", "status": "Pending", "category": "Billing"},
        csv_path=test_csv,
    )
    sync_ticket_to_spreadsheet(
        {"ticket_id": "TCK-CNT-02", "status": "needs_info", "category": "Billing"},
        csv_path=test_csv,
    )

    res = client.get("/ops/approvals/pending")
    assert res.status_code == 200
    data = res.json()
    assert "pending_count" in data
    assert "needs_info_count" in data
    assert data["pending_count"] == 1
    assert data["needs_info_count"] == 1


def test_health_check_verifies_digest_scheduler_readiness():
    """Spec L48: GET /health verifies digest scheduling readiness."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert "digest_scheduler" in data
    assert data["digest_scheduler"] in ("ready", "active", "healthy")


def test_action_url_query_format_in_email_digest(tmp_path, monkeypatch):
    """Spec L69: Action link format: /ops/approvals/action?ticket_id={id}&status=needs_info."""
    test_csv = str(tmp_path / "action_url_format.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)
    monkeypatch.setenv("BASE_URL", "https://api.example.com")

    sync_ticket_to_spreadsheet(
        {
            "ticket_id": "TCK-URL-01",
            "status": "Pending",
            "category": "Billing",
            "amount": 100.0,
        },
        csv_path=test_csv,
    )

    digest = generate_batch_digest(csv_path=test_csv)
    assert (
        "https://api.example.com/ops/approvals/action?ticket_id=TCK-URL-01&status=Approved"
        in digest["body_table"]
    )
    assert (
        "https://api.example.com/ops/approvals/action?ticket_id=TCK-URL-01&status=Rejected"
        in digest["body_table"]
    )
    assert (
        "https://api.example.com/ops/approvals/action?ticket_id=TCK-URL-01&status=needs_info"
        in digest["body_table"]
    )


def test_send_agent_info_request_email_positional_args():
    """Spec L71: send_agent_info_request_email(ticket_id, customer_name, amount, reason, agent_email)."""
    res = send_agent_info_request_email(
        "TCK-POS-01",
        "Bruce Wayne",
        "500.00",
        "Duplicate invoice investigation",
        "lucius@wayne.com",
    )
    assert res["dispatched"] is True
    assert "TCK-POS-01" in res["subject"]
    assert "Bruce Wayne" in res["body"]


def test_approval_status_enum_needs_info_value():
    """Spec L27 & L58: ApprovalStatusEnum.NEEDS_INFO.value == 'needs_info'."""
    assert ApprovalStatusEnum.NEEDS_INFO.value == "needs_info"


def test_sync_ticket_request_schema_no_arbitrary_status():
    """Spec Scope: SyncTicketRequest does not expose arbitrary status injection field."""
    fields = SyncTicketRequest.model_fields
    assert "status" not in fields
