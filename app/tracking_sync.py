import csv
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

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


class SpreadsheetLockedError(Exception):
    """Raised when the tracking spreadsheet file is locked by an external process."""


def _write_all(csv_path: str, rows: list[dict[str, Any]]) -> None:
    """Write all rows back to the tracking CSV file."""
    _ensure_file_exists(csv_path)
    try:
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    except PermissionError as err:
        logger.error(
            "Spreadsheet file %s is locked by an external process: %s",
            csv_path,
            err,
        )
        raise SpreadsheetLockedError(
            f"The spreadsheet file '{csv_path}' is currently open in Microsoft Excel or another program. "
            "Please close the file in Excel and click Triage Ticket again."
        ) from err


def is_ticket_urgent(ticket: dict[str, Any]) -> bool:
    """Determine whether a ticket is urgent or explicitly escalated."""
    return (
        ticket.get("priority") == "urgent"
        or str(ticket.get("escalated", "")).lower() == "true"
        or ticket.get("escalated") is True
    )


def get_next_ticket_id(csv_path: str | None = None) -> str:
    """Generate the next sequential ticket ID (e.g. TCK-1020)."""
    highest = 1019  # baseline from sample data

    # Check sample tickets file if present
    base_dir = Path(__file__).resolve().parent.parent
    sample_path = base_dir / "data" / "tickets_sample.csv"
    if sample_path.exists():
        try:
            with open(sample_path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    tid = row.get("ticket_id", "")
                    m = re.search(r"TCK-(\d+)", tid, re.IGNORECASE)
                    if m:
                        highest = max(highest, int(m.group(1)))
        except (OSError, csv.Error, ValueError) as err:
            logger.debug("Could not inspect sample tickets for max ID: %s", err)

    # Check ops tracking sheet
    path = csv_path or os.getenv("OPS_TRACKING_CSV_PATH", DEFAULT_CSV_PATH)
    if os.path.exists(path):
        try:
            with open(path, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    tid = row.get("ticket_id", "")
                    m = re.search(r"TCK-(\d+)", tid, re.IGNORECASE)
                    if m:
                        highest = max(highest, int(m.group(1)))
        except (OSError, csv.Error, ValueError) as err:
            logger.debug("Could not inspect tracking sheet for max ID: %s", err)

    return f"TCK-{highest + 1}"


def extract_operational_reason(subject: str, text: str) -> str:
    """Extract a meaningful operational reason for approval rather than copying subject."""
    full = f"{subject} {text}".lower()

    # Check for order / invoice identifier
    inv_match = re.search(
        r"\b(?:invoice|inv|order)\b\s*(?:#|no\.?|num)?\s*([0-9A-Za-z-]+)",
        f"{subject} {text}",
        re.IGNORECASE,
    )
    inv_suffix = f" ({inv_match.group(0).strip()})" if inv_match else ""

    if any(
        k in full
        for k in [
            "billed twice",
            "charged twice",
            "duplicate charge",
            "double billed",
            "charged two times",
        ]
    ):
        return f"Duplicate charge refund{inv_suffix}"
    if any(
        k in full
        for k in [
            "overcharged",
            "incorrect charge",
            "wrong amount",
            "charged more",
        ]
    ):
        return f"Overcharge dispute{inv_suffix}"
    if any(k in full for k in ["cancel", "cancellation", "subscription renewal"]):
        return f"Subscription dispute{inv_suffix}"
    if "refund" in full:
        return f"Refund request{inv_suffix}"
    if any(k in full for k in ["locked out", "lockout", "password", "login"]):
        return "Account access recovery"
    if any(k in full for k in ["freeze", "freezing", "crash", "bug", "error"]):
        return "Application technical issue"
    if any(k in full for k in ["tracking", "shipment", "delivery"]):
        return f"Order delivery status{inv_suffix}"

    clean_subj = " ".join(subject.replace("\r", " ").replace("\n", " ").split())
    if clean_subj:
        return clean_subj
    clean_text = " ".join(text.replace("\r", " ").replace("\n", " ").split())
    return clean_text[:80]


def sanitize_cell(value: Any) -> str:
    """Normalize whitespace and strip newlines to ensure single-line CSV rows."""
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return " ".join(text.split())


def sync_ticket_to_spreadsheet(
    ticket: dict[str, Any], csv_path: str | None = None
) -> dict[str, Any]:
    """Sync a ticket into the operations tracking spreadsheet."""
    path = csv_path or os.getenv("OPS_TRACKING_CSV_PATH", DEFAULT_CSV_PATH)
    rows = _read_all(path)
    now_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ticket_id = str(ticket.get("ticket_id", "")).strip()
    if not ticket_id:
        ticket_id = get_next_ticket_id(csv_path=path)

    # Determine amount
    provided_amount = ticket.get("amount")
    text_content = f"{ticket.get('reason', '')} {ticket.get('text', '')}".strip()

    if provided_amount is not None and float(provided_amount) > 0:
        amount_val = float(provided_amount)
    else:
        amount_val, _ = extract_amount(text_content)

    existing_idx = next(
        (i for i, r in enumerate(rows) if r["ticket_id"] == ticket_id), None
    )

    is_urgent = is_ticket_urgent(ticket)

    # If ticket already exists and status was not explicitly passed in payload, retain existing status
    if existing_idx is not None:
        created_time = rows[existing_idx].get("created_at") or now_local
        updated_time = rows[existing_idx].get("updated_at") or ""
        status_val = (
            rows[existing_idx].get("status", "Pending")
            if "status" not in ticket
            else str(ticket.get("status", "Pending"))
        )
    else:
        created_time = now_local
        updated_time = ""
        status_val = str(ticket.get("status", "Pending"))

    new_row: dict[str, Any] = {
        "ticket_id": sanitize_cell(ticket_id),
        "customer_name": sanitize_cell(ticket.get("customer_name") or "Customer"),
        "category": sanitize_cell(ticket.get("category", "Billing")),
        "priority": sanitize_cell(ticket.get("priority", "normal")),
        "amount": f"{amount_val:.2f}",
        "reason": sanitize_cell(ticket.get("reason", "")),
        "agent": sanitize_cell(ticket.get("agent") or "Mara"),
        "status": sanitize_cell(status_val),
        "escalated": "True" if is_urgent else "False",
        "created_at": sanitize_cell(created_time),
        "updated_at": sanitize_cell(updated_time),
    }

    if existing_idx is not None:
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
    target["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _write_all(path, rows)
    return target
