from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_sync_ticket_rejects_negative_amount():
    response = client.post(
        "/ops/sync-ticket",
        json={"customer_name": "Alice Smith", "amount": -45.50},
    )
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data
    assert any(
        "greater than or equal to 0" in str(err) or "negative" in str(err)
        for err in (
            data["detail"] if isinstance(data["detail"], list) else [data["detail"]]
        )
    )


def test_sync_ticket_rejects_blank_customer_name():
    response = client.post(
        "/ops/sync-ticket",
        json={"customer_name": "   ", "amount": 45.50},
    )
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


def test_sync_ticket_rejects_invalid_priority():
    response = client.post(
        "/ops/sync-ticket",
        json={"customer_name": "Alice Smith", "priority": "invalid_priority"},
    )
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


def test_approval_action_rejects_blank_ticket_id():
    response = client.get("/ops/approvals/   /action?status=Approved")
    assert response.status_code == 400
    data = response.json()
    assert "ticket id" in data["detail"].lower()


def test_approval_action_rejects_invalid_status():
    response = client.get("/ops/approvals/TCK-1001/action?status=Pending")
    assert response.status_code == 400
    data = response.json()
    assert "status must be" in data["detail"].lower()
