import logging
import os
import smtplib
import sys
from email.mime.text import MIMEText
from typing import Any

from app.schemas import OpsTicketRecord
from app.tracking_sync import is_ticket_urgent

logger = logging.getLogger(__name__)


def dispatch_smtp_email(
    to_email: str,
    subject: str,
    body: str,
) -> dict[str, Any]:
    """Send real email via SMTP if credentials are configured in environment."""
    if "pytest" in sys.modules and not os.getenv("ENABLE_LIVE_SMTP_IN_TESTS"):
        return {
            "sent": False,
            "mode": "mock",
            "message": "Pytest environment detected. Real SMTP suppressed.",
        }

    smtp_host = os.getenv("SMTP_HOST")
    smtp_port_raw = os.getenv("SMTP_PORT", "587")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "alerts@company.com")

    if not smtp_host or not smtp_user or not smtp_password:
        return {
            "sent": False,
            "mode": "mock",
            "message": "SMTP credentials not configured. Dispatched in mock mode.",
        }

    try:
        port = int(smtp_port_raw)
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = to_email

        with smtplib.SMTP(smtp_host, port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, [to_email], msg.as_string())
        logger.info("Real SMTP email successfully delivered to %s", to_email)
        return {"sent": True, "mode": "smtp", "recipient": to_email}
    except (smtplib.SMTPException, OSError) as err:
        logger.error("SMTP delivery failed to %s: %s", to_email, err)
        return {"sent": False, "mode": "smtp_error", "error": str(err)}


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
        or os.getenv("ESCALATION_EMAIL")
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
    smtp_res = dispatch_smtp_email(recipient, subject, body)
    return {
        "dispatched": True,
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "ticket_id": ticket_id,
        "amount": amount,
        "alert_type": alert_type,
        "smtp": smtp_res,
    }
