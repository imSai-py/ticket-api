import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_tracking_sheet(tmp_path, monkeypatch):
    test_csv = str(tmp_path / "test_api_tracking.csv")
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)
    return test_csv


def test_post_ops_sync_ticket():
    payload = {
        "ticket_id": "TCK-5001",
        "customer_name": "Carol Danvers",
        "category": "Billing",
        "priority": "normal",
        "amount": 80.0,
        "reason": "Duplicate subscription charge",
        "agent": "Dan",
    }
    response = client.post("/ops/sync-ticket", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["ticket"]["ticket_id"] == "TCK-5001"
    assert data["ticket"]["status"] == "Pending"
    assert float(data["ticket"]["amount"]) == 80.0

    pending_res = client.get("/ops/approvals/pending")
    assert pending_res.status_code == 200
    pending_data = pending_res.json()
    assert pending_data["pending_count"] == 1
    assert pending_data["pending_approvals"][0]["ticket_id"] == "TCK-5001"


def test_triage_auto_syncs_billing_ticket(monkeypatch):
    from app.schemas import CategoryEnum, PriorityEnum, TriageResponse

    monkeypatch.setattr(
        "app.main.classify_and_reply",
        lambda subject, text, matched_articles=None: TriageResponse(
            category=CategoryEnum.BILLING,
            priority=PriorityEnum.NORMAL,
            suggested_reply="We have verified your billing issue.",
            article_ids=["KB-001"],
        ),
    )

    triage_req = {
        "subject": "Overcharge on subscription",
        "text": "I was billed $45.00 twice for this month plan.",
    }
    response = client.post("/triage", json=triage_req)
    assert response.status_code == 200

    pending_res = client.get("/ops/approvals/pending")
    assert pending_res.status_code == 200
    pending = pending_res.json()["pending_approvals"]
    assert len(pending) == 1
    assert pending[0]["category"] == "Billing"
    assert float(pending[0]["amount"]) == 45.00


def test_sync_ticket_with_explicit_escalated_flag():
    payload = {
        "ticket_id": "TCK-SYNC-FLAG",
        "customer_name": "VIP Client",
        "category": "Billing",
        "priority": "normal",
        "amount": 25.0,
        "escalated": True,
    }
    res = client.post("/ops/sync-ticket", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["ticket"]["escalated"] == "True"
    assert data["escalation_alert"]["dispatched"] is True


def test_sync_ticket_returns_423_when_spreadsheet_locked(monkeypatch):
    from app.tracking_sync import SpreadsheetLockedError

    def mock_sync(*args, **kwargs):
        raise SpreadsheetLockedError("File is locked by Excel")

    monkeypatch.setattr("app.main.sync_ticket_to_spreadsheet", mock_sync)

    payload = {
        "ticket_id": "TCK-LOCK-HTTP",
        "customer_name": "Lock Test",
        "category": "Billing",
        "priority": "normal",
        "amount": 50.0,
    }
    res = client.post("/ops/sync-ticket", json=payload)
    assert res.status_code == 423
    assert "File is locked by Excel" in res.json()["detail"]
