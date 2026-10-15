import logging
import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from app.schemas import OpsTicketRecord
from app.tracking_sync import is_ticket_urgent

logger = logging.getLogger(__name__)


def is_billing_category(category: Any) -> bool:
    """Return True if category is within the client billing/refund scope."""
    val = str(getattr(category, "value", category) or "").strip().lower()
    return "billing" in val or "refund" in val


def dispatch_smtp_email(
    to_email: str,
    subject: str,
    body: str,
    html_body: str | None = None,
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
        if html_body:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = smtp_from
            msg["To"] = to_email
            msg.attach(MIMEText(body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))
        else:
            msg = MIMEText(body, "plain", "utf-8")
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
    dispatch_smtp: bool = True,
) -> dict[str, Any]:
    """Dispatch an alert for urgent escalated tickets or high-dollar refunds directly to the manager inbox."""
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

    # Scope rule: only Billing/Refund tickets trigger manager escalation alerts
    if not is_billing_category(category):
        return {
            "dispatched": False,
            "reason": f"Non-billing category '{category}' outside current escalation scope",
            "ticket_id": ticket_id,
        }

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

    base_url = (os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/")
    approve_url = f"{base_url}/ops/approvals/{ticket_id}/action?status=Approved"
    reject_url = f"{base_url}/ops/approvals/{ticket_id}/action?status=Rejected"
    need_info_url = f"{base_url}/ops/approvals/{ticket_id}/action?status=needs_info"

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
        "ACTION REQUIRED: Immediate management review and approval required.\n\n"
        f"Approve:        {approve_url}\n"
        f"Reject:         {reject_url}\n"
        f"Need More Info: {need_info_url}\n"
    )

    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px; color: #1e293b; }}
    .card {{ background-color: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; max-width: 580px; margin: 0 auto; padding: 28px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }}
    .header {{ border-bottom: 2px solid #ef4444; padding-bottom: 12px; margin-bottom: 18px; }}
    .title {{ color: #dc2626; font-size: 18px; font-weight: bold; margin: 0; }}
    .desc {{ color: #475569; font-size: 14px; margin: 0 0 16px 0; }}
    .table {{ width: 100%; border-collapse: collapse; margin-bottom: 24px; }}
    .table td {{ padding: 10px 12px; border-bottom: 1px solid #f1f5f9; font-size: 14px; }}
    .label {{ font-weight: 600; color: #64748b; width: 130px; }}
    .value {{ font-weight: 500; color: #0f172a; }}
    .amount-highlight {{ color: #dc2626; font-weight: bold; font-size: 16px; }}
    .actions {{ text-align: center; padding-top: 16px; border-top: 1px solid #e2e8f0; }}
    .btn {{ display: inline-block; padding: 12px 24px; font-size: 14px; font-weight: bold; text-decoration: none; border-radius: 6px; margin: 0 6px; }}
    .footer {{ margin-top: 24px; font-size: 12px; color: #94a3b8; text-align: center; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <h2 class="title">🚨 {alert_type}</h2>
    </div>
    <p class="desc">A high-priority billing escalation requires your immediate review and approval.</p>
    <table class="table">
      <tr><td class="label">Ticket ID:</td><td class="value"><strong>{ticket_id}</strong></td></tr>
      <tr><td class="label">Customer:</td><td class="value">{customer}</td></tr>
      <tr><td class="label">Category:</td><td class="value">{category}</td></tr>
      <tr><td class="label">Amount:</td><td class="value"><span class="amount-highlight">${amount:.2f}</span></td></tr>
      <tr><td class="label">Reason:</td><td class="value">{reason}</td></tr>
    </table>
    <div class="actions">
      <a href="{approve_url}" class="btn" style="background-color: #16a34a; color: #ffffff !important; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block; margin-right: 8px;">✅ Approve</a>
      <a href="{reject_url}" class="btn" style="background-color: #dc2626; color: #ffffff !important; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block; margin-right: 8px;">❌ Reject</a>
      <a href="{need_info_url}" class="btn" style="background-color: #d97706; color: #ffffff !important; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">⚠️ Need Info</a>
    </div>
    <div class="footer">
      Automated operations alert &bull; Bitcot Operations System
    </div>
  </div>
</body>
</html>"""

    if dispatch_smtp:
        logger.warning(
            "Dispatched urgent escalation alert for ticket %s to %s (%s)",
            ticket_id,
            recipient,
            alert_type,
        )
        smtp_res = dispatch_smtp_email(recipient, subject, body, html_body=html_body)
    else:
        smtp_res = {
            "sent": False,
            "mode": "batch_digest_deferred",
            "message": "Individual email suppressed in favor of consolidated digest.",
        }

    return {
        "dispatched": True,
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "html_body": html_body,
        "ticket_id": ticket_id,
        "amount": amount,
        "alert_type": alert_type,
        "smtp": smtp_res,
        "approve_url": approve_url,
        "reject_url": reject_url,
    }


def send_agent_action_notification(
    ticket: dict[str, Any],
    action: str,
    recipient_override: str | None = None,
) -> dict[str, Any]:
    """Notify the assigned support agent and manager that an approval decision has been made."""
    ticket_id = ticket.get("ticket_id", "Unknown")
    customer = ticket.get("customer_name") or ticket.get("customer_email") or "Customer"
    assigned_to = ticket.get("assigned_to") or ticket.get("agent") or "Support Team"
    amount = ticket.get("refund_amount") or ticket.get("amount") or "0.00"
    reason = ticket.get("reason") or "Operational review"

    recipient = (
        recipient_override
        or os.getenv("AGENT_NOTIFICATIONS_EMAIL")
        or os.getenv("ESCALATION_MANAGER_EMAIL")
        or f"{str(assigned_to).lower()}@company.com"
    )

    action_lower = action.lower()
    if action_lower in ("approved", "approve"):
        action_verb = "APPROVED"
        badge_color = "#16a34a"
        next_step = (
            f"You are authorized to execute the refund of ${amount} to {customer}."
        )
    elif action_lower in (
        "needs info",
        "need info",
        "need more info",
        "needs more info",
        "needs_info",
    ):
        action_verb = "MORE INFO REQUESTED"
        badge_color = "#d97706"
        next_step = f"Manager requires more information. Please contact {customer} to gather necessary verification details and update the ticket."
    else:
        action_verb = "REJECTED"
        badge_color = "#dc2626"
        next_step = f"Do not issue a refund. Please contact {customer} to communicate the rejection."

    subject = f"[DECISION: {action_verb}] Ticket {ticket_id} - {customer} (${amount})"
    body = (
        f"========================================\n"
        f"DECISION NOTIFICATION: Ticket {ticket_id}\n"
        f"========================================\n"
        f"Status:       {action_verb}\n"
        f"Customer:     {customer}\n"
        f"Amount:       ${amount}\n"
        f"Assigned To:  {assigned_to}\n"
        f"Reason:       {reason}\n\n"
        f"NEXT STEP: {next_step}\n"
    )

    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 20px; }}
    .card {{ background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; max-width: 560px; margin: 0 auto; padding: 24px; }}
    .badge {{ display: inline-block; padding: 6px 12px; border-radius: 4px; color: #ffffff; font-weight: bold; background: {badge_color}; }}
    .table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
    .table td {{ padding: 8px 10px; border-bottom: 1px solid #f1f5f9; font-size: 13px; }}
    .next-box {{ background: #f1f5f9; border-left: 4px solid {badge_color}; padding: 12px; margin-top: 16px; font-size: 13px; }}
  </style>
</head>
<body>
  <div class="card">
    <div style="margin-bottom: 12px;">
      <span class="badge">MANAGER {action_verb}</span>
    </div>
    <h3 style="margin: 0 0 8px;">Decision on Ticket {ticket_id}</h3>
    <p style="color: #64748b; font-size: 13px; margin: 0 0 16px;">
      Hello {assigned_to}, the operations manager has reviewed and marked this ticket <strong>{action}</strong>.
    </p>
    <table class="table">
      <tr><td style="color: #64748b; width: 120px;">Ticket ID:</td><td><strong>{ticket_id}</strong></td></tr>
      <tr><td style="color: #64748b;">Customer:</td><td>{customer}</td></tr>
      <tr><td style="color: #64748b;">Amount:</td><td><strong>${amount}</strong></td></tr>
      <tr><td style="color: #64748b;">Reason:</td><td>{reason}</td></tr>
    </table>
    <div class="next-box">
      <strong>Action for Agent:</strong><br>{next_step}
    </div>
  </div>
</body>
</html>"""

    smtp_res = dispatch_smtp_email(recipient, subject, body, html_body=html_body)
    return {
        "dispatched": True,
        "recipient": recipient,
        "action": action,
        "subject": subject,
        "smtp": smtp_res,
    }


def send_agent_info_request_email(
    ticket: dict[str, Any],
    instructions: str = "Manager requested additional customer information and verification details before approving this refund.",
    recipient_override: str | None = None,
) -> dict[str, Any]:
    """Dispatch an automated request-for-info email notification to the assigned support agent."""
    ticket_id = ticket.get("ticket_id", "Unknown")
    customer = ticket.get("customer_name") or ticket.get("customer_email") or "Customer"
    assigned_to = ticket.get("assigned_to") or ticket.get("agent") or "Support Team"
    amount = ticket.get("refund_amount") or ticket.get("amount") or "0.00"
    reason = ticket.get("reason") or "Operational review"

    recipient = (
        recipient_override
        or os.getenv("AGENT_NOTIFICATIONS_EMAIL")
        or os.getenv("ESCALATION_MANAGER_EMAIL")
        or f"{str(assigned_to).lower()}@company.com"
    )

    action_verb = "MORE INFO REQUESTED"
    badge_color = "#d97706"
    next_step = (
        f"{instructions} Please contact {customer} to gather verification details, "
        f"update the ticket context, and re-submit for approval."
    )

    subject = f"[ACTION REQUIRED: More Info Needed] Ticket {ticket_id} - {customer} (${amount})"
    body = (
        f"========================================\n"
        f"ACTION REQUIRED: Ticket {ticket_id}\n"
        f"========================================\n"
        f"Status:       {action_verb}\n"
        f"Customer:     {customer}\n"
        f"Amount:       ${amount}\n"
        f"Assigned To:  {assigned_to}\n"
        f"Reason:       {reason}\n\n"
        f"INSTRUCTIONS:\n{next_step}\n"
    )

    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 20px; }}
    .card {{ background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; max-width: 560px; margin: 0 auto; padding: 24px; }}
    .badge {{ display: inline-block; padding: 6px 12px; border-radius: 4px; color: #ffffff; font-weight: bold; background: {badge_color}; }}
    .table {{ width: 100%; border-collapse: collapse; margin: 16px 0; }}
    .table td {{ padding: 8px 10px; border-bottom: 1px solid #f1f5f9; font-size: 13px; }}
    .next-box {{ background: #fef3c7; border-left: 4px solid {badge_color}; padding: 12px; margin-top: 16px; font-size: 13px; color: #92400e; }}
  </style>
</head>
<body>
  <div class="card">
    <div style="margin-bottom: 12px;">
      <span class="badge">MANAGER REQUEST: MORE INFO</span>
    </div>
    <h3 style="margin: 0 0 8px;">Action Required on Ticket {ticket_id}</h3>
    <p style="color: #64748b; font-size: 13px; margin: 0 0 16px;">
      Hello {assigned_to}, the operations manager reviewed this billing escalation and requested more information before making an approval decision.
    </p>
    <table class="table">
      <tr><td style="color: #64748b; width: 120px;">Ticket ID:</td><td><strong>{ticket_id}</strong></td></tr>
      <tr><td style="color: #64748b;">Customer:</td><td>{customer}</td></tr>
      <tr><td style="color: #64748b;">Amount:</td><td><strong>${amount}</strong></td></tr>
      <tr><td style="color: #64748b;">Reason:</td><td>{reason}</td></tr>
    </table>
    <div class="next-box">
      <strong>Action Required for Agent:</strong><br>{next_step}
    </div>
  </div>
</body>
</html>"""

    smtp_res = dispatch_smtp_email(recipient, subject, body, html_body=html_body)
    return {
        "dispatched": True,
        "recipient": recipient,
        "action": "Needs Info",
        "subject": subject,
        "instructions": instructions,
        "smtp": smtp_res,
    }
