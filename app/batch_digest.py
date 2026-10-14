import csv
import io
import os
from datetime import UTC, datetime
from typing import Any

from app.tracking_sync import get_pending_approvals


def generate_batch_digest(
    csv_path: str | None = None,
    recipient: str | None = None,
    spreadsheet_url: str | None = None,
) -> dict[str, Any]:
    """Generate a single consolidated email digest for all pending billing approvals."""
    target_recipient = (
        recipient or os.getenv("DIGEST_MANAGER_EMAIL") or "billing-manager@company.com"
    )
    pending_tickets = get_pending_approvals(csv_path=csv_path)
    count = len(pending_tickets)
    today_str = datetime.now(UTC).strftime("%Y-%m-%d")
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
            "csv_payload": "",
            "spreadsheet_link": sheet_link,
        }

    header_line = f"{'Ticket ID':<12} | {'Customer':<20} | {'Amount':<10} | {'Agent':<12} | {'Reason'}"
    sep_line = "-" * 85
    data_lines = []
    for t in pending_tickets:
        amount_num = float(t.get("amount") or 0.0)
        data_lines.append(
            f"{t['ticket_id']:<12} | {t['customer_name']:<20} | ${amount_num:<9.2f} | {t.get('agent', 'System'):<12} | {t.get('reason', '')}"
        )

    table_content = "\n".join([header_line, sep_line] + data_lines)
    footer_text = f"\n\nSpreadsheet Link for bulk reviews: {sheet_link}"
    full_body_table = table_content + footer_text

    # Generate CSV payload in memory
    csv_buffer = io.StringIO()
    if pending_tickets:
        fieldnames = list(pending_tickets[0].keys())
        writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(pending_tickets)

    return {
        "has_pending": True,
        "dispatched": True,
        "pending_count": count,
        "recipient": target_recipient,
        "subject": subject,
        "body_table": full_body_table,
        "csv_payload": csv_buffer.getvalue(),
        "spreadsheet_link": sheet_link,
    }
