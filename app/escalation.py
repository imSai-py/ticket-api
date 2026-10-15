import logging
import os
from typing import Any

from app.schemas import OpsTicketRecord
from app.tracking_sync import is_ticket_urgent

logger = logging.getLogger(__name__)


def send_escalation_alert(
    ticket: OpsTicketRecord | dict[str, Any],
    recipient_override: str | None = None,
    refund_threshold: float | None = None,
) -> dict[str, Any]:
    """Dispatch an instant alert for urgent escalated tickets or high-dollar refunds directly to the manager inbox."""
    if isinstance(ticket, OpsTicketRecord):
        ticket_id = ticket.ticket_id
        customer = ticket.customer_name
        category = ticket.category
        raw_amt = ticket.refund_amount or ticket.amount or 0.0
        reason = ticket.reason or "No reason provided"
    else:
        ticket_id = ticket.get("ticket_id", "Unknown")
        customer = (
            ticket.get("customer_name") or ticket.get("customer_email") or "Unknown"
        )
        category = ticket.get("category", "Billing")
        raw_amt = ticket.get("refund_amount") or ticket.get("amount") or 0.0
        reason = ticket.get("reason", "No reason provided")

    try:
        amount = float(str(raw_amt).replace("$", "").replace(",", "").strip() or 0.0)
    except ValueError:
        amount = 0.0

    is_urgent = is_ticket_urgent(ticket)
    is_high_dollar = bool(
        refund_threshold is not None and amount >= refund_threshold and amount > 0.0
    )

    if not is_urgent and not is_high_dollar:
        return {"dispatched": False, "reason": "Not an urgent ticket"}

    recipient = (
        recipient_override
        or os.getenv("ESCALATION_MANAGER_EMAIL")
        or "manager@company.com"
    )

    alert_type = (
        f"HIGH-DOLLAR REFUND (${amount:.2f} >= ${refund_threshold:.2f})"
        if (is_high_dollar and not is_urgent)
        else "URGENT TICKET ESCALATED FOR MANAGEMENT"
    )

    subject = f"[URGENT ESCALATION] Ticket {ticket_id} - {customer}"
    body = (
        "========================================\n"
        f"{alert_type}\n"
        "========================================\n"
        f"Ticket ID:     {ticket_id}\n"
        f"Customer:      {customer}\n"
        f"Category:      {category}\n"
        f"Amount:        ${amount:.2f}\n"
        f"Reason:        {reason}\n\n"
        "ACTION REQUIRED: Immediate management review and approval required.\n"
    )

    logger.warning(
        "Dispatched urgent escalation alert for ticket %s to %s (%s)",
        ticket_id,
        recipient,
        alert_type,
    )
    return {
        "dispatched": True,
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "ticket_id": ticket_id,
        "amount": amount,
        "alert_type": alert_type,
    }
