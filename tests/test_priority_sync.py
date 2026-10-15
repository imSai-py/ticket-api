import pytest
from fastapi.testclient import TestClient

from app.main import app, load_tickets
from app.tracking_sync import (
    check_escalation_in_labels,
    check_vip_in_labels,
    extract_amount,
    resolve_ticket_priority_and_escalation,
    sync_ticket_to_spreadsheet,
)

client = TestClient(app)


@pytest.fixture
def temp_csv(tmp_path):
    return str(tmp_path / "test_priority_tracking.csv")


def test_label_detection_helpers():
    assert check_escalation_in_labels("escalated") is True
    assert check_escalation_in_labels("esc") is True
    assert check_escalation_in_labels("ESCALATED") is True
    assert check_escalation_in_labels("Escalated;vip") is True
    assert check_escalation_in_labels("vip") is False
    assert check_escalation_in_labels("de-escalated") is False
    assert check_escalation_in_labels("") is False
    assert check_escalation_in_labels(None) is False

    assert check_vip_in_labels("vip") is True
    assert check_vip_in_labels("VIP") is True
    assert check_vip_in_labels("Escalated;vip") is True
    assert check_vip_in_labels("escalated") is False
    assert check_vip_in_labels("vipassana") is False
    assert check_vip_in_labels("") is False
    assert check_vip_in_labels(None) is False


def test_priority_hierarchy_precedence_rules():
    # 1. Escalated / esc maps to urgent
    p, esc = resolve_ticket_priority_and_escalation(
        {"labels": "escalated", "priority": "normal"}
    )
    assert p == "urgent"
    assert esc is True

    p, esc = resolve_ticket_priority_and_escalation(
        {"labels": "esc", "priority": "low"}
    )
    assert p == "urgent"
    assert esc is True

    # 2. VIP maps to high priority
    p, esc = resolve_ticket_priority_and_escalation(
        {"labels": "vip", "priority": "normal"}
    )
    assert p == "high"
    assert esc is False

    p, esc = resolve_ticket_priority_and_escalation(
        {"labels": "VIP", "priority": "low"}
    )
    assert p == "high"
    assert esc is False

    # 3. Compound labels: escalated > vip
    p, esc = resolve_ticket_priority_and_escalation(
        {"labels": "Escalated;vip", "priority": "normal"}
    )
    assert p == "urgent"
    assert esc is True

    p, esc = resolve_ticket_priority_and_escalation(
        {"labels": "vip;esc", "priority": "normal"}
    )
    assert p == "urgent"
    assert esc is True

    # 4. VIP on ticket that is already urgent preserves urgent
    p, esc = resolve_ticket_priority_and_escalation(
        {"labels": "vip", "priority": "urgent"}
    )
    assert p == "urgent"
    assert esc is True

    # 5. Empty labels retains original priority
    p, esc = resolve_ticket_priority_and_escalation({"labels": "", "priority": "low"})
    assert p == "low"
    assert esc is False


def test_extract_amount_defaults_to_usd():
    assert extract_amount("480") == (480.0, "")
    assert extract_amount("100.50") == (100.5, "")
    assert extract_amount("refund amount: 250") == (250.0, "")
    assert extract_amount("$1,250.00") == (1250.0, "")
    assert extract_amount("50 dollars") == (50.0, "")
    assert extract_amount("") == (0.0, "Needs amount verification")


def test_sync_ticket_priority_hierarchy_and_refund_usd(temp_csv):
    # Ticket with escalated label
    ticket_esc = {
        "ticket_id": "TCK-2001",
        "labels": "escalated",
        "refund_amount": "480",
        "customer_email": "omar.ali@example.com",
    }
    row_esc = sync_ticket_to_spreadsheet(ticket_esc, csv_path=temp_csv)
    assert row_esc["priority"] == "urgent"
    assert row_esc["escalated"] == "True"
    assert row_esc["amount"] == "480.00"
    assert row_esc["customer_name"] == "omar.ali@example.com"

    # Ticket with vip label
    ticket_vip = {
        "ticket_id": "TCK-2002",
        "labels": "vip",
        "refund_amount": 150,
        "customer_email": "vip.client@example.com",
    }
    row_vip = sync_ticket_to_spreadsheet(ticket_vip, csv_path=temp_csv)
    assert row_vip["priority"] == "high"
    assert row_vip["escalated"] == "False"
    assert row_vip["amount"] == "150.00"
    assert row_vip["customer_name"] == "vip.client@example.com"

    # Ticket with compound label (Escalated;vip)
    ticket_compound = {
        "ticket_id": "TCK-2003",
        "labels": "Escalated;vip",
        "refund_amount": "200.00",
        "customer_name": "Sarah Connor",
        "customer_email": "sarah@example.com",
    }
    row_compound = sync_ticket_to_spreadsheet(ticket_compound, csv_path=temp_csv)
    assert row_compound["priority"] == "urgent"
    assert row_compound["escalated"] == "True"
    assert row_compound["amount"] == "200.00"
    assert row_compound["customer_name"] == "Sarah Connor"
    assert "email: sarah@example.com" in row_compound["notes"]


def test_post_ops_sync_ticket_alert_behavior_with_labels(temp_csv):
    # 1. Escalated triggers alert
    resp_esc = client.post(
        "/ops/sync-ticket",
        json={
            "ticket_id": "TCK-2010",
            "customer_name": "Test Escalation",
            "labels": "escalated",
            "refund_amount": "300",
        },
    )
    assert resp_esc.status_code == 200
    data_esc = resp_esc.json()
    assert data_esc["ticket"]["priority"] == "urgent"
    assert data_esc["ticket"]["escalated"] == "True"
    assert data_esc["ticket"]["amount"] == "300.00"
    assert data_esc["escalation_alert"]["dispatched"] is True

    # 2. VIP does not trigger urgent escalation alert
    resp_vip = client.post(
        "/ops/sync-ticket",
        json={
            "ticket_id": "TCK-2011",
            "customer_name": "Test VIP",
            "labels": "vip",
            "refund_amount": "120",
        },
    )
    assert resp_vip.status_code == 200
    data_vip = resp_vip.json()
    assert data_vip["ticket"]["priority"] == "high"
    assert data_vip["ticket"]["escalated"] == "False"
    assert data_vip["ticket"]["amount"] == "120.00"
    assert data_vip["escalation_alert"]["dispatched"] is False


def test_sync_records_from_helpdesk_export_file(temp_csv):
    tickets = load_tickets("data/helpdesk_export.csv")
    assert len(tickets) == 120

    # TCK-5007: escalated, 480 refund, omar.ali@example.com
    t5007 = next(t for t in tickets if t["ticket_id"] == "TCK-5007")
    synced_5007 = sync_ticket_to_spreadsheet(t5007, csv_path=temp_csv)
    assert synced_5007["priority"] == "urgent"
    assert synced_5007["escalated"] == "True"
    assert synced_5007["amount"] == "480.00"
    assert synced_5007["customer_name"] == "omar.ali@example.com"

    # TCK-5041: esc, 80 refund, max.obi@example.com
    t5041 = next(t for t in tickets if t["ticket_id"] == "TCK-5041")
    synced_5041 = sync_ticket_to_spreadsheet(t5041, csv_path=temp_csv)
    assert synced_5041["priority"] == "urgent"
    assert synced_5041["escalated"] == "True"
    assert synced_5041["amount"] == "80.00"
    assert synced_5041["customer_name"] == "max.obi@example.com"
