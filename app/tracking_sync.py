import csv
import os
import re
from datetime import UTC, datetime
from typing import Any

FIELDNAMES = [
    "ticket_id",
    "customer_name",
    "category",
    "priority",
    "amount",
    "reason",
    "agent",
    "status",
    "escalated",
    "created_at",
    "updated_at",
    "notes",
]

DEFAULT_CSV_PATH = os.path.join("data", "ops_tracking_sheet.csv")


def extract_amount(text: str) -> tuple[float, str]:
    """Extract currency amount from text or flag for verification if missing."""
    if not text:
        return 0.0, "Needs amount verification"

    # Match patterns like $49.99, $ 50, 50.00 USD, 50 dollars
    dollar_match = re.search(r"\$\s*([0-9]+(?:\.[0-9]{1,2})?)", text)
    if dollar_match:
        try:
            return float(dollar_match.group(1)), ""
        except ValueError:
            pass

    usd_match = re.search(
        r"([0-9]+(?:\.[0-9]{1,2})?)\s*(?:usd|dollars?)", text, re.IGNORECASE
    )
    if usd_match:
        try:
            return float(usd_match.group(1)), ""
        except ValueError:
            pass

    return 0.0, "Needs amount verification"


def _ensure_file_exists(csv_path: str) -> None:
    """Ensure directory and CSV file with header exist."""
    os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()


def _read_all(csv_path: str) -> list[dict[str, Any]]:
    """Read all rows from the tracking CSV file."""
    _ensure_file_exists(csv_path)
    with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _write_all(csv_path: str, rows: list[dict[str, Any]]) -> None:
    """Write all rows back to the tracking CSV file."""
    _ensure_file_exists(csv_path)
    with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def sync_ticket_to_spreadsheet(
    ticket: dict[str, Any], csv_path: str | None = None
) -> dict[str, Any]:
    """Sync a ticket into the operations tracking spreadsheet."""
    path = csv_path or os.getenv("OPS_TRACKING_CSV_PATH", DEFAULT_CSV_PATH)
    rows = _read_all(path)
    now = datetime.now(UTC).isoformat()
    ticket_id = str(ticket.get("ticket_id", "")).strip()

    # Determine amount and verification note
    provided_amount = ticket.get("amount")
    text_content = f"{ticket.get('reason', '')} {ticket.get('text', '')}".strip()
    notes = str(ticket.get("notes", "")).strip()

    if provided_amount is not None and float(provided_amount) > 0:
        amount_val = float(provided_amount)
    else:
        amount_val, auto_note = extract_amount(text_content)
        if auto_note and auto_note not in notes:
            notes = f"{notes}; {auto_note}".strip("; ")

    existing_idx = next(
        (i for i, r in enumerate(rows) if r["ticket_id"] == ticket_id), None
    )

    is_escalated = (
        ticket.get("priority") == "urgent"
        or str(ticket.get("escalated", "")).lower() == "true"
        or ticket.get("escalated") is True
    )

    new_row: dict[str, Any] = {
        "ticket_id": ticket_id,
        "customer_name": str(ticket.get("customer_name", "Unknown")),
        "category": str(ticket.get("category", "Billing")),
        "priority": str(ticket.get("priority", "normal")),
        "amount": f"{amount_val:.2f}",
        "reason": str(ticket.get("reason", "")),
        "agent": str(ticket.get("agent", "System")),
        "status": str(ticket.get("status", "Pending")),
        "escalated": "True" if is_escalated else "False",
        "created_at": now,
        "updated_at": now,
        "notes": notes,
    }

    if existing_idx is not None:
        new_row["created_at"] = rows[existing_idx].get("created_at", now)
        rows[existing_idx] = new_row
    else:
        rows.append(new_row)

    _write_all(path, rows)
    return new_row


def get_pending_approvals(csv_path: str | None = None) -> list[dict[str, Any]]:
    """Retrieve all tickets in Pending status from the tracking spreadsheet."""
    path = csv_path or os.getenv("OPS_TRACKING_CSV_PATH", DEFAULT_CSV_PATH)
    rows = _read_all(path)
    return [r for r in rows if r["status"] == "Pending"]


def update_approval_status(
    ticket_id: str,
    new_status: str,
    notes: str = "",
    csv_path: str | None = None,
) -> dict[str, Any]:
    """Update the status of a specific ticket in the tracking spreadsheet."""
    path = csv_path or os.getenv("OPS_TRACKING_CSV_PATH", DEFAULT_CSV_PATH)
    rows = _read_all(path)
    target = next((r for r in rows if r["ticket_id"] == ticket_id), None)
    if not target:
        raise ValueError(f"Ticket with ID {ticket_id} not found in tracking sheet.")

    target["status"] = new_status
    target["updated_at"] = datetime.now(UTC).isoformat()
    if notes:
        existing_notes = target.get("notes", "")
        target["notes"] = (
            f"{existing_notes}; {notes}".strip("; ") if existing_notes else notes
        )

    _write_all(path, rows)
    return target
