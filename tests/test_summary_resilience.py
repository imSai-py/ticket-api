"""Tests for summary analytics resilience with unresolved tickets and helpdesk export datasets."""

from fastapi.testclient import TestClient

from app.main import app, load_tickets
from ticket_summary import compute_metrics

client = TestClient(app)


def test_summary_endpoint_with_helpdesk_export(monkeypatch):
    tickets = load_tickets("data/helpdesk_export.csv")
    assert len(tickets) == 120
    monkeypatch.setattr("app.main.TICKETS", tickets)

    resp = client.get("/summary")
    assert resp.status_code == 200
    data = resp.json()

    # 1. Total volume
    assert data["total"] == 120

    # 2. Category distributions
    by_cat = data["by_category"]
    assert by_cat["Billing"] == 33
    assert by_cat["Technical"] == 26
    assert by_cat["Shipping"] == 20
    assert by_cat["Refunds"] == 17
    assert by_cat["Login"] == 17
    assert by_cat["Account"] == 7
    assert sum(by_cat.values()) == 120

    # 3. Average resolution hours defaults cleanly when all unresolved
    assert data["average_resolution_hours"] == 0.0

    # 4. Clean enumeration of skipped tickets
    assert "skipped_tickets" in data
    skipped_missing = data["skipped_tickets"]["Unresolved / Missing resolution date"]
    assert len(skipped_missing) == 120
    assert "TCK-5007" in skipped_missing
    assert "TCK-5039" in skipped_missing


def test_compute_metrics_mixed_resolution_dataset():
    # Synthetic dataset with mixed resolved and unresolved rows
    mixed_rows = [
        {
            "ticket_id": "TCK-001",
            "category": "Billing",
            "created_at": "2026-10-01 10:00",
            "resolved_at": "2026-10-01 12:00",
            "status": "resolved",
        },
        {
            "ticket_id": "TCK-002",
            "category": "Billing",
            "created_at": "2026-10-01 11:00",
            "resolved_at": None,
            "status": "in_progress",
        },
        {
            "ticket_id": "TCK-003",
            "category": "Technical",
            "created_at": "2026-10-01 12:00",
            "resolved_at": "",
            "status": "open",
        },
    ]

    metrics, _ = compute_metrics(mixed_rows)

    assert metrics.category_counts["Billing"] == 2
    assert metrics.category_counts["Technical"] == 1
    # 2 hours resolution for TCK-001
    assert metrics.overall_average_hours() == 2.0
    assert metrics.category_average_hours()["Billing"] == 2.0
    assert metrics.category_average_hours()["Technical"] is None
    assert len(metrics.skipped_tickets["Unresolved / Missing resolution date"]) == 2
    assert "TCK-002" in metrics.skipped_tickets["Unresolved / Missing resolution date"]
    assert "TCK-003" in metrics.skipped_tickets["Unresolved / Missing resolution date"]


def test_legacy_tickets_sample_summary_backward_compatibility():
    # Verify legacy sample data metrics unchanged
    legacy_tickets = load_tickets("data/tickets_sample.csv")
    metrics, _ = compute_metrics(legacy_tickets)

    assert len(legacy_tickets) == 60
    assert metrics.overall_average_hours() == 25.27
    assert metrics.category_average_hours()["Billing"] == 37.9
    assert len(metrics.skipped_tickets["Unresolved / Missing resolution date"]) == 18
