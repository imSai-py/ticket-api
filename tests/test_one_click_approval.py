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
        "https://api.example.com/ops/approvals/TCK-ACT-001/action?status=Approved"
        in digest["body_table"]
    )
    assert (
        "https://api.example.com/ops/approvals/TCK-ACT-001/action?status=Rejected"
        in digest["body_table"]
    )


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
