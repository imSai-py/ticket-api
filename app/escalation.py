import os
from typing import Any


def send_escalation_alert(
    ticket: dict[str, Any], recipient_override: str | None = None
) -> dict[str, Any]:
    """Dispatch an instant alert for urgent escalated tickets directly to the manager inbox."""
    is_urgent = (
        ticket.get("priority") == "urgent"
        or str(ticket.get("escalated", "")).lower() == "true"
        or ticket.get("escalated") is True
    )
    if not is_urgent:
        return {"dispatched": False, "reason": "Not an urgent ticket"}

    recipient = (
        recipient_override
        or os.getenv("ESCALATION_MANAGER_EMAIL")
        or "manager@company.com"
    )
    ticket_id = ticket.get("ticket_id", "Unknown")
    customer = ticket.get("customer_name", "Unknown")
    category = ticket.get("category", "Billing")
    amount = float(ticket.get("amount") or 0.0)
    reason = ticket.get("reason", "No reason provided")

    subject = f"[URGENT ESCALATION] Ticket {ticket_id} - {customer}"
    body = (
        "========================================\n"
        "URGENT TICKET ESCALATED FOR MANAGEMENT\n"
        "========================================\n"
        f"Ticket ID:     {ticket_id}\n"
        f"Customer:      {customer}\n"
        f"Category:      {category}\n"
        f"Amount:        ${amount:.2f}\n"
        f"Reason:        {reason}\n\n"
        "ACTION REQUIRED: Immediate management review and approval required.\n"
    )

    return {
        "dispatched": True,
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "ticket_id": ticket_id,
    }
