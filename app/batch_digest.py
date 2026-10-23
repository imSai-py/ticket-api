import csv
import io
import os
from datetime import datetime
from typing import Any

from app.escalation import (
    build_approval_action_urls,
    dispatch_smtp_email,
    get_base_url,
)
from app.tracking_sync import (
    _is_needs_info_status,
    _read_all,
    get_ops_tracking_path,
    is_ticket_urgent,
)


def parse_ticket_datetime(dt_val: Any) -> datetime | None:
    """Parse a datetime object or date/time string into a naive datetime."""
    if not dt_val:
        return None
    if isinstance(dt_val, datetime):
        return dt_val
    val_str = str(dt_val).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val_str, fmt)
        except ValueError:
            continue
    return None


def generate_batch_digest(
    csv_path: str | None = None,
    recipient: str | None = None,
    spreadsheet_url: str | None = None,
    tickets: list[dict[str, Any]] | None = None,
    send_email: bool = True,
    start_time: datetime | str | None = None,
    end_time: datetime | str | None = None,
    slot_label: str | None = None,
) -> dict[str, Any]:
    """Generate a single consolidated email digest for all non-urgent tickets in the batch slot."""
    target_recipient = (
        recipient
        or os.getenv("DIGEST_MANAGER_EMAIL")
        or os.getenv("ESCALATION_MANAGER_EMAIL")
        or "billing-manager@company.com"
    )

    if tickets is not None:
        source_tickets = tickets
    else:
        path = csv_path or get_ops_tracking_path()
        source_tickets = _read_all(path)

    start_dt = parse_ticket_datetime(start_time)
    end_dt = parse_ticket_datetime(end_time)

    eligible_tickets = []
    for t in source_tickets:
        is_resubmit = bool(
            t.get("is_resubmission") is True
            or str(t.get("is_resubmission", "")).lower() == "true"
            or "resubmitted" in str(t.get("notes", "")).lower()
            or "manager requested more info" in str(t.get("notes", "")).lower()
        )
        # Exclude urgent priority incoming tickets (escalated immediately)
        if is_ticket_urgent(t) and not is_resubmit:
            continue

        # Exclude closed and resolved tickets
        status_clean = str(t.get("status", "")).strip().lower()
        if status_clean in (
            "closed",
            "resolved",
            "approved",
            "rejected",
        ) or _is_needs_info_status(status_clean):
            continue

        # Optional time window filter
        if start_dt is not None or end_dt is not None:
            created_dt = parse_ticket_datetime(t.get("created_at"))
            if created_dt is None:
                continue
            if start_dt is not None and created_dt < start_dt:
                continue
            if end_dt is not None and created_dt >= end_dt:
                continue

        eligible_tickets.append(t)

    count = len(eligible_tickets)
    today_str = datetime.now().strftime("%Y-%m-%d")
    sheet_link = (
        spreadsheet_url or os.getenv("SPREADSHEET_URL") or "data/ops_tracking_sheet.csv"
    )

    if slot_label:
        subject = f"[Batch Digest - {slot_label}] {count} Tickets ({today_str})"
    else:
        subject = f"[Daily Digest] Billing Approvals: {count} Pending ({today_str})"

    if count == 0:
        empty_msg = "No pending billing approvals today."
        return {
            "has_pending": False,
            "dispatched": False,
            "pending_count": 0,
            "recipient": target_recipient,
            "subject": subject,
            "body_table": empty_msg,
            "html_body": f"<p>{empty_msg}</p>",
            "csv_payload": "",
            "spreadsheet_link": sheet_link,
            "smtp": {
                "sent": False,
                "mode": "skipped",
                "message": "No pending tickets to digest.",
            },
        }

    header_line = f"{'Ticket ID':<12} | {'Customer':<20} | {'Category':<12} | {'Priority':<10} | {'Amount':<10} | {'Agent':<12} | {'Reason'}"
    sep_line = "-" * 110
    base_url = get_base_url()
    data_lines = []
    html_rows = []

    for t in eligible_tickets:
        raw_amt = t.get("refund_amount") or t.get("amount") or 0.0
        try:
            amount_num = float(
                str(raw_amt).replace("$", "").replace(",", "").strip() or 0.0
            )
        except ValueError:
            amount_num = 0.0

        customer = t.get("customer_name") or t.get("customer_email") or "Customer"
        category = t.get("category") or "General"
        priority = str(t.get("priority") or "normal")
        agent = t.get("assigned_to") or t.get("agent") or "System"
        reason = t.get("reason") or "Operational review"

        action_urls = build_approval_action_urls(t["ticket_id"], base_url)
        approve_url = action_urls.approve_url
        reject_url = action_urls.reject_url
        need_info_url = action_urls.need_info_url

        amount_display = f"${amount_num:<9.2f}" if amount_num > 0.0 else f"{'-':<10}"
        html_amount = f"${amount_num:.2f}" if amount_num > 0.0 else "-"

        data_lines.append(
            f"{t['ticket_id']:<12} | {customer:<20} | {category:<12} | {priority:<10} | {amount_display} | {agent:<12} | {reason}\n"
            f"  -> Actions: [Approve: {approve_url}]  [Reject: {reject_url}]  [Need More Info: {need_info_url}]"
        )

        html_rows.append(
            f"<tr>"
            f"  <td style='padding: 10px 12px; border-bottom: 1px solid #e2e8f0; font-weight: bold;'>{t['ticket_id']}</td>"
            f"  <td style='padding: 10px 12px; border-bottom: 1px solid #e2e8f0;'>{customer}</td>"
            f"  <td style='padding: 10px 12px; border-bottom: 1px solid #e2e8f0; color: #475569; font-weight: 500;'>{category}</td>"
            f"  <td style='padding: 10px 12px; border-bottom: 1px solid #e2e8f0; font-weight: 600; text-transform: capitalize;'>{priority}</td>"
            f"  <td style='padding: 10px 12px; border-bottom: 1px solid #e2e8f0; color: #dc2626; font-weight: bold;'>{html_amount}</td>"
            f"  <td style='padding: 10px 12px; border-bottom: 1px solid #e2e8f0;'>{agent}</td>"
            f"  <td style='padding: 10px 12px; border-bottom: 1px solid #e2e8f0;'>{reason}</td>"
            f"  <td style='padding: 10px 12px; border-bottom: 1px solid #e2e8f0; text-align: center; white-space: nowrap;'>"
            f"    <a href='{approve_url}' style='background-color: #28a745; color: #ffffff !important; padding: 6px 12px; text-decoration: none; border-radius: 4px; font-weight: bold; font-size: 12px; display: inline-block; margin-right: 6px;'>Approve</a>"
            f"    <a href='{reject_url}' style='background-color: #dc3545; color: #ffffff !important; padding: 6px 12px; text-decoration: none; border-radius: 4px; font-weight: bold; font-size: 12px; display: inline-block; margin-right: 6px;'>Reject</a>"
            f"    <a href='{need_info_url}' style='background-color: #ffc107; color: #212529 !important; padding: 6px 12px; text-decoration: none; border-radius: 4px; font-weight: bold; font-size: 12px; display: inline-block;'>Need More Info</a>"
            f"  </td>"
            f"</tr>"
        )

    table_content = "\n".join([header_line, sep_line] + data_lines)
    footer_text = f"\n\nSpreadsheet Link for bulk reviews: {sheet_link}"
    full_body_table = table_content + footer_text

    title_label = (
        f"Consolidated Batch Digest ({slot_label})"
        if slot_label
        else "Consolidated Billing Approvals Digest"
    )

    html_table = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px; color: #1e293b; }}
    .container {{ max-width: 860px; margin: 0 auto; background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; padding: 28px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }}
    .header {{ border-bottom: 2px solid #2563eb; padding-bottom: 12px; margin-bottom: 16px; }}
    .title {{ color: #1e40af; font-size: 20px; font-weight: bold; margin: 0; }}
    .badge {{ display: inline-block; background-color: #fee2e2; color: #991b1b; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; margin-left: 8px; }}
    .table {{ width: 100%; border-collapse: collapse; margin-top: 16px; margin-bottom: 20px; font-size: 13px; }}
    .table th {{ background-color: #f1f5f9; padding: 10px 12px; text-align: left; font-size: 12px; font-weight: 600; color: #475569; border-bottom: 2px solid #cbd5e1; }}
    .footer {{ margin-top: 24px; font-size: 12px; color: #64748b; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 16px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h2 class="title">📊 {title_label} <span class="badge">{count} PENDING</span></h2>
    </div>
    <p style="color: #475569; font-size: 14px; margin-top: 4px;">
      The following tickets require your management review. You can approve or reject each item directly below:
    </p>
    <table class="table">
      <thead>
        <tr>
          <th>Ticket ID</th>
          <th>Customer</th>
          <th>Category</th>
          <th>Priority</th>
          <th>Amount</th>
          <th>Agent</th>
          <th>Reason</th>
          <th style="text-align: center;">Action</th>
        </tr>
      </thead>
      <tbody>
        {"".join(html_rows)}
      </tbody>
    </table>
    <div class="footer">
      Spreadsheet review link: <a href="{sheet_link}" style="color: #2563eb;">{sheet_link}</a><br>
      Automated operations digest &bull; Bitcot Operations System
    </div>
  </div>
</body>
</html>"""

    # Generate CSV payload in memory
    csv_buffer = io.StringIO()
    if eligible_tickets:
        fieldnames = list(eligible_tickets[0].keys())
        writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(eligible_tickets)

    smtp_res = None
    if send_email:
        smtp_res = dispatch_smtp_email(
            target_recipient,
            subject,
            full_body_table,
            html_body=html_table,
        )

    return {
        "has_pending": True,
        "dispatched": True,
        "pending_count": count,
        "recipient": target_recipient,
        "subject": subject,
        "body_table": full_body_table,
        "html_body": html_table,
        "csv_payload": csv_buffer.getvalue(),
        "spreadsheet_link": sheet_link,
        "smtp": smtp_res,
    }
