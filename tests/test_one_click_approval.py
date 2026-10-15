from fastapi.testclient import TestClient

from app.batch_digest import generate_batch_digest
from app.main import app
from app.tracking_sync import get_pending_approvals, sync_ticket_to_spreadsheet

client = TestClient(app)


def test_batch_digest_includes_action_links(tmp_path, monkeypatch):
    test_csv = str(tmp_path / "action_links_test.csv")
    monkeypatch.setenv("BASE_URL", "https://api.example.com")

    sync_ticket_to_spreadsheet(
        {
            "ticket_id": "TCK-ACT-001",
            "customer_name": "Diana Prince",
            "category": "Billing",
            "priority": "normal",
            "amount": 150.0,
            "reason": "Overage adjustment",
            "agent": "Alfred",
        },
        csv_path=test_csv,
    )

    digest = generate_batch_digest(csv_path=test_csv)
    assert digest["has_pending"] is True
    assert (
        "https://api.example.com/ops/approvals/action?ticket_id=TCK-ACT-001&status=Approved"
        in digest["body_table"]
    )
    assert (
        "https://api.example.com/ops/approvals/action?ticket_id=TCK-ACT-001&status=Rejected"
        in digest["body_table"]
    )
    assert (
        "https://api.example.com/ops/approvals/action?ticket_id=TCK-ACT-001&status=needs_info"
        in digest["body_table"]
    )
    assert "Need More Info" in digest["html_body"]


def test_one_click_approve_action(tmp_path, monkeypatch):
    test_csv = str(tmp_path / "approve_action.csv")
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)

    sync_ticket_to_spreadsheet(
        {
            "ticket_id": "TCK-ACT-101",
            "customer_name": "Bruce Wayne",
            "category": "Billing",
            "priority": "normal",
            "amount": 500.0,
            "reason": "Annual server charge adjustment",
            "agent": "Lucius",
        },
        csv_path=test_csv,
    )

    res = client.get("/ops/approvals/TCK-ACT-101/action?status=Approved")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Ticket TCK-ACT-101 marked Approved" in res.text
    assert "You may close this tab" in res.text

    # Verify status in tracking sheet
    pending = get_pending_approvals(csv_path=test_csv)
    assert len(pending) == 0


def test_one_click_reject_action(tmp_path, monkeypatch):
    test_csv = str(tmp_path / "reject_action.csv")
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)

    sync_ticket_to_spreadsheet(
        {
            "ticket_id": "TCK-ACT-102",
            "customer_name": "Arthur Curry",
            "category": "Billing",
            "priority": "normal",
            "amount": 75.0,
            "reason": "Duplicate claim",
            "agent": "Mera",
        },
        csv_path=test_csv,
    )

    res = client.get("/ops/approvals/TCK-ACT-102/action?status=Rejected")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Ticket TCK-ACT-102 marked Rejected" in res.text

    # Verify status in tracking sheet
    pending = get_pending_approvals(csv_path=test_csv)
    assert len(pending) == 0


def test_one_click_action_invalid_status():
    res = client.get("/ops/approvals/TCK-ACT-101/action?status=InvalidStatus")
    assert res.status_code == 400
    assert "Invalid status" in res.text


def test_one_click_action_missing_ticket():
    res = client.get("/ops/approvals/TCK-DOES-NOT-EXIST/action?status=Approved")
    assert res.status_code == 404
    assert "not found" in res.text


def test_one_click_need_more_info_action(tmp_path, monkeypatch):
    test_csv = str(tmp_path / "need_more_info_action.csv")
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)

    sync_ticket_to_spreadsheet(
        {
            "ticket_id": "TCK-ACT-103",
            "customer_name": "Barry Allen",
            "category": "Billing",
            "priority": "urgent",
            "amount": 250.0,
            "reason": "Speed refund claim",
            "agent": "Cisco",
        },
        csv_path=test_csv,
    )

    res = client.get("/ops/approvals/TCK-ACT-103/action?status=needs_info")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "Ticket TCK-ACT-103 marked as needing more info" in res.text
    assert "You may close this tab" in res.text

    # Excluded from pending queue
    pending = get_pending_approvals(csv_path=test_csv)
    assert len(pending) == 0


def test_one_click_need_more_info_via_query_route(tmp_path, monkeypatch):
    test_csv = str(tmp_path / "need_more_info_query.csv")
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)

    sync_ticket_to_spreadsheet(
        {
            "ticket_id": "TCK-ACT-104",
            "customer_name": "Iris West",
            "category": "Billing",
            "priority": "normal",
            "amount": 120.0,
            "reason": "Subscription check",
            "agent": "Cisco",
        },
        csv_path=test_csv,
    )

    res = client.get(
        "/ops/approvals/action?ticket_id=TCK-ACT-104&status=need_more_info"
    )
    assert res.status_code == 200
    assert "Ticket TCK-ACT-104 marked as needing more info" in res.text


def test_action_route_dispatches_agent_info_request(tmp_path, monkeypatch):
    test_csv = str(tmp_path / "dispatch_agent_info.csv")
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)

    dispatched_calls = []

    def mock_send_agent_info(ticket, instructions=None, recipient_override=None):
        dispatched_calls.append(
            {
                "ticket_id": ticket.get("ticket_id"),
                "customer": ticket.get("customer_name"),
            }
        )
        return {"dispatched": True, "action": "Needs Info"}

    monkeypatch.setattr("app.main.send_agent_info_request_email", mock_send_agent_info)

    sync_ticket_to_spreadsheet(
        {
            "ticket_id": "TCK-ACT-105",
            "customer_name": "Wally West",
            "category": "Billing",
            "priority": "normal",
            "amount": 95.0,
            "reason": "Overcharge on account",
            "agent": "Cisco",
        },
        csv_path=test_csv,
    )

    res = client.get("/ops/approvals/TCK-ACT-105/action?status=needs_info")
    assert res.status_code == 200
    assert len(dispatched_calls) == 1
    assert dispatched_calls[0]["ticket_id"] == "TCK-ACT-105"


def test_resubmission_loop_transitions_status_back_to_pending(tmp_path, monkeypatch):
    """Verify closed-loop re-submission: pending -> needs_info -> agent update -> pending -> approved."""
    test_csv = str(tmp_path / "resubmission_loop.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)

    # 1. Ingest initial ticket
    init_res = client.post(
        "/ops/sync-ticket",
        json={
            "ticket_id": "TCK-RESUB-01",
            "customer_name": "Hal Jordan",
            "customer_email": "hal@oa.org",
            "category": "Billing",
            "priority": "urgent",
            "amount": 450.0,
            "reason": "Battery charge discrepancy",
            "agent": "Kilowog",
        },
    )
    assert init_res.status_code == 200

    # 2. Confirm it appears in pending queue
    pending_res1 = client.get("/ops/approvals/pending")
    assert pending_res1.status_code == 200
    pending_ids1 = [
        t["ticket_id"] for t in pending_res1.json().get("pending_approvals", [])
    ]
    assert "TCK-RESUB-01" in pending_ids1

    # 3. Manager requests more info
    action_res = client.get("/ops/approvals/TCK-RESUB-01/action?status=needs_info")
    assert action_res.status_code == 200
    assert "Ticket TCK-RESUB-01 marked as needing more info" in action_res.text

    # 4. Ticket is no longer in pending approvals
    pending_res2 = client.get("/ops/approvals/pending")
    pending_ids2 = [
        t["ticket_id"] for t in pending_res2.json().get("pending_approvals", [])
    ]
    assert "TCK-RESUB-01" not in pending_ids2

    # 5. Agent resubmits with invoice verification details
    resubmit_res = client.post(
        "/ops/sync-ticket",
        json={
            "ticket_id": "TCK-RESUB-01",
            "customer_name": "Hal Jordan",
            "customer_email": "hal@oa.org",
            "category": "Billing",
            "priority": "urgent",
            "amount": 450.0,
            "reason": "Verified battery charge discrepancy with energy invoice #GL-2814",
            "notes": "Agent verified transaction log and energy invoice #GL-2814",
            "agent": "Kilowog",
        },
    )
    assert resubmit_res.status_code == 200
    resub_data = resubmit_res.json()["ticket"]
    assert resub_data["status"] == "Pending"
    assert "Manager requested more info at" in resub_data["notes"]
    assert (
        "Agent verified transaction log and energy invoice #GL-2814 at"
        in resub_data["notes"]
    )

    # 6. Ticket re-appears in pending approvals
    pending_res3 = client.get("/ops/approvals/pending")
    pending_ids3 = [
        t["ticket_id"] for t in pending_res3.json().get("pending_approvals", [])
    ]
    assert "TCK-RESUB-01" in pending_ids3

    # 7. Subsequent batch digest includes the resubmitted ticket
    digest = generate_batch_digest(csv_path=test_csv)
    assert digest["has_pending"] is True
    assert "TCK-RESUB-01" in digest["body_table"]
    assert "Need More Info" in digest["html_body"]

    # 8. Manager now approves the resubmitted ticket
    approve_res = client.get("/ops/approvals/TCK-RESUB-01/action?status=Approved")
    assert approve_res.status_code == 200
    assert "Ticket TCK-RESUB-01 marked Approved" in approve_res.text

    # 9. Verify ticket leaves pending queue and keeps full audit notes
    pending_res4 = client.get("/ops/approvals/pending")
    pending_ids4 = [
        t["ticket_id"] for t in pending_res4.json().get("pending_approvals", [])
    ]
    assert "TCK-RESUB-01" not in pending_ids4


def test_resubmission_without_explicit_notes(tmp_path, monkeypatch):
    """Verify resubmission defaults to a timestamped audit note when agent passes no notes."""
    test_csv = str(tmp_path / "resubmission_no_notes.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)

    client.post(
        "/ops/sync-ticket",
        json={
            "ticket_id": "TCK-RESUB-02",
            "customer_name": "Carol Danvers",
            "category": "Billing",
            "amount": 300.0,
            "reason": "Flight charge adjustment",
            "agent": "Fury",
        },
    )

    # Mark as needing more info
    client.get("/ops/approvals/TCK-RESUB-02/action?status=needs_info")

    # Agent resubmits with only updated amount
    resubmit_res = client.post(
        "/ops/sync-ticket",
        json={
            "ticket_id": "TCK-RESUB-02",
            "customer_name": "Carol Danvers",
            "category": "Billing",
            "amount": 250.0,
            "reason": "Adjusted refund amount per policy",
            "agent": "Fury",
        },
    )
    assert resubmit_res.status_code == 200
    ticket = resubmit_res.json()["ticket"]
    assert ticket["status"] == "Pending"
    assert "Manager requested more info at" in ticket["notes"]
    assert "Agent resubmitted ticket at" in ticket["notes"]
    assert ticket["refund_amount"] == "250.00"


def test_resubmission_csv_row_integrity_with_newlines(tmp_path, monkeypatch):
    """Ensure multi-line agent notes pass through sanitize_cell and preserve single-line CSV rows."""
    test_csv = str(tmp_path / "resubmission_integrity.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)

    client.post(
        "/ops/sync-ticket",
        json={
            "ticket_id": "TCK-RESUB-03",
            "customer_name": "Clark Kent",
            "category": "Billing",
            "amount": 100.0,
            "reason": "Press pass reimbursement",
            "agent": "Lois",
        },
    )

    client.get("/ops/approvals/TCK-RESUB-03/action?status=needs_info")

    res = client.post(
        "/ops/sync-ticket",
        json={
            "ticket_id": "TCK-RESUB-03",
            "customer_name": "Clark Kent",
            "category": "Billing",
            "amount": 100.0,
            "reason": "Press pass\nreimbursement\rwith receipt",
            "notes": "Verified receipt:\nInvoice #9001\r\nApproved by editor\timmediately.",
            "agent": "Lois",
        },
    )
    assert res.status_code == 200
    ticket = res.json()["ticket"]
    assert ticket["status"] == "Pending"
    assert "\n" not in ticket["notes"]
    assert "\r" not in ticket["notes"]
    assert "\t" not in ticket["notes"]

    # Verify CSV file on disk has exactly header + 1 row (2 lines total)
    with open(test_csv, mode="r", encoding="utf-8") as f:
        lines = [line for line in f if line.strip()]
    assert len(lines) == 2
