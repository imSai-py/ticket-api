from fastapi.testclient import TestClient

from app.main import app
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

    res = client.post("/ops/approvals/send-digest")
    assert res.status_code == 200
    digest = res.json()
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


def test_send_agent_info_request_email_positional_args(tmp_path, monkeypatch):
    """Spec L71: needs_info action dispatches agent notification with ticket details."""
    test_csv = str(tmp_path / "agent_notif_test.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)

    captured = []

    def fake_dispatch(to_email, subject, body, html_body=None):
        captured.append({"to": to_email, "subject": subject, "body": body})
        return {"sent": True}

    import app.escalation as esc

    monkeypatch.setattr(esc, "dispatch_smtp_email", fake_dispatch)

    sync_res = client.post(
        "/ops/sync-ticket",
        json={
            "customer_name": "Bruce Wayne",
            "category": "Billing",
            "priority": "urgent",
            "amount": 500.0,
            "reason": "Duplicate invoice investigation",
            "agent": "lucius@wayne.com",
        },
    )
    assert sync_res.status_code == 200
    ticket_id = sync_res.json()["ticket"]["ticket_id"]

    res_action = client.get(f"/ops/approvals/{ticket_id}/action?status=needs_info")
    assert res_action.status_code == 200
    assert len(captured) > 0
    notif = captured[-1]
    assert notif["to"] == "lucius@wayne.com"
    assert ticket_id in notif["subject"]
    assert "Bruce Wayne" in notif["body"]


def test_approval_action_accepts_needs_info_status(tmp_path, monkeypatch):
    """Spec L27 & L58: /ops/approvals/action endpoint accepts status=needs_info."""
    test_csv = str(tmp_path / "needs_info_enum.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)

    sync_res = client.post(
        "/ops/sync-ticket",
        json={
            "customer_name": "Test User",
            "category": "Billing",
            "priority": "urgent",
            "amount": 100.0,
            "reason": "Initial inquiry",
        },
    )
    assert sync_res.status_code == 200
    ticket_id = sync_res.json()["ticket"]["ticket_id"]

    res = client.get(f"/ops/approvals/{ticket_id}/action?status=needs_info")
    assert res.status_code == 200
    assert "marked as needing more info" in res.text


def test_sync_ticket_request_ignores_arbitrary_status_injection(tmp_path, monkeypatch):
    """Spec Scope: POST /ops/sync-ticket does not permit arbitrary client status override to Approved."""
    test_csv = str(tmp_path / "no_status_injection.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)

    sync_res = client.post(
        "/ops/sync-ticket",
        json={
            "customer_name": "Injected Customer",
            "category": "Billing",
            "priority": "normal",
            "amount": 50.0,
            "reason": "Test dispute",
            "status": "Approved",
        },
    )
    assert sync_res.status_code == 200
    assert sync_res.json()["ticket"]["status"] == "Pending"


def test_terminal_approval_status_transitions(tmp_path, monkeypatch):
    """Spec L60-61: Approved and Rejected are terminal states."""
    test_csv = str(tmp_path / "terminal_test.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)

    sync_ticket_to_spreadsheet(
        {
            "ticket_id": "TCK-TERM-01",
            "status": "Pending",
            "category": "Billing",
            "amount": 100.0,
            "reason": "Verified service cancellation credit",
        },
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

    # Spec L62-63: Transitioning needs_info directly to Approved without agent re-submission fails with 400
    sync_ticket_to_spreadsheet(
        {
            "ticket_id": "TCK-TERM-02",
            "status": "needs_info",
            "category": "Billing",
            "amount": 100.0,
            "reason": "Verified service cancellation credit",
        },
        csv_path=test_csv,
    )
    res_direct_approve = client.get("/ops/approvals/TCK-TERM-02/action?status=Approved")
    assert res_direct_approve.status_code == 400
    assert "re-submission" in res_direct_approve.json()["detail"].lower()


def test_batch_ingest_does_not_reset_needs_info(tmp_path, monkeypatch):
    """Spec L29: Batch CSV ingest must not auto-resubmit needs_info tickets."""
    test_csv = str(tmp_path / "batch_no_reset.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)

    sync_res = client.post(
        "/ops/sync-ticket",
        json={
            "customer_name": "Test User",
            "category": "Billing",
            "priority": "urgent",
            "amount": 100.0,
            "reason": "Initial inquiry",
        },
    )
    assert sync_res.status_code == 200
    ticket_id = sync_res.json()["ticket"]["ticket_id"]

    res_action = client.get(f"/ops/approvals/{ticket_id}/action?status=needs_info")
    assert res_action.status_code == 200

    csv_content = (
        f"ticket_id,created_at,status,priority,category,assigned_to,customer_email,labels,refund_amount\n"
        f"{ticket_id},2026-10-15 12:00:00,open,urgent,Billing,Riya,test@example.com,escalated,100.00\n"
    )
    res_batch = client.post("/ops/ingest-batch", json={"csv_content": csv_content})
    assert res_batch.status_code == 200

    counts = client.get("/ops/approvals/pending").json()
    assert counts["needs_info_count"] == 1
    assert counts["pending_count"] == 0


def test_agent_recipient_email_resolution(tmp_path, monkeypatch):
    """Spec L28: Automatic agent notification properly formats email without double domain."""
    test_csv = str(tmp_path / "agent_recipient.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)
    monkeypatch.delenv("AGENT_NOTIFICATIONS_EMAIL", raising=False)

    captured_recipients = []

    def fake_dispatch(to_email, subject, body, html_body=None):
        captured_recipients.append(to_email)
        return {"sent": True}

    import app.escalation as esc

    monkeypatch.setattr(esc, "dispatch_smtp_email", fake_dispatch)

    sync_res = client.post(
        "/ops/sync-ticket",
        json={
            "customer_name": "Alex",
            "customer_email": "customer@external.com",
            "category": "Billing",
            "priority": "urgent",
            "amount": 250.0,
            "reason": "Duplicate transaction",
            "agent": "Riya",
        },
    )
    assert sync_res.status_code == 200
    ticket_id = sync_res.json()["ticket"]["ticket_id"]

    res = client.get(f"/ops/approvals/{ticket_id}/action?status=needs_info")
    assert res.status_code == 200
    assert len(captured_recipients) > 0
    assert captured_recipients[-1] == "riya@company.com"
    assert "customer@external.com" not in captured_recipients


def test_escalation_alert_dictionary_contains_need_info_url(tmp_path, monkeypatch):
    """Spec L26 & L69: Alert return dictionary includes need_info_url."""
    test_csv = str(tmp_path / "escalation_dict_test.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)

    sync_res = client.post(
        "/ops/sync-ticket",
        json={
            "customer_name": "Test User",
            "category": "Billing",
            "priority": "urgent",
            "amount": 250.0,
            "reason": "Test dispute",
        },
    )
    assert sync_res.status_code == 200
    data = sync_res.json()
    assert "escalation_alert" in data
    alert = data["escalation_alert"]
    assert alert["dispatched"] is True
    assert "need_info_url" in alert
    ticket_id = data["ticket"]["ticket_id"]
    assert f"ticket_id={ticket_id}&status=needs_info" in alert["need_info_url"]


def test_agent_info_request_uses_agent_email_not_customer_email(tmp_path, monkeypatch):
    """Spec L28: Agent info request never routes internal notification to customer email."""
    test_csv = str(tmp_path / "agent_not_customer.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)
    monkeypatch.delenv("AGENT_NOTIFICATIONS_EMAIL", raising=False)

    captured = []

    def fake_dispatch(to_email, subject, body, html_body=None):
        captured.append(to_email)
        return {"sent": True}

    import app.escalation as esc

    monkeypatch.setattr(esc, "dispatch_smtp_email", fake_dispatch)

    sync_res = client.post(
        "/ops/sync-ticket",
        json={
            "customer_name": "Customer User",
            "customer_email": "customer@external.com",
            "category": "Billing",
            "priority": "urgent",
            "amount": 150.0,
            "reason": "Need info test",
            "agent": "agent_sarah",
        },
    )
    assert sync_res.status_code == 200
    ticket_id = sync_res.json()["ticket"]["ticket_id"]

    res = client.get(f"/ops/approvals/{ticket_id}/action?status=needs_info")
    assert res.status_code == 200
    assert "agent_sarah@company.com" in captured
    assert "customer@external.com" not in captured


def test_refund_requires_operational_justification(tmp_path, monkeypatch):
    """Spec L30 & L41: Missing operational reasons for refund block approval until justified."""
    test_csv = str(tmp_path / "reason_test.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)

    # 1. Sync refund without operational reason
    res_sync = client.post(
        "/ops/sync-ticket",
        json={
            "customer_name": "Valued Customer",
            "category": "Billing",
            "priority": "urgent",
            "amount": 120.0,
            "reason": "",
            "agent": "Dan",
        },
    )
    assert res_sync.status_code == 200
    ticket_id = res_sync.json()["ticket"]["ticket_id"]

    # 2. Payout approval without operational reason is blocked
    res_approve_fail = client.get(f"/ops/approvals/{ticket_id}/action?status=Approved")
    assert res_approve_fail.status_code == 400
    assert "operational justification" in res_approve_fail.json()["detail"].lower()

    # 3. Agent re-submits with verified operational justification
    res_resubmit = client.post(
        "/ops/sync-ticket",
        json={
            "ticket_id": ticket_id,
            "customer_name": "Valued Customer",
            "category": "Billing",
            "priority": "urgent",
            "amount": 120.0,
            "reason": "Double billing on subscription plan confirmed with merchant gateway",
            "agent": "Dan",
        },
    )
    assert res_resubmit.status_code == 200

    # 4. Approval now succeeds with verified reason
    res_approve_ok = client.get(f"/ops/approvals/{ticket_id}/action?status=Approved")
    assert res_approve_ok.status_code == 200
    assert "Approved" in res_approve_ok.text
