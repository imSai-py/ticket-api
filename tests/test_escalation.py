from fastapi.testclient import TestClient

from app.escalation import send_escalation_alert
from app.main import app
from app.schemas import CategoryEnum, PriorityEnum, TriageResponse

client = TestClient(app)


def test_escalation_alert_urgent_ticket(monkeypatch):
    monkeypatch.setenv("ESCALATION_MANAGER_EMAIL", "lead-ops@company.com")
    ticket = {
        "ticket_id": "TCK-9901",
        "customer_name": "VIP Enterprise",
        "category": "Billing",
        "priority": "urgent",
        "amount": 2500.0,
        "reason": "Complete service lockout after double deduction",
    }
    alert = send_escalation_alert(ticket)
    assert alert["dispatched"] is True
    assert alert["recipient"] == "lead-ops@company.com"
    assert "URGENT ESCALATION" in alert["subject"]
    assert "TCK-9901" in alert["subject"]
    assert "VIP Enterprise" in alert["body"]
    assert "$2500.00" in alert["body"]


def test_escalation_alert_explicit_escalated_flag():
    ticket = {
        "ticket_id": "TCK-9902",
        "customer_name": "Acme Corp",
        "category": "Billing",
        "priority": "high",
        "escalated": True,
        "amount": 150.0,
        "reason": "Customer threatened to churn if not resolved immediately",
    }
    alert = send_escalation_alert(ticket)
    assert alert["dispatched"] is True
    assert "TCK-9902" in alert["subject"]


def test_escalation_alert_normal_priority_suppressed():
    ticket = {
        "ticket_id": "TCK-9903",
        "customer_name": "John Doe",
        "category": "Billing",
        "priority": "normal",
        "amount": 19.99,
        "reason": "Question about monthly invoice",
    }
    alert = send_escalation_alert(ticket)
    assert alert["dispatched"] is False
    assert alert["reason"] == "Not an urgent ticket"


def test_escalation_alert_fallback_recipient(monkeypatch):
    monkeypatch.delenv("ESCALATION_MANAGER_EMAIL", raising=False)
    ticket = {
        "ticket_id": "TCK-9904",
        "customer_name": "Alice Smith",
        "category": "Billing",
        "priority": "urgent",
        "amount": 300.0,
        "reason": "Urgent refund required",
    }
    alert = send_escalation_alert(ticket)
    assert alert["dispatched"] is True
    assert alert["recipient"] == "manager@company.com"


def test_post_ops_sync_ticket_returns_escalation_alert():
    payload_urgent = {
        "ticket_id": "TCK-SYNC-URGENT",
        "customer_name": "Emergency Client",
        "category": "Billing",
        "priority": "urgent",
        "amount": 1000.0,
        "reason": "System critical invoice issue",
    }
    res_urgent = client.post("/ops/sync-ticket", json=payload_urgent)
    assert res_urgent.status_code == 200
    data_urgent = res_urgent.json()
    assert "escalation_alert" in data_urgent
    assert data_urgent["escalation_alert"]["dispatched"] is True

    payload_normal = {
        "ticket_id": "TCK-SYNC-NORMAL",
        "customer_name": "Regular Client",
        "category": "Billing",
        "priority": "normal",
        "amount": 50.0,
        "reason": "Normal billing question",
    }
    res_normal = client.post("/ops/sync-ticket", json=payload_normal)
    assert res_normal.status_code == 200
    data_normal = res_normal.json()
    assert "escalation_alert" in data_normal
    assert data_normal["escalation_alert"]["dispatched"] is False


def test_triage_auto_sync_triggers_escalation_for_urgent(monkeypatch):
    monkeypatch.setattr(
        "app.main.classify_and_reply",
        lambda subject, text, matched_articles=None: TriageResponse(
            category=CategoryEnum.BILLING,
            priority=PriorityEnum.URGENT,
            suggested_reply="Immediate assistance requested for critical billing failure.",
            article_ids=["KB-001"],
        ),
    )

    triage_req = {
        "subject": "EMERGENCY: Entire office account locked out due to billing",
        "text": "Our payment method was rejected and all 50 staff are locked out.",
    }
    response = client.post("/triage", json=triage_req)
    assert response.status_code == 200

    pending_res = client.get("/ops/approvals/pending")
    assert pending_res.status_code == 200
    pending = pending_res.json()["pending_approvals"]
    urgent_ticket = next((t for t in pending if t["priority"] == "urgent"), None)
    assert urgent_ticket is not None
    assert urgent_ticket["escalated"] == "True"


def test_smtp_email_dispatch_flow(monkeypatch):
    from app.escalation import dispatch_smtp_email

    # 1. Mock mode when live SMTP is not enabled in test
    monkeypatch.delenv("ENABLE_LIVE_SMTP_IN_TESTS", raising=False)
    res_mock = dispatch_smtp_email("test@example.com", "Test Subject", "Test Body")
    assert res_mock["sent"] is False
    assert res_mock["mode"] == "mock"

    # 2. Simulated SMTP connection
    sent_calls = []

    class MockSMTP:
        def __init__(self, host, port, timeout=10):
            self.host = host
            self.port = port

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def starttls(self):
            pass

        def login(self, user, pwd):
            pass

        def sendmail(self, from_addr, to_addrs, msg_str):
            sent_calls.append({"from": from_addr, "to": to_addrs, "msg": msg_str})

    monkeypatch.setattr("smtplib.SMTP", MockSMTP)
    monkeypatch.setenv("ENABLE_LIVE_SMTP_IN_TESTS", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.testserver.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "notifications@company.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret_pass")

    res_live = dispatch_smtp_email(
        "sailakshman212005@gmail.com", "Urgent Alert", "Ticket body"
    )
    assert res_live["sent"] is True
    assert res_live["mode"] == "smtp"
    assert len(sent_calls) == 1
    assert sent_calls[0]["to"] == ["sailakshman212005@gmail.com"]


def test_escalation_alert_contains_html_approve_reject_buttons(monkeypatch):
    monkeypatch.setenv("BASE_URL", "http://localhost:8000")
    ticket = {
        "ticket_id": "TCK-BTN-1",
        "customer_name": "Test Customer",
        "category": "Billing",
        "priority": "urgent",
        "amount": 450.0,
        "reason": "Double billing dispute",
    }
    alert = send_escalation_alert(ticket, dispatch_smtp=False)
    assert alert["dispatched"] is True
    assert "html_body" in alert
    assert "✅ Approve" in alert["html_body"]
    assert "❌ Reject" in alert["html_body"]
    assert (
        "http://localhost:8000/ops/approvals/TCK-BTN-1/action?status=Approved"
        in alert["html_body"]
    )
    assert (
        "http://localhost:8000/ops/approvals/TCK-BTN-1/action?status=Rejected"
        in alert["html_body"]
    )


def test_escalation_alert_non_billing_category_suppressed():
    non_billing_ticket = {
        "ticket_id": "TCK-LOGIN-URGENT",
        "customer_name": "Login User",
        "category": "Login",
        "priority": "urgent",
        "amount": 0.0,
        "reason": "Locked out of 2FA",
    }
    alert = send_escalation_alert(non_billing_ticket)
    assert alert["dispatched"] is False
    assert "outside current escalation scope" in alert["reason"]


def test_batch_ingest_dispatches_single_digest_email(tmp_path, monkeypatch):
    test_csv = str(tmp_path / "single_digest_ops.csv")
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)

    digest_calls = []

    def mock_generate_batch_digest(*args, **kwargs):
        digest_calls.append({"args": args, "kwargs": kwargs})
        return {"has_pending": True, "dispatched": True, "pending_count": 2}

    monkeypatch.setattr("app.main.generate_batch_digest", mock_generate_batch_digest)

    csv_batch = (
        "ticket_id,created_at,status,priority,category,assigned_to,customer_email,labels,refund_amount\n"
        "TCK-B1,2026-10-15 10:00,open,urgent,Billing,riya,user1@example.com,escalated,120.00\n"
        "TCK-B2,2026-10-15 10:05,open,urgent,Refunds,sam,user2@example.com,escalated,250.00\n"
        "TCK-B3,2026-10-15 10:10,open,normal,Login,lia,user3@example.com,,0.00\n"
    )

    resp = client.post(
        "/ops/ingest-batch",
        files={"file": ("batch.csv", csv_batch.encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["processed_count"] == 3
    assert data["escalated_count"] == 2
    # Verify exactly ONE consolidated digest was triggered for the entire batch
    assert len(digest_calls) == 1
