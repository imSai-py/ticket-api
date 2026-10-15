from fastapi.testclient import TestClient

from app import tracking_sync
from app.main import app
from app.schemas import ApprovalStatusEnum

client = TestClient(app, raise_server_exceptions=False)


def test_health_payload_schema_has_flat_subsystem_keys():
    """Spec fix: GET /health must provide top-level subsystem keys as specified."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "1.0.0"
    assert data["storage"] == "accessible"
    assert data["tickets_data"] == "loaded"
    assert data["knowledge_base"] == "indexed"


def test_request_validation_error_handler_formats_concise_string():
    """Spec fix: RequestValidationError must return a concise, readable detail string."""
    response = client.post(
        "/ops/sync-ticket",
        json={"customer_name": "Alice Smith", "amount": -100.0},
    )
    assert response.status_code == 422
    data = response.json()
    assert isinstance(data["detail"], str)
    assert "validation" in data["detail"].lower() or "amount" in data["detail"].lower()


def test_catch_all_exception_handler_returns_clean_500(monkeypatch):
    """Spec fix: Unhandled exceptions return clean HTTP 500 without leaking stack traces."""

    def crash_metrics(_tickets):
        raise RuntimeError("Simulated internal database crash")

    monkeypatch.setattr("app.main.compute_metrics", crash_metrics)

    response = client.get("/summary")
    assert response.status_code == 500
    data = response.json()
    assert "detail" in data
    assert "internal server error" in data["detail"].lower()
    assert "Simulated internal database crash" not in data["detail"]


def test_ops_tracking_path_env_var_support(monkeypatch):
    """Standards fix: OPS_TRACKING_PATH from .env.example must be read by tracking_sync."""
    test_path = "custom/test_ops.csv"
    monkeypatch.setenv("OPS_TRACKING_PATH", test_path)
    resolved = tracking_sync.get_ops_tracking_path()
    assert test_path in resolved or resolved.endswith("test_ops.csv")


def test_approval_status_enum_values():
    """Standards fix: Approval status values must be governed by ApprovalStatusEnum."""
    assert ApprovalStatusEnum.APPROVED == "Approved"
    assert ApprovalStatusEnum.REJECTED == "Rejected"
    assert ApprovalStatusEnum.PENDING == "Pending"
