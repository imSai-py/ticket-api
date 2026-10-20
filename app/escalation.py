import logging
import os
import smtplib
import sys
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import httpx

from app.schemas import ApprovalActionUrls, ApprovalStatusEnum, OpsTicketRecord
from app.tracking_sync import is_ticket_urgent

logger = logging.getLogger(__name__)


def is_billing_category(category: Any) -> bool:
    """Return True if category is within the client billing/refund scope."""
    val = str(getattr(category, "value", category) or "").strip().lower()
    return "billing" in val or "refund" in val


def build_approval_action_urls(
    ticket_id: str, base_url: str | None = None
) -> ApprovalActionUrls:
    """Build standardized query-parameter approval action URLs."""
    root = (base_url or os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/")
    return ApprovalActionUrls(
        approve_url=f"{root}/ops/approvals/action?ticket_id={ticket_id}&status=Approved",
        reject_url=f"{root}/ops/approvals/action?ticket_id={ticket_id}&status=Rejected",
        need_info_url=f"{root}/ops/approvals/action?ticket_id={ticket_id}&status=needs_info",
    )


def dispatch_http_email(
    to_email: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> dict[str, Any] | None:
    """Send email via HTTP APIs (HTTPS Port 443) which bypass cloud firewall port blocks.

    Returns dict if an HTTP provider was configured and attempted, or None if no HTTP provider is set.
    """
    recipient_list = [addr.strip() for addr in to_email.split(",") if addr.strip()]
    if not recipient_list:
        return {
            "sent": False,
            "mode": "error",
            "message": "No valid recipients provided.",
        }
    formatted_to = ", ".join(recipient_list)

    # 1. Resend API (https://resend.com)
    resend_api_key = os.getenv("RESEND_API_KEY")
    if resend_api_key:
        resend_from = (
            os.getenv("RESEND_FROM")
            or os.getenv("SMTP_FROM")
            or "onboarding@resend.dev"
        )
        payload: dict[str, Any] = {
            "from": resend_from,
            "to": recipient_list,
            "subject": subject,
            "text": body,
        }
        if html_body:
            payload["html"] = html_body
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {resend_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            if resp.status_code in (200, 201):
                msg_id = resp.json().get("id", "unknown")
                logger.info(
                    "Resend HTTP email successfully delivered to %s (id: %s)",
                    formatted_to,
                    msg_id,
                )
                return {
                    "sent": True,
                    "mode": "resend",
                    "recipient": formatted_to,
                    "id": msg_id,
                }
            else:
                err_text = resp.text
                logger.error(
                    "Resend HTTP email failed: %s %s", resp.status_code, err_text
                )
                return {
                    "sent": False,
                    "mode": "resend_error",
                    "error": f"HTTP {resp.status_code}: {err_text}",
                }
        except Exception as exc:
            logger.error("Resend HTTP request failed: %s", exc)
            return {"sent": False, "mode": "resend_error", "error": str(exc)}

    # 2. Brevo API (https://brevo.com)
    brevo_api_key = os.getenv("BREVO_API_KEY")
    if brevo_api_key:
        brevo_from = (
            os.getenv("BREVO_FROM")
            or os.getenv("SMTP_FROM")
            or "alerts@company.com"
        )
        payload = {
            "sender": {"email": brevo_from, "name": "Bitcot Operations"},
            "to": [{"email": addr} for addr in recipient_list],
            "subject": subject,
            "textContent": body,
        }
        if html_body:
            payload["htmlContent"] = html_body
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    "https://api.brevo.com/v3/smtp/email",
                    headers={
                        "api-key": brevo_api_key,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json=payload,
                )
            if resp.status_code in (200, 201):
                msg_id = resp.json().get("messageId", "unknown")
                logger.info(
                    "Brevo HTTP email successfully delivered to %s (messageId: %s)",
                    formatted_to,
                    msg_id,
                )
                return {
                    "sent": True,
                    "mode": "brevo",
                    "recipient": formatted_to,
                    "messageId": msg_id,
                }
            else:
                err_text = resp.text
                logger.error(
                    "Brevo HTTP email failed: %s %s", resp.status_code, err_text
                )
                return {
                    "sent": False,
                    "mode": "brevo_error",
                    "error": f"HTTP {resp.status_code}: {err_text}",
                }
        except Exception as exc:
            logger.error("Brevo HTTP request failed: %s", exc)
            return {"sent": False, "mode": "brevo_error", "error": str(exc)}

    # 3. Generic Webhook / Relay URL
    webhook_url = os.getenv("EMAIL_WEBHOOK_URL")
    if webhook_url:
        payload = {
            "to": recipient_list,
            "from": os.getenv("SMTP_FROM", "alerts@company.com"),
            "subject": subject,
            "body": body,
            "html_body": html_body,
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(webhook_url, json=payload)
            if resp.status_code in (200, 201, 202, 204):
                logger.info(
                    "Webhook email successfully delivered to %s via %s",
                    formatted_to,
                    webhook_url,
                )
                return {
                    "sent": True,
                    "mode": "webhook",
                    "recipient": formatted_to,
                }
            else:
                return {
                    "sent": False,
                    "mode": "webhook_error",
                    "error": f"HTTP {resp.status_code}: {resp.text}",
                }
        except Exception as exc:
            logger.error("Webhook email request failed: %s", exc)
            return {"sent": False, "mode": "webhook_error", "error": str(exc)}

    return None


def dispatch_smtp_email(
    to_email: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> dict[str, Any]:
    """Send real email via HTTP API (port 443) or SMTP.

    First checks for HTTP providers (Resend, Brevo, Webhook) which bypass cloud host port blocks.
    Falls back to SMTP if no HTTP providers are active.
    """
    if "pytest" in sys.modules and not os.getenv("ENABLE_LIVE_SMTP_IN_TESTS"):
        return {
            "sent": False,
            "mode": "mock",
            "message": "Pytest environment detected. Real SMTP suppressed.",
        }

    # 1. Attempt HTTP email delivery first (bypasses Render/cloud SMTP port blocks)
    http_result = dispatch_http_email(
        to_email, subject, body, html_body=html_body
    )
    if http_result is not None:
        return http_result

    # 2. Fall back to standard SMTP
    smtp_host = os.getenv("SMTP_HOST") or os.getenv("SMTP_SERVER")
    smtp_port_raw = os.getenv("SMTP_PORT", "587")
    smtp_user = os.getenv("SMTP_USER") or os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD") or os.getenv("SMTP_PASS")
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "alerts@company.com")

    if not smtp_host or not smtp_user or not smtp_password:
        logger.info(
            "SMTP credentials not configured (host=%s, user=%s, pass=%s). Dispatched in mock mode.",
            bool(smtp_host),
            bool(smtp_user),
            bool(smtp_password),
        )
        return {
            "sent": False,
            "mode": "mock",
            "message": "SMTP credentials not configured. Dispatched in mock mode.",
        }

    try:
        port = int(smtp_port_raw)
        recipient_list = [addr.strip() for addr in to_email.split(",") if addr.strip()]
        if not recipient_list:
            return {
                "sent": False,
                "mode": "error",
                "message": "No valid recipients provided.",
            }

        formatted_to = ", ".join(recipient_list)
        if html_body:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = smtp_from
            msg["To"] = formatted_to
            msg.attach(MIMEText(body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))
        else:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = smtp_from
            msg["To"] = formatted_to

        with smtplib.SMTP(smtp_host, port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, recipient_list, msg.as_string())
        logger.info("Real SMTP email successfully delivered to %s", formatted_to)
        return {"sent": True, "mode": "smtp", "recipient": formatted_to}
    except (smtplib.SMTPException, OSError) as err:
        logger.error("SMTP delivery failed to %s: %s", to_email, err)
        err_str = str(err)
        res: dict[str, Any] = {"sent": False, "mode": "smtp_error", "error": err_str}
        if "101" in err_str or "unreachable" in err_str.lower() or "timed out" in err_str.lower():
            res["diagnosis"] = (
                "Outbound SMTP ports (25, 465, 587) are blocked by hosting firewall (e.g. Render Free Tier). "
                "Configure an HTTP email provider (RESEND_API_KEY or BREVO_API_KEY) or upgrade to a paid tier."
            )
        return res


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
    action_urls = build_approval_action_urls(ticket_id, base_url)
    approve_url = action_urls.approve_url
    reject_url = action_urls.reject_url
    need_info_url = action_urls.need_info_url

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
      <a href="{approve_url}" class="btn" style="background-color: #28a745; color: #ffffff !important; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block; margin-right: 8px;">✅ Approve</a>
      <a href="{reject_url}" class="btn" style="background-color: #dc3545; color: #ffffff !important; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block; margin-right: 8px;">❌ Reject</a>
      <a href="{need_info_url}" class="btn" style="background-color: #ffc107; color: #212529 !important; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">⚠️ Need More Info</a>
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
        "need_info_url": need_info_url,
    }


@dataclass
class AgentCardTheme:
    """Theme and layout attributes for agent notification card."""

    badge_label: str
    badge_color: str
    greeting_text: str
    box_title: str
    box_bg: str
    box_color: str
    next_step: str


def _resolve_agent_recipient(
    assigned_to: str,
    agent_email: str | None = None,
    recipient_override: str | None = None,
) -> str:
    """Resolve destination email address for support agent notifications."""
    if recipient_override:
        return recipient_override
    if agent_email and "@" in agent_email:
        return agent_email
    if assigned_to and "@" in assigned_to:
        return assigned_to
    if os.getenv("AGENT_NOTIFICATIONS_EMAIL"):
        return os.getenv("AGENT_NOTIFICATIONS_EMAIL")
    if assigned_to and assigned_to.lower() not in ("support team", "unknown", ""):
        return f"{assigned_to.strip().lower()}@company.com"
    return os.getenv("ESCALATION_MANAGER_EMAIL") or "support@company.com"


def _render_agent_notification_email(
    ticket_id: str,
    customer: str,
    amount: str,
    assigned_to: str,
    reason: str,
    theme: AgentCardTheme,
    recipient: str,
    subject: str,
    action: str,
    instructions: str | None = None,
) -> dict[str, Any]:
    """Helper to render and dispatch unified agent notification HTML emails."""
    badge_label = theme.badge_label
    badge_color = theme.badge_color
    greeting_text = theme.greeting_text
    box_title = theme.box_title
    box_bg = theme.box_bg
    box_color = theme.box_color
    next_step = theme.next_step

    body = (
        f"========================================\n"
        f"NOTIFICATION: Ticket {ticket_id}\n"
        f"========================================\n"
        f"Status:       {badge_label}\n"
        f"Customer:     {customer}\n"
        f"Amount:       ${amount}\n"
        f"Assigned To:  {assigned_to}\n"
        f"Reason:       {reason}\n\n"
        f"{box_title}:\n{next_step}\n"
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
    .next-box {{ background: {box_bg}; border-left: 4px solid {badge_color}; padding: 12px; margin-top: 16px; font-size: 13px; color: {box_color}; }}
  </style>
</head>
<body>
  <div class="card">
    <div style="margin-bottom: 12px;">
      <span class="badge">{badge_label}</span>
    </div>
    <h3 style="margin: 0 0 8px;">Action on Ticket {ticket_id}</h3>
    <p style="color: #64748b; font-size: 13px; margin: 0 0 16px;">
      {greeting_text}
    </p>
    <table class="table">
      <tr><td style="color: #64748b; width: 120px;">Ticket ID:</td><td><strong>{ticket_id}</strong></td></tr>
      <tr><td style="color: #64748b;">Customer:</td><td>{customer}</td></tr>
      <tr><td style="color: #64748b;">Amount:</td><td><strong>${amount}</strong></td></tr>
      <tr><td style="color: #64748b;">Reason:</td><td>{reason}</td></tr>
    </table>
    <div class="next-box">
      <strong>{box_title}:</strong><br>{next_step}
    </div>
  </div>
</body>
</html>"""

    logger.warning(
        "Dispatched agent notification for ticket %s to %s (action: %s)",
        ticket_id,
        recipient,
        action,
    )
    smtp_res = dispatch_smtp_email(recipient, subject, body, html_body=html_body)
    res: dict[str, Any] = {
        "dispatched": True,
        "recipient": recipient,
        "action": action,
        "subject": subject,
        "body": body,
        "html_body": html_body,
        "smtp": smtp_res,
    }
    if instructions is not None:
        res["instructions"] = instructions
    return res


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

    recipient = _resolve_agent_recipient(
        str(assigned_to),
        recipient_override=recipient_override,
    )

    try:
        approval_status = ApprovalStatusEnum.from_action(action)
    except ValueError:
        approval_status = None

    if approval_status == ApprovalStatusEnum.APPROVED:
        action_verb = "APPROVED"
        badge_color = "#16a34a"
        next_step = (
            f"You are authorized to execute the refund of ${amount} to {customer}."
        )
    elif approval_status == ApprovalStatusEnum.NEEDS_INFO:
        action_verb = "MORE INFO REQUESTED"
        badge_color = "#ffc107"
        next_step = f"Manager requires more information. Please contact {customer} to gather necessary verification details and update the ticket."
    else:
        action_verb = "REJECTED"
        badge_color = "#dc2626"
        next_step = f"Do not issue a refund. Please contact {customer} to communicate the rejection."

    subject = f"[DECISION: {action_verb}] Ticket {ticket_id} - {customer} (${amount})"
    theme = AgentCardTheme(
        badge_label=f"MANAGER {action_verb}",
        badge_color=badge_color,
        greeting_text=f"Hello {assigned_to}, the operations manager has reviewed and marked this ticket <strong>{action}</strong>.",
        box_title="Action for Agent",
        box_bg="#f1f5f9",
        box_color="#334155",
        next_step=next_step,
    )
    return _render_agent_notification_email(
        ticket_id=ticket_id,
        customer=customer,
        amount=str(amount),
        assigned_to=str(assigned_to),
        reason=str(reason),
        theme=theme,
        recipient=recipient,
        subject=subject,
        action=action,
    )


def send_agent_info_request_email(
    ticket_or_id: dict[str, Any] | str | None = None,
    customer_name: str | None = None,
    amount: float | str | None = None,
    reason: str | None = None,
    agent_email: str | None = None,
    instructions: str = "Manager requested additional customer information and verification details before approving this refund.",
    recipient_override: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Dispatch an automated request-for-info email notification to the assigned support agent.

    Supports both dictionary payload and positional arguments per Spec L71.
    """
    actual_input = (
        ticket_or_id if ticket_or_id is not None else kwargs.get("ticket_id", "Unknown")
    )
    if isinstance(actual_input, dict):
        ticket = actual_input
        resolved_ticket_id = ticket.get("ticket_id", "Unknown")
        customer = (
            ticket.get("customer_name") or ticket.get("customer_email") or "Customer"
        )
        assigned_to = ticket.get("assigned_to") or ticket.get("agent") or "Support Team"
        amount_val = ticket.get("refund_amount") or ticket.get("amount") or "0.00"
        reason_val = ticket.get("reason") or "Operational review"
        target_agent = _resolve_agent_recipient(
            str(assigned_to),
            agent_email=ticket.get("agent_email"),
            recipient_override=recipient_override,
        )
    else:
        resolved_ticket_id = str(actual_input)
        customer = str(customer_name or "Customer")
        amount_val = (
            f"{float(amount):.2f}"
            if isinstance(amount, (int, float))
            else str(amount or "0.00")
        )
        reason_val = str(reason or "Operational review")
        assigned_to = str(agent_email or "Support Team")
        target_agent = _resolve_agent_recipient(
            str(assigned_to),
            agent_email=agent_email,
            recipient_override=recipient_override,
        )

    badge_color = "#ffc107"
    next_step = (
        f"{instructions} Please contact {customer} to gather verification details, "
        f"update the ticket context, and re-submit for approval."
    )
    subject = f"[ACTION REQUIRED: More Info Needed] Ticket {resolved_ticket_id} - {customer} (${amount_val})"

    theme = AgentCardTheme(
        badge_label="MANAGER REQUEST: MORE INFO",
        badge_color=badge_color,
        greeting_text=f"Hello {assigned_to}, the operations manager reviewed this billing escalation and requested more information before making an approval decision.",
        box_title="Action Required for Agent",
        box_bg="#fef3c7",
        box_color="#92400e",
        next_step=next_step,
    )
    return _render_agent_notification_email(
        ticket_id=resolved_ticket_id,
        customer=customer,
        amount=str(amount_val),
        assigned_to=str(assigned_to),
        reason=str(reason_val),
        theme=theme,
        recipient=target_agent,
        subject=subject,
        action="Needs Info",
        instructions=instructions,
    )


def send_resubmission_notification(
    ticket: OpsTicketRecord | dict[str, Any],
    recipient_override: str | None = None,
    dispatch_smtp: bool = True,
) -> dict[str, Any]:
    """Dispatch an alert to the operations manager when a ticket is re-submitted by a support agent."""
    if isinstance(ticket, OpsTicketRecord):
        ticket_id = ticket.ticket_id
        customer = ticket.customer_name
        category = ticket.category
        raw_amt = ticket.refund_amount or ticket.amount or 0.0
        reason = ticket.reason or "Supplemental operational justification provided."
        agent = ticket.agent or ticket.assigned_to or "Support Agent"
        notes = ticket.notes or ""
    else:
        ticket_id = ticket.get("ticket_id", "Unknown")
        customer = (
            ticket.get("customer_name") or ticket.get("customer_email") or "Customer"
        )
        category = ticket.get("category", "Billing")
        raw_amt = ticket.get("refund_amount") or ticket.get("amount") or 0.0
        reason = (
            ticket.get("reason") or "Supplemental operational justification provided."
        )
        agent = ticket.get("agent") or ticket.get("assigned_to") or "Support Agent"
        notes = ticket.get("notes") or ""

    try:
        amount = float(str(raw_amt).replace("$", "").replace(",", "").strip() or 0.0)
    except ValueError:
        amount = 0.0

    recipient = (
        recipient_override
        or os.getenv("ESCALATION_MANAGER_EMAIL")
        or os.getenv("MANAGER_EMAIL")
        or os.getenv("ESCALATION_EMAIL")
        or "manager@company.com"
    )

    base_url = (os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/")
    action_urls = build_approval_action_urls(ticket_id, base_url)
    approve_url = action_urls.approve_url
    reject_url = action_urls.reject_url
    need_info_url = action_urls.need_info_url

    subject = f"[URGENT RESUBMISSION FOR REVIEW] Ticket {ticket_id} - {customer} (${amount:.2f})"
    body = (
        "========================================\n"
        "URGENT TICKET RESUBMITTED FOR MANAGER REVIEW\n"
        "========================================\n"
        f"Ticket ID:     {ticket_id}\n"
        f"Customer:      {customer}\n"
        f"Category:      {category}\n"
        f"Priority:      URGENT\n"
        f"Amount:        ${amount:.2f}\n"
        f"Agent:         {agent}\n"
        f"Reason:        {reason}\n"
        f"Audit Notes:   {notes}\n\n"
        "ACTION REQUIRED: Support agent has re-submitted this ticket with updated context. Please review and make an approval decision.\n\n"
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
    .header {{ border-bottom: 2px solid #dc2626; padding-bottom: 12px; margin-bottom: 18px; }}
    .title {{ color: #b91c1c; font-size: 18px; font-weight: bold; margin: 0; }}
    .desc {{ color: #475569; font-size: 14px; margin: 0 0 16px 0; }}
    .table {{ width: 100%; border-collapse: collapse; margin-bottom: 24px; }}
    .table td {{ padding: 10px 12px; border-bottom: 1px solid #f1f5f9; font-size: 14px; }}
    .label {{ font-weight: 600; color: #64748b; width: 140px; }}
    .value {{ font-weight: 500; color: #0f172a; }}
    .amount-highlight {{ color: #0f766e; font-weight: bold; font-size: 16px; }}
    .actions {{ text-align: center; padding-top: 16px; border-top: 1px solid #e2e8f0; }}
    .btn {{ display: inline-block; padding: 12px 24px; font-size: 14px; font-weight: bold; text-decoration: none; border-radius: 6px; margin: 0 6px; }}
    .footer {{ margin-top: 24px; font-size: 12px; color: #94a3b8; text-align: center; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <h2 class="title">🚨 URGENT TICKET RESUBMITTED FOR MANAGER REVIEW</h2>
    </div>
    <p class="desc">Support agent <strong>{agent}</strong> has re-submitted ticket <strong>{ticket_id}</strong> with updated operational context and verification details for urgent manager review.</p>
    <table class="table">
      <tr><td class="label">Ticket ID:</td><td class="value"><strong>{ticket_id}</strong></td></tr>
      <tr><td class="label">Customer:</td><td class="value">{customer}</td></tr>
      <tr><td class="label">Priority:</td><td class="value"><span style="color: #dc2626; font-weight: bold; text-transform: uppercase;">urgent</span></td></tr>
      <tr><td class="label">Category:</td><td class="value">{category}</td></tr>
      <tr><td class="label">Refund Amount:</td><td class="value"><span class="amount-highlight">${amount:.2f}</span></td></tr>
      <tr><td class="label">Handling Agent:</td><td class="value">{agent}</td></tr>
      <tr><td class="label">Justification:</td><td class="value">{reason}</td></tr>
      <tr><td class="label">Audit Trail:</td><td class="value">{notes}</td></tr>
    </table>
    <div class="actions">
      <a href="{approve_url}" class="btn" style="background-color: #28a745; color: #ffffff !important; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block; margin-right: 8px;">✅ Approve</a>
      <a href="{reject_url}" class="btn" style="background-color: #dc3545; color: #ffffff !important; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block; margin-right: 8px;">❌ Reject</a>
      <a href="{need_info_url}" class="btn" style="background-color: #ffc107; color: #212529 !important; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">⚠️ Need More Info</a>
    </div>
    <div class="footer">
      Automated operations alert &bull; Bitcot Operations System
    </div>
  </div>
</body>
</html>"""

    if dispatch_smtp:
        logger.warning(
            "Dispatched resubmission alert for ticket %s to %s",
            ticket_id,
            recipient,
        )
        smtp_res = dispatch_smtp_email(recipient, subject, body, html_body=html_body)
    else:
        smtp_res = {
            "sent": False,
            "mode": "suppressed",
            "message": "Dispatch suppressed.",
        }

    return {
        "dispatched": True,
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "html_body": html_body,
        "ticket_id": ticket_id,
        "amount": amount,
        "alert_type": "TICKET RESUBMITTED FOR MANAGER REVIEW",
        "smtp": smtp_res,
        "approve_url": approve_url,
        "reject_url": reject_url,
        "need_info_url": need_info_url,
    }
