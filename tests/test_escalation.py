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
    assert "⚠️ Need More Info" in alert["html_body"]
    assert (
        "http://localhost:8000/ops/approvals/action?ticket_id=TCK-BTN-1&status=Approved"
        in alert["html_body"]
    )
    assert (
        "http://localhost:8000/ops/approvals/action?ticket_id=TCK-BTN-1&status=Rejected"
        in alert["html_body"]
    )
    assert (
        "http://localhost:8000/ops/approvals/action?ticket_id=TCK-BTN-1&status=needs_info"
        in alert["html_body"]
    )


def test_escalation_alert_all_categories_when_urgent(monkeypatch):
    monkeypatch.setenv("ESCALATION_MANAGER_EMAIL", "manager@company.com")
    categories = ["Technical", "Login", "Shipping", "Account", "Billing", "Refunds"]
    for cat in categories:
        ticket = {
            "ticket_id": f"TCK-{cat.upper()}-01",
            "customer_name": f"{cat} User",
            "category": cat,
            "priority": "urgent",
            "amount": 0.0,
            "reason": f"Urgent issue in {cat}",
        }
        alert = send_escalation_alert(ticket, dispatch_smtp=False)
        assert alert["dispatched"] is True, f"Failed for category {cat}"
        assert alert["recipient"] == "manager@company.com"
        assert f"TCK-{cat.upper()}-01" in alert["subject"]
        assert f"Category:      {cat}" in alert["body"]
        assert "http://localhost:8000/ops/approvals/action" in alert["body"]
        assert "http://localhost:8000/ops/approvals/action" in alert["html_body"]


def test_escalation_alert_non_urgent_all_categories_suppressed():
    categories = ["Technical", "Login", "Shipping", "Account"]
    for cat in categories:
        ticket = {
            "ticket_id": f"TCK-{cat.upper()}-LOW",
            "customer_name": f"{cat} Normal User",
            "category": cat,
            "priority": "normal",
            "amount": 0.0,
            "reason": f"Normal question in {cat}",
        }
        alert = send_escalation_alert(ticket, dispatch_smtp=False)
        assert alert["dispatched"] is False
        assert "Not an urgent ticket" in alert["reason"]


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


def test_send_agent_info_request_email_dispatch(tmp_path, monkeypatch):
    """Test agent notification dispatch through the FastAPI HTTP boundary."""
    from fastapi.testclient import TestClient

    import app.escalation as esc
    from app.main import app
    from app.tracking_sync import sync_ticket_to_spreadsheet

    client = TestClient(app)
    test_csv = str(tmp_path / "agent_dispatch_test.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)
    monkeypatch.setenv("AGENT_NOTIFICATIONS_EMAIL", "agent-support@company.com")

    captured = []

    def fake_dispatch(to_email, subject, body, html_body=None):
        captured.append({"to": to_email, "subject": subject, "body": body})
        return {"sent": True}

    monkeypatch.setattr(esc, "dispatch_smtp_email", fake_dispatch)

    sync_ticket_to_spreadsheet(
        {
            "ticket_id": "TCK-INFO-001",
            "customer_name": "Oliver Queen",
            "category": "Billing",
            "priority": "urgent",
            "amount": 350.0,
            "reason": "Double monthly subscription deduction",
            "assigned_to": "Felicity",
        },
        csv_path=test_csv,
    )

    res = client.get(
        "/ops/approvals/TCK-INFO-001/action?status=needs_info&instructions=Please+request+bank+statement+copy+verifying+charge."
    )
    assert res.status_code == 200
    assert len(captured) > 0
    notif = captured[-1]
    assert notif["to"] == "agent-support@company.com"
    assert "TCK-INFO-001" in notif["subject"]
    assert "Oliver Queen" in notif["subject"]
    assert "bank statement copy" in notif["body"]


def test_send_resubmission_notification_format_and_dispatch(monkeypatch):
    """Verify send_resubmission_notification dispatches email to manager with 3 action buttons and context."""
    import app.escalation as esc
    from app.escalation import send_resubmission_notification

    monkeypatch.setenv("ESCALATION_MANAGER_EMAIL", "ops-manager@company.com")
    monkeypatch.setenv("BASE_URL", "https://api.test.com")

    captured = []

    def fake_dispatch(to_email, subject, body, html_body=None):
        captured.append(
            {
                "to": to_email,
                "subject": subject,
                "body": body,
                "html": html_body,
            }
        )
        return {"sent": True, "mode": "smtp"}

    monkeypatch.setattr(esc, "dispatch_smtp_email", fake_dispatch)

    ticket = {
        "ticket_id": "TCK-RESUB-77",
        "customer_name": "Bruce Wayne",
        "category": "Billing",
        "refund_amount": "450.00",
        "assigned_to": "Alfred",
        "reason": "Verified dual billing on invoice #INV-7711",
        "notes": "Manager requested more info at 2026-10-15 10:00:00; Agent verified dual charge",
    }

    alert = send_resubmission_notification(ticket)
    assert alert["dispatched"] is True
    assert alert["recipient"] == "ops-manager@company.com"
    assert "TCK-RESUB-77" in alert["subject"]
    assert "Bruce Wayne" in alert["subject"]
    assert "$450.00" in alert["subject"]
    assert len(captured) == 1
    call = captured[0]
    assert call["to"] == "ops-manager@company.com"
    assert "status=Approved" in call["html"]
    assert "status=Rejected" in call["html"]
    assert "status=needs_info" in call["html"]
    assert "Alfred" in call["html"]
    assert "Verified dual billing on invoice #INV-7711" in call["html"]


def test_ops_sync_ticket_dispatches_notification_to_manager_on_resubmission(
    tmp_path, monkeypatch
):
    """Verify POST /ops/sync-ticket notifies the manager when a ticket is resubmitted."""
    from fastapi.testclient import TestClient

    import app.escalation as esc
    from app.main import app

    client = TestClient(app)
    test_csv = str(tmp_path / "sync_resubmit_dispatch.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)
    monkeypatch.setenv("ESCALATION_MANAGER_EMAIL", "manager-review@example.com")

    captured_emails = []

    def fake_dispatch(to_email, subject, body, html_body=None):
        captured_emails.append(
            {
                "to": to_email,
                "subject": subject,
                "body": body,
                "html": html_body,
            }
        )
        return {"sent": True}

    monkeypatch.setattr(esc, "dispatch_smtp_email", fake_dispatch)

    # 1. Create initial ticket
    init_res = client.post(
        "/ops/sync-ticket",
        json={
            "ticket_id": "TCK-RESUB-88",
            "customer_name": "Diana Prince",
            "customer_email": "diana@themyscira.gov",
            "category": "Billing",
            "priority": "normal",
            "amount": 180.0,
            "reason": "Subscription duplicate",
            "agent": "Steve",
        },
    )
    assert init_res.status_code == 200
    captured_emails.clear()

    # 2. Transition to needs_info
    info_res = client.get("/ops/approvals/TCK-RESUB-88/action?status=needs_info")
    assert info_res.status_code == 200
    captured_emails.clear()

    # 3. Agent resubmits ticket
    resubmit_res = client.post(
        "/ops/sync-ticket",
        json={
            "ticket_id": "TCK-RESUB-88",
            "reason": "Confirmed customer was billed twice via Stripe transaction #ch_9921",
            "agent": "Steve",
            "amount": 180.0,
        },
    )
    assert resubmit_res.status_code == 200
    res_data = resubmit_res.json()
    assert res_data["ticket"]["status"] == "Pending"
    assert "resubmission_notification" in res_data
    assert res_data["resubmission_notification"]["dispatched"] is True

    # 4. Verify email was dispatched to manager
    manager_emails = [
        c for c in captured_emails if c["to"] == "manager-review@example.com"
    ]
    assert len(manager_emails) >= 1
    m_email = manager_emails[0]
    assert "TCK-RESUB-88" in m_email["subject"]
    assert "status=Approved" in m_email["html"]


def test_resubmission_urgent_priority_category_preservation_and_enum_sanitization(
    tmp_path, monkeypatch
):
    """Verify that re-submitting a ticket elevates priority to 'urgent', preserves original
    category unless overridden, and strictly sanitizes any enum representations.
    """
    from fastapi.testclient import TestClient

    import app.escalation as esc
    from app.main import app
    from app.tracking_sync import _read_all

    client = TestClient(app)
    test_csv = str(tmp_path / "resubmit_urgent_test.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)
    monkeypatch.setenv("ESCALATION_MANAGER_EMAIL", "manager-urgent@example.com")

    captured_emails = []

    def fake_dispatch(to_email, subject, body, html_body=None):
        captured_emails.append(
            {
                "to": to_email,
                "subject": subject,
                "body": body,
                "html": html_body,
            }
        )
        return {"sent": True}

    monkeypatch.setattr(esc, "dispatch_smtp_email", fake_dispatch)

    # 1. Create an initial ticket with category 'Refunds' and priority 'normal'
    init_res = client.post(
        "/ops/sync-ticket",
        json={
            "ticket_id": "TCK-URG-100",
            "customer_name": "Tony Stark",
            "customer_email": "tony@stark.com",
            "category": "Refunds",
            "priority": "normal",
            "amount": 250.0,
            "reason": "Damaged parts returned",
            "agent": "Pepper",
        },
    )
    assert init_res.status_code == 200
    init_data = init_res.json()
    assert init_data["ticket"]["category"] == "Refunds"
    assert init_data["ticket"]["priority"] == "normal"
    assert "Enum" not in init_data["ticket"]["category"]
    assert "enum" not in init_data["ticket"]["priority"].lower().replace(
        "urgent", ""
    ).replace("normal", "")

    # 2. Transition ticket to needs_info
    client.get("/ops/approvals/TCK-URG-100/action?status=needs_info")
    captured_emails.clear()

    # 3. Agent re-submits ticket with supplemental context without specifying category
    resubmit_res = client.post(
        "/ops/sync-ticket",
        json={
            "ticket_id": "TCK-URG-100",
            "reason": "Verified carrier return tracking #STARK-9918 delivered to warehouse.",
            "agent": "Pepper",
            "amount": 250.0,
            "is_resubmission": True,
        },
    )
    assert resubmit_res.status_code == 200
    res_data = resubmit_res.json()
    ticket_row = res_data["ticket"]

    # Priority MUST be elevated to 'urgent' and marked escalated
    assert ticket_row["priority"] == "urgent"
    assert ticket_row["escalated"] == "True"

    # Category MUST preserve 'Refunds' (not overwritten with 'Billing' or 'CategoryEnum.BILLING')
    assert ticket_row["category"] == "Refunds"

    # Manager notification MUST contain '[URGENT RESUBMISSION FOR REVIEW]' and urgent priority
    assert len(captured_emails) >= 1
    manager_email = captured_emails[-1]
    assert "[URGENT RESUBMISSION FOR REVIEW]" in manager_email["subject"]
    assert "URGENT" in manager_email["body"].upper()

    # 4. Agent re-submits with an explicit category change to 'Technical'
    captured_emails.clear()
    resubmit_tech = client.post(
        "/ops/sync-ticket",
        json={
            "ticket_id": "TCK-URG-100",
            "category": "Technical",
            "reason": "Escalating hardware diagnostics to engineering.",
            "agent": "Pepper",
            "amount": 250.0,
            "is_resubmission": True,
        },
    )
    assert resubmit_tech.status_code == 200
    tech_row = resubmit_tech.json()["ticket"]
    assert tech_row["category"] == "Technical"
    assert tech_row["priority"] == "urgent"

    # 5. Verify CSV records on disk never contain Enum class names
    rows = _read_all(test_csv)
    for row in rows:
        assert "CategoryEnum." not in row.get("category", "")
        assert "categoryenum." not in row.get("category", "").lower()
        assert "PriorityEnum." not in row.get("priority", "")
        assert "priorityenum." not in row.get("priority", "").lower()


def test_dispatch_http_email_resend_success(monkeypatch):
    """Verify HTTP email dispatch via Resend API when RESEND_API_KEY is configured."""
    import httpx

    from app.escalation import dispatch_smtp_email

    monkeypatch.setenv("ENABLE_LIVE_SMTP_IN_TESTS", "1")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key_123")
    monkeypatch.setenv("RESEND_FROM", "test@resend.dev")

    posted_urls = []
    posted_payloads = []

    def mock_post(self, url, headers=None, json=None, **kwargs):
        posted_urls.append(url)
        posted_payloads.append(json)
        return httpx.Response(
            200, json={"id": "msg_resend_abc123"}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    res = dispatch_smtp_email(
        to_email="manager@example.com",
        subject="[URGENT REVIEW] Test",
        body="Plain text body",
        html_body="<p>HTML body</p>",
    )

    assert res["sent"] is True
    assert res["mode"] == "resend"
    assert res["id"] == "msg_resend_abc123"
    assert "https://api.resend.com/emails" in posted_urls
    assert posted_payloads[0]["to"] == ["manager@example.com"]
    assert posted_payloads[0]["from"] == "test@resend.dev"


def test_dispatch_http_email_brevo_success(monkeypatch):
    """Verify HTTP email dispatch via Brevo API when BREVO_API_KEY is configured."""
    import httpx

    from app.escalation import dispatch_smtp_email

    monkeypatch.setenv("ENABLE_LIVE_SMTP_IN_TESTS", "1")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib_test_key_456")
    monkeypatch.setenv("BREVO_FROM", "alerts@customcompany.com")

    posted_urls = []
    posted_payloads = []

    def mock_post(self, url, headers=None, json=None, **kwargs):
        posted_urls.append(url)
        posted_payloads.append(json)
        return httpx.Response(
            201,
            json={"messageId": "<msg_brevo_xyz@smtp>"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    res = dispatch_smtp_email(
        to_email="manager@example.com",
        subject="[URGENT REVIEW] Brevo Test",
        body="Plain text body",
        html_body="<p>HTML body</p>",
    )

    assert res["sent"] is True
    assert res["mode"] == "brevo"
    assert res["messageId"] == "<msg_brevo_xyz@smtp>"
    assert "https://api.brevo.com/v3/smtp/email" in posted_urls
    assert posted_payloads[0]["to"] == [{"email": "manager@example.com"}]
    assert posted_payloads[0]["sender"]["email"] == "alerts@customcompany.com"


def test_dispatch_http_email_webhook_success(monkeypatch):
    """Verify HTTP email dispatch via generic webhook URL."""
    import httpx

    from app.escalation import dispatch_smtp_email

    monkeypatch.setenv("ENABLE_LIVE_SMTP_IN_TESTS", "1")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.setenv("EMAIL_WEBHOOK_URL", "https://relay.example.com/api/send")

    posted_urls = []

    def mock_post(self, url, json=None, **kwargs):
        posted_urls.append(url)
        return httpx.Response(
            200, json={"status": "queued"}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    res = dispatch_smtp_email(
        to_email="manager@example.com",
        subject="Webhook Test",
        body="Plain body",
    )

    assert res["sent"] is True
    assert res["mode"] == "webhook"
    assert "https://relay.example.com/api/send" in posted_urls


def test_dispatch_smtp_email_diagnoses_network_unreachable_on_cloud_hosts(monkeypatch):
    """Verify that when SMTP raises Errno 101 (Network unreachable), diagnosis is returned."""
    import smtplib

    from app.escalation import dispatch_smtp_email

    monkeypatch.setenv("ENABLE_LIVE_SMTP_IN_TESTS", "1")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.delenv("EMAIL_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "test@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")

    def mock_smtp(*args, **kwargs):
        raise OSError(101, "Network is unreachable")

    monkeypatch.setattr(smtplib, "SMTP", mock_smtp)

    res = dispatch_smtp_email(
        to_email="manager@example.com",
        subject="Test Alert",
        body="Body",
    )

    assert res["sent"] is False
    assert res["mode"] == "smtp_error"
    assert "Network is unreachable" in res["error"]
    assert "Render Free Tier" in res.get("diagnosis", "")
