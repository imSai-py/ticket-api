"""Tests for automated ticket intake extraction and auto-populate (Issue #41)."""

from fastapi.testclient import TestClient

from app.intake_extraction import (
    extract_agent_context,
    extract_customer_identity,
    extract_operational_reason_with_fallback,
    extract_or_generate_subject,
)
from app.main import app

client = TestClient(app)


def test_extract_customer_name_from_introduction():
    """Extract customer name when introduced via 'My name is ...'."""
    text = "Hello support, my name is Marcus Brody and I cannot sign in to my account."
    name, email = extract_customer_identity(text)
    assert name == "Marcus Brody"
    assert email is None


def test_extract_customer_name_from_signoff():
    """Extract customer name from standard email signoff."""
    text = (
        "Please reset my password as soon as possible.\n\nBest regards,\nSarah Jenkins"
    )
    name, _email = extract_customer_identity(text)
    assert name == "Sarah Jenkins"


def test_extract_customer_email_from_text():
    """Extract customer email address from customer query text."""
    text = (
        "Please reach back out to me at sarah.jenkins@example.org regarding this issue."
    )
    name, email = extract_customer_identity(text)
    assert email == "sarah.jenkins@example.org"
    assert name == "Customer"  # Safe default when no explicit name is stated


def test_extract_customer_fallback_to_default_customer():
    """Ensure safe fallback to 'Customer' when no name or sender can be identified."""
    text = "The system is throwing a 500 internal server error when uploading files."
    name, email = extract_customer_identity(text)
    assert name == "Customer"
    assert email is None


def test_extract_customer_preserves_explicitly_provided_name():
    """Explicitly supplied customer name takes highest precedence."""
    text = "My name is John Doe, but use my company record."
    name, email = extract_customer_identity(
        text, provided_name="Alice Smith", provided_email="alice@company.com"
    )
    assert name == "Alice Smith"
    assert email == "alice@company.com"


def test_extract_agent_context_from_header():
    """Agent context extracts from session/auth header when present."""
    agent = extract_agent_context(header_agent="Elena Rostova", provided_agent=None)
    assert agent == "Elena Rostova"


def test_extract_agent_context_defaults_to_sai():
    """Agent context defaults cleanly to 'Sai' when unauthenticated."""
    agent = extract_agent_context(header_agent=None, provided_agent=None)
    assert agent == "Sai"


def test_extract_or_generate_subject_preserves_existing():
    """Existing subject is preserved intact."""
    subj = extract_or_generate_subject(
        "I need a refund for $150", provided_subject="Invoice #8841 Overcharge"
    )
    assert subj == "Invoice #8841 Overcharge"


def test_extract_or_generate_subject_synthesizes_refund_title():
    """Synthesizes concise subject when customer omits subject line."""
    text = "I was double charged $99.00 on my credit card for the annual plan renewal. Please refund."
    subj = extract_or_generate_subject(text, provided_subject=None)
    assert "Refund" in subj or "Charge" in subj
    words = subj.split()
    assert 2 <= len(words) <= 10


def test_extract_or_generate_subject_synthesizes_password_title():
    """Synthesizes concise subject for password issues."""
    text = "I forgot my password and cannot log into my workspace account."
    subj = extract_or_generate_subject(text, provided_subject=None)
    assert "Password" in subj or "Account" in subj


def test_extract_operational_reason_with_fallback():
    """Derives clean operational root cause for spreadsheet justification."""
    reason = extract_operational_reason_with_fallback(
        "Overcharge", "I was charged twice on invoice INV-2024-99", category="Billing"
    )
    assert "Double charge" in reason or "INV-2024-99" in reason


def test_post_triage_extract_endpoint_success():
    """Verify HTTP endpoint POST /triage/extract returns complete auto-populated metadata."""
    payload = {
        "text": "Hello, my name is David Miller. I noticed a double charge of $120.00 on order #7712. Please process a refund to my original payment method at david.miller@example.com.",
        "subject": "",
    }
    response = client.post(
        "/triage/extract",
        json=payload,
        headers={"X-Agent-Name": "Sai"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["customer_name"] == "David Miller"
    assert data["customer_email"] == "david.miller@example.com"
    assert data["agent"] == "Sai"
    assert "Refund" in data["subject"] or "Charge" in data["subject"]
    assert (
        "Double charge" in data["operational_reason"]
        or "7712" in data["operational_reason"]
    )
    assert data["category"] in ("Billing", "Refunds")
    assert data["refund_amount"] == 120.00
    assert "customer_name" in data["auto_populated_fields"]
    assert "operational_reason" in data["auto_populated_fields"]


def test_post_triage_extract_endpoint_safe_fallbacks():
    """Verify HTTP endpoint falls back cleanly when customer identity is absent."""
    payload = {
        "text": "The mobile app is crashing on the splash screen after the latest update.",
    }
    response = client.post("/triage/extract", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["customer_name"] == "Customer"
    assert data["customer_email"] is None
    assert data["agent"] == "Sai"
    assert len(data["subject"]) > 0
    assert data["category"] == "Technical"
    assert data["priority"] in ("urgent", "high", "normal", "low")


def test_post_triage_extract_validation_rejects_empty_input():
    """Empty or whitespace text triggers HTTP 422 Unprocessable Entity."""
    response = client.post("/triage/extract", json={"text": "   "})
    assert response.status_code == 422


def test_triage_endpoint_includes_operational_reason():
    """Verify standard POST /triage returns operational_reason."""
    response = client.post(
        "/triage",
        json={
            "subject": "Duplicate subscription payment",
            "text": "I was charged twice for order #9921",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "operational_reason" in data
    assert data["operational_reason"] is not None
