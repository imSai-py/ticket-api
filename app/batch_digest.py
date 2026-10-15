import csv
import io
import os
from datetime import datetime
from typing import Any

from app.escalation import (
    build_approval_action_urls,
    dispatch_smtp_email,
    is_billing_category,
)
from app.tracking_sync import get_pending_approvals


def generate_batch_digest(
    csv_path: str | None = None,
    recipient: str | None = None,
    spreadsheet_url: str | None = None,
    tickets: list[dict[str, Any]] | None = None,
    send_email: bool = True,
) -> dict[str, Any]:
    """Generate a single consolidated email digest for all pending billing approvals."""
    target_recipient = (
        recipient
        or os.getenv("DIGEST_MANAGER_EMAIL")
        or os.getenv("ESCALATION_MANAGER_EMAIL")
        or "billing-manager@company.com"
    )

    if tickets is not None:
        pending_tickets = [
            t
            for t in tickets
            if is_billing_category(t.get("category"))
            and str(t.get("status", "")).strip().lower() not in ("approved", "rejected")
        ]
    else:
        all_pending = get_pending_approvals(csv_path=csv_path)
        pending_tickets = [
            t for t in all_pending if is_billing_category(t.get("category"))
        ]

    count = len(pending_tickets)
    today_str = datetime.now().strftime("%Y-%m-%d")
    sheet_link = (
        spreadsheet_url or os.getenv("SPREADSHEET_URL") or "data/ops_tracking_sheet.csv"
    )

    subject = f"[Daily Digest] Billing Approvals: {count} Pending ({today_str})"

    if count == 0:
        return {
            "has_pending": False,
            "dispatched": False,
            "pending_count": 0,
            "recipient": target_recipient,
            "subject": subject,
            "body_table": "No pending billing approvals today.",
            "html_body": "<p>No pending billing approvals today.</p>",
            "csv_payload": "",
            "spreadsheet_link": sheet_link,
            "smtp": {
                "sent": False,
                "mode": "skipped",
                "message": "No pending tickets to digest.",
            },
        }

    header_line = f"{'Ticket ID':<12} | {'Customer':<20} | {'Amount':<10} | {'Agent':<12} | {'Reason'}"
    sep_line = "-" * 85
    base_url = (os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/")
    data_lines = []
    html_rows = []

    for t in pending_tickets:
        raw_amt = t.get("refund_amount") or t.get("amount") or 0.0
        try:
            amount_num = float(
                str(raw_amt).replace("$", "").replace(",", "").strip() or 0.0
            )
        except ValueError:
            amount_num = 0.0

        customer = t.get("customer_name") or t.get("customer_email") or "Customer"
        agent = t.get("assigned_to") or t.get("agent") or "System"
        reason = t.get("reason") or "Operational review"

        action_urls = build_approval_action_urls(t["ticket_id"], base_url)
        approve_url = action_urls.approve_url
        reject_url = action_urls.reject_url
        need_info_url = action_urls.need_info_url

        data_lines.append(
            f"{t['ticket_id']:<12} | {customer:<20} | ${amount_num:<9.2f} | {agent:<12} | {reason}\n"
            f"  -> Actions: [Approve: {approve_url}]  [Reject: {reject_url}]  [Need More Info: {need_info_url}]"
        )

        html_rows.append(
            f"<tr>"
            f"  <td style='padding: 10px 12px; border-bottom: 1px solid #e2e8f0; font-weight: bold;'>{t['ticket_id']}</td>"
            f"  <td style='padding: 10px 12px; border-bottom: 1px solid #e2e8f0;'>{customer}</td>"
            f"  <td style='padding: 10px 12px; border-bottom: 1px solid #e2e8f0; color: #dc2626; font-weight: bold;'>${amount_num:.2f}</td>"
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
      <h2 class="title">📊 Consolidated Billing Approvals Digest <span class="badge">{count} PENDING</span></h2>
    </div>
    <p style="color: #475569; font-size: 14px; margin-top: 4px;">
      The following urgent billing tickets require your management review. You can approve or reject each item directly below:
    </p>
    <table class="table">
      <thead>
        <tr>
          <th>Ticket ID</th>
          <th>Customer</th>
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
    if pending_tickets:
        fieldnames = list(pending_tickets[0].keys())
        writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(pending_tickets)

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
