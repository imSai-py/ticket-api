from fastapi.testclient import TestClient

from app.main import app
from app.tracking_sync import SpreadsheetLockedError


def test_health_check_healthy():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert data["storage"] == "accessible"
    assert data["tickets_data"] == "loaded"
    assert data["knowledge_base"] == "indexed"
    assert data["checks"]["storage"] == "accessible"
    assert data["checks"]["tickets_data"] == "loaded"
    assert data["checks"]["knowledge_base"] == "indexed"


def test_health_check_degraded_when_storage_locked(monkeypatch):
    client = TestClient(app)

    def mock_ensure():
        raise SpreadsheetLockedError(
            "Tracking spreadsheet is locked by another program."
        )

    monkeypatch.setattr("app.main.check_storage_health", mock_ensure)

    response = client.get("/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert "locked" in data["storage"].lower() or "error" in data["storage"].lower()
