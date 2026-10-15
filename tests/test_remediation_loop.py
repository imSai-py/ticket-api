import inspect

from fastapi.testclient import TestClient

import app.escalation as escalation_mod
import app.schemas as schemas_mod
from app.main import app as fastapi_app
from app.tracking_sync import (
    sync_ticket_to_spreadsheet,
    update_approval_status,
)

client = TestClient(fastapi_app)


def test_status_sanitization_in_csv(tmp_path, monkeypatch):
    test_csv = str(tmp_path / "test_status_sanitize.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)

    sync_ticket_to_spreadsheet(
        {
            "ticket_id": "TCK-SAN-01",
            "status": "Pending",
            "category": "Billing",
            "reason": "Valid reason",
        },
        csv_path=test_csv,
    )
    # Inject status with newline
    res = update_approval_status("TCK-SAN-01", "needs_info\r\n", csv_path=test_csv)
    assert "\r" not in res["status"]
    assert "\n" not in res["status"]
    assert res["status"] == "needs_info"


def test_approval_requires_operational_justification(tmp_path, monkeypatch):
    test_csv = str(tmp_path / "test_payout_block.csv")
    monkeypatch.setenv("OPS_TRACKING_PATH", test_csv)
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", test_csv)

    # Sync a ticket with empty reason and amount > 0
    sync_ticket_to_spreadsheet(
        {
            "ticket_id": "TCK-NO-REASON",
            "status": "Pending",
            "category": "Billing",
            "amount": 500.0,
            "reason": "",
        },
        csv_path=test_csv,
    )
    # Approving through HTTP interface without operational reason should be blocked
    res = client.get("/ops/approvals/TCK-NO-REASON/action?status=Approved")
    assert res.status_code == 400
    assert "operational justification" in res.json()["detail"].lower()


def test_send_agent_info_request_email_signature():
    sig = inspect.signature(escalation_mod.send_agent_info_request_email)
    param_names = list(sig.parameters.keys())
    assert (
        param_names[0] == "ticket_id"
    ), f"First parameter should be 'ticket_id', got {param_names[0]}"


def test_build_approval_action_urls_in_escalation():
    assert hasattr(escalation_mod, "build_approval_action_urls")
    # Verify app.schemas only re-exports it
    assert (
        schemas_mod.build_approval_action_urls
        is escalation_mod.build_approval_action_urls
    )


def test_spec_alignment_tests_use_http_boundary_exclusively():
    import tests.test_spec_alignment_verification as target_mod

    src = inspect.getsource(target_mod)
    assert (
        "_resolve_agent_recipient" not in src
    ), "Private helper _resolve_agent_recipient should not be directly imported in tests"
    assert (
        "_read_all" not in src
    ), "Private helper _read_all should not be directly imported in tests"
