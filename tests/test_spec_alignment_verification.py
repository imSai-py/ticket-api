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


def test_terminal_approval_status_transitions(tmp_path, monkeypatch):
    """Spec L60-61: Approved and Rejected are terminal states."""
    test_csv = str(tmp_path / "terminal_test.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)

    sync_ticket_to_spreadsheet(
        {"ticket_id": "TCK-TERM-01", "status": "Pending", "category": "Billing"},
        csv_path=test_csv,
    )

    # Approve ticket
    res1 = client.get("/ops/approvals/TCK-TERM-01/action?status=Approved")
    assert res1.status_code == 200

    # Idempotent re-approval succeeds
    res_idempotent = client.get("/ops/approvals/TCK-TERM-01/action?status=Approved")
    assert res_idempotent.status_code == 200

    # Attempting to transition terminal Approved to needs_info fails with 400
    res_invalid = client.get("/ops/approvals/TCK-TERM-01/action?status=needs_info")
    assert res_invalid.status_code == 400
    assert "terminal" in res_invalid.json()["detail"].lower()


def test_batch_ingest_does_not_reset_needs_info(tmp_path, monkeypatch):
    """Spec L29: Batch CSV ingest must not auto-resubmit needs_info tickets."""
    from app.tracking_sync import (
        get_needs_info_approvals,
        sync_tickets_batch_to_spreadsheet,
    )

    test_csv = str(tmp_path / "batch_no_reset.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)

    sync_ticket_to_spreadsheet(
        {"ticket_id": "TCK-BATCH-NI", "status": "needs_info", "category": "Billing"},
        csv_path=test_csv,
    )

    # Batch import with default open status
    sync_tickets_batch_to_spreadsheet(
        [
            {
                "ticket_id": "TCK-BATCH-NI",
                "customer_name": "Test User",
                "category": "Billing",
                "status": "open",
            }
        ],
        csv_path=test_csv,
    )

    needs_info = get_needs_info_approvals(csv_path=test_csv)
    assert len(needs_info) == 1
    assert needs_info[0]["ticket_id"] == "TCK-BATCH-NI"


def test_agent_recipient_email_resolution(monkeypatch):
    """Spec L28: Automatic agent notification properly formats email without double domain."""
    from app.escalation import _resolve_agent_recipient

    monkeypatch.delenv("AGENT_NOTIFICATIONS_EMAIL", raising=False)
    assert _resolve_agent_recipient("riya@example.com") == "riya@example.com"
    assert (
        _resolve_agent_recipient("Support Team", agent_email="dan@example.com")
        == "dan@example.com"
    )
    assert _resolve_agent_recipient("Riya") == "riya@company.com"


def test_escalation_alert_dictionary_contains_need_info_url():
    """Spec L26 & L69: Alert return dictionary includes need_info_url."""
    from app.escalation import send_escalation_alert

    ticket = {
        "ticket_id": "TCK-RET-01",
        "category": "Billing",
        "priority": "urgent",
        "amount": 250.0,
        "reason": "Test dispute",
    }
    alert = send_escalation_alert(ticket, dispatch_smtp=False)
    assert alert["dispatched"] is True
    assert "need_info_url" in alert
    assert "ticket_id=TCK-RET-01&status=needs_info" in alert["need_info_url"]


def test_agent_info_request_uses_agent_email_not_customer_email(monkeypatch):
    """Spec L28: Agent info request never routes internal notification to customer email."""
    from app.escalation import send_agent_info_request_email

    monkeypatch.delenv("AGENT_NOTIFICATIONS_EMAIL", raising=False)
    ticket = {
        "ticket_id": "TCK-CUST-NOTIF",
        "customer_name": "Customer User",
        "customer_email": "customer@external.com",
        "assigned_to": "agent_sarah",
        "amount": 150.0,
        "category": "Billing",
    }
    res = send_agent_info_request_email(ticket)
    assert res["dispatched"] is True
    assert res["recipient"] == "agent_sarah@company.com"
    assert res["recipient"] != "customer@external.com"


def test_refund_requires_operational_justification(tmp_path, monkeypatch):
    """Spec L30 & L41: Missing operational reasons for refund trigger justification note."""
    test_csv = str(tmp_path / "reason_test.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)

    sync_ticket_to_spreadsheet(
        {
            "ticket_id": "TCK-REASON-01",
            "category": "Billing",
            "amount": 120.0,
            "reason": "",
            "assigned_to": "Dan",
        },
        csv_path=test_csv,
    )

    from app.tracking_sync import _read_all, update_approval_status

    rows = _read_all(test_csv)
    target = next(r for r in rows if r["ticket_id"] == "TCK-REASON-01")
    assert "Needs operational justification" in target["notes"]

    # Verify agent sign-off in notes upon approval per Spec L47
    updated = update_approval_status("TCK-REASON-01", "Approved", csv_path=test_csv)
    assert "Verified: Agent Dan signed off" in updated["notes"]
