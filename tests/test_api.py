from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_summary_has_categories():
    body = client.get("/summary").json()
    assert body["total"] == 60
    assert "Billing" in body["by_category"]


def test_summary_calculates_correct_resolution_average():
    body = client.get("/summary").json()
    # 42 resolved tickets with 1061.39 total hours yields 25.27 hours avg
    assert body["average_resolution_hours"] == 25.27
    assert "category_averages" in body
    assert body["category_averages"]["Billing"] == 37.9
    assert "skipped_tickets" in body
    assert len(body["skipped_tickets"]["Unresolved / Missing resolution date"]) == 18


def test_first_page_has_ten_tickets():
    body = client.get("/tickets?page=1&size=10").json()
    assert len(body) == 10
    assert body[0]["ticket_id"] == "TCK-1001"
    assert body[9]["ticket_id"] == "TCK-1010"


def test_second_page_continues_tickets():
    body = client.get("/tickets?page=2&size=10").json()
    assert len(body) == 10
    assert body[0]["ticket_id"] == "TCK-1011"


def test_default_data_path_loads():
    response = client.get("/tickets?page=1&size=1")
    assert response.status_code == 200
    assert response.json()[0]["ticket_id"] == "TCK-1001"


def test_unknown_ticket_is_404():
    assert client.get("/tickets/TCK-0000").status_code == 404


def test_legacy_frontend_month_formatting():
    # Verifies web/index.html formats months 1-indexed (d.getMonth() + 1)
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "d.getMonth() + 1" in html


def test_summary_endpoint_contract_compliance():
    # Direct contract test ensuring summary endpoint computes Day 1 metrics through HTTP interface
    response = client.get("/summary")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "average_resolution_hours" in data
    assert "category_averages" in data
    assert "skipped_tickets" in data
    assert data["average_resolution_hours"] == 25.27


def test_service_starts_cleanly_when_env_vars_unset(monkeypatch):
    # Verifies requirement 15: backend starts cleanly with unset env variables using local defaults
    monkeypatch.delenv("TICKETS_DATA_PATH", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from app.main import DEFAULT_DATA_PATH, load_tickets

    tickets = load_tickets(DEFAULT_DATA_PATH)
    assert len(tickets) == 60
    assert tickets[0]["ticket_id"] == "TCK-1001"
