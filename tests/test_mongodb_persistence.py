"""Tests for MongoDB Atlas persistence layer and integration."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db import (
    _clean_doc,
    check_mongodb_health,
    clear_tracking_records,
    fetch_all_tickets,
    fetch_all_tracking_records,
    fetch_ticket_by_id,
    get_max_ticket_number_from_db,
    is_mongodb_enabled,
    upsert_ticket,
    upsert_tickets_batch,
    upsert_tracking_record,
    upsert_tracking_records_batch,
)
from app.main import app


def test_is_mongodb_enabled_toggle(monkeypatch):
    """Verify is_mongodb_enabled responds correctly to environment flags."""
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.delenv("MONGO_URI", raising=False)
    assert is_mongodb_enabled() is False

    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017")
    monkeypatch.setenv("TEST_USE_MONGODB", "1")
    assert is_mongodb_enabled() is True

    monkeypatch.setenv("DISABLE_MONGODB", "1")
    assert is_mongodb_enabled() is False


def test_clean_doc_serializes_primitives_and_datetimes():
    """Verify _clean_doc strips _id and normalizes datetimes to ISO format."""
    now = datetime(2026, 10, 21, 10, 30, 0, tzinfo=UTC)
    raw = {
        "_id": "6715f8a00000000000000001",
        "ticket_id": "TCK-1001",
        "created_at": now,
        "amount": 150.50,
        "tags": ("vip", "billing"),
        "meta": {"nested_dt": now, "flag": True},
    }
    clean = _clean_doc(raw)
    assert "_id" not in clean
    assert clean["ticket_id"] == "TCK-1001"
    assert clean["created_at"] == now.isoformat()
    assert clean["amount"] == 150.50
    assert clean["tags"] == ["vip", "billing"]
    assert clean["meta"]["nested_dt"] == now.isoformat()
    assert clean["meta"]["flag"] is True


def test_mongodb_health_disabled_when_unconfigured(monkeypatch):
    """Verify health returns disabled when MongoDB is not active."""
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.delenv("MONGO_URI", raising=False)
    ok, msg = check_mongodb_health()
    assert ok is False
    assert msg == "disabled"


def test_mongodb_health_connected_with_mock_client(monkeypatch):
    """Verify health returns connected when ping probe succeeds."""
    mock_client = MagicMock()
    mock_client.admin.command.return_value = {"ok": 1}

    monkeypatch.setattr("app.db.is_mongodb_enabled", lambda: True)
    monkeypatch.setattr("app.db.get_mongodb_client", lambda: mock_client)

    ok, msg = check_mongodb_health()
    assert ok is True
    assert msg == "connected"
    mock_client.admin.command.assert_called_once_with("ping")


def test_fetch_all_tickets_with_mock_db(monkeypatch):
    """Verify fetch_all_tickets parses timestamps and normalizes aliases."""
    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find.return_value = [
        {
            "ticket_id": "TCK-2001",
            "created_at": "2026-10-15T12:00:00Z",
            "category": "Billing",
            "priority": "urgent",
            "status": "open",
            "labels": "escalated",
            "refund_amount": "250.00",
        }
    ]

    monkeypatch.setattr("app.db.get_db", lambda: mock_db)
    tickets = fetch_all_tickets()
    assert len(tickets) == 1
    t = tickets[0]
    assert t["ticket_id"] == "TCK-2001"
    assert t["created"] is not None
    assert t["tags"] == "escalated"
    assert t["refund_amount"] == 250.00


def test_fetch_ticket_by_id_with_mock_db(monkeypatch):
    """Verify fetch_ticket_by_id retrieves ticket and handles alias mapping."""
    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find_one.return_value = {
        "ticket_id": "TCK-3001",
        "created_at": "2026-10-16T14:30:00Z",
        "category": "Refunds",
        "priority": "high",
        "status": "Pending",
        "customer_email": "user@example.com",
    }

    monkeypatch.setattr("app.db.get_db", lambda: mock_db)
    doc = fetch_ticket_by_id("TCK-3001")
    assert doc is not None
    assert doc["ticket_id"] == "TCK-3001"
    assert doc["requester_email"] == "user@example.com"


def test_upsert_ticket_and_batch_with_mock_db(monkeypatch):
    """Verify upsert_ticket and upsert_tickets_batch execute update queries."""
    mock_db = MagicMock()
    monkeypatch.setattr("app.db.get_db", lambda: mock_db)

    # Single upsert
    res = upsert_ticket({"ticket_id": "TCK-4001", "status": "Pending"})
    assert res["ticket_id"] == "TCK-4001"
    mock_db["tickets"].update_one.assert_called_once()

    # Batch upsert
    upsert_tickets_batch(
        [
            {"ticket_id": "TCK-4002", "status": "Pending"},
            {"ticket_id": "TCK-4003", "status": "Approved"},
        ]
    )
    mock_db["tickets"].bulk_write.assert_called_once()


def test_tracking_records_crud_with_mock_db(monkeypatch):
    """Verify tracking records fetch, upsert, batch, and clear operations."""
    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find.return_value = [
        {
            "ticket_id": "TCK-5001",
            "created_at": "2026-10-20 10:00:00",
            "status": "Pending",
            "priority": "urgent",
            "category": "Billing",
            "assigned_to": "Sai",
            "refund_amount": "120.00",
        }
    ]
    mock_delete = MagicMock()
    mock_delete.deleted_count = 5
    mock_db.__getitem__.return_value.delete_many.return_value = mock_delete

    monkeypatch.setattr("app.db.get_db", lambda: mock_db)

    # 1. Fetch
    rows = fetch_all_tracking_records()
    assert len(rows) == 1
    assert rows[0]["agent"] == "Sai"
    assert rows[0]["amount"] == "120.00"

    # 2. Upsert single
    upsert_tracking_record({"ticket_id": "TCK-5002", "status": "Approved"})
    mock_db["tracking_records"].update_one.assert_called_once()

    # 3. Upsert batch
    upsert_tracking_records_batch(
        [{"ticket_id": "TCK-5003"}, {"ticket_id": "TCK-5004"}]
    )
    mock_db["tracking_records"].bulk_write.assert_called_once()

    # 4. Clear
    deleted = clear_tracking_records()
    assert deleted == 5
    mock_db["tracking_records"].delete_many.assert_called_once_with({})


def test_get_max_ticket_number_from_db_with_mock_db(monkeypatch):
    """Verify get_max_ticket_number_from_db extracts highest number correctly."""
    mock_db = MagicMock()
    mock_tickets_coll = MagicMock()
    mock_tickets_coll.find.return_value = [
        {"ticket_id": "TCK-1050"},
        {"ticket_id": "TCK-5007"},
    ]
    mock_tracking_coll = MagicMock()
    mock_tracking_coll.find.return_value = [
        {"ticket_id": "TCK-5012"},
        {"ticket_id": "TCK-2000"},
    ]

    def get_coll(name):
        return mock_tickets_coll if name == "tickets" else mock_tracking_coll

    mock_db.__getitem__.side_effect = get_coll
    monkeypatch.setattr("app.db.get_db", lambda: mock_db)

    max_num = get_max_ticket_number_from_db()
    assert max_num == 5012


def test_health_check_includes_mongodb_when_enabled(monkeypatch):
    """Verify GET /health includes mongodb probe status when MongoDB is enabled."""
    monkeypatch.setattr("app.db.is_mongodb_enabled", lambda: True)
    monkeypatch.setattr("app.db.check_mongodb_health", lambda: (True, "connected"))

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["mongodb"] == "connected"


def test_live_mongodb_persistence_across_app_restart():
    """Live Atlas integration test verifying data persists across client restarts."""
    import os

    from app.db import (
        close_mongodb_client,
        fetch_all_tracking_records,
        fetch_ticket_by_id,
        get_db,
        get_mongodb_uri,
        upsert_ticket,
        upsert_tracking_record,
    )

    uri = get_mongodb_uri()
    if not uri:
        pytest.skip("No live MONGODB_URI configured for integration testing.")

    os.environ["TEST_USE_MONGODB"] = "1"
    try:
        test_tid = "TCK-TEST-PERSIST-9999"

        # 1. Write ticket and tracking record to Atlas
        ticket_data = {
            "ticket_id": test_tid,
            "created_at": "2026-10-21T10:00:00Z",
            "category": "Billing",
            "priority": "urgent",
            "status": "Pending",
            "customer_email": "atlas_test@example.com",
            "refund_amount": "399.00",
            "reason": "MongoDB Atlas persistence test",
        }
        upsert_ticket(ticket_data)
        upsert_tracking_record(ticket_data)

        # 2. Simulate application restart: completely close connection pool and reset memory
        close_mongodb_client()

        # 3. Re-open connection (fresh client instance) and verify data is stored
        restored_ticket = fetch_ticket_by_id(test_tid)
        assert restored_ticket is not None
        assert restored_ticket["ticket_id"] == test_tid
        assert restored_ticket["category"] == "Billing"
        assert restored_ticket["refund_amount"] == 399.00

        all_tracking = fetch_all_tracking_records()
        matching_tracking = [r for r in all_tracking if r.get("ticket_id") == test_tid]
        assert len(matching_tracking) == 1
        assert matching_tracking[0]["ticket_id"] == test_tid
        assert matching_tracking[0]["status"] == "Pending"

        # 4. Cleanup test documents from Atlas
        db = get_db()
        if db is not None:
            db["tickets"].delete_one({"ticket_id": test_tid})
            db["tracking_records"].delete_one({"ticket_id": test_tid})
    finally:
        os.environ.pop("TEST_USE_MONGODB", None)
        close_mongodb_client()
