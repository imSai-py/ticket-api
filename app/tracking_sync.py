import csv
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from app.schemas import OpsTicketRecord

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
    "notes",
]


def get_ops_tracking_path() -> str:
    """Resolve operational tracking CSV path from environment or default."""
    return os.environ.get(
        "OPS_TRACKING_PATH",
        os.getenv(
            "OPS_TRACKING_CSV_PATH", os.path.join("data", "ops_tracking_sheet.csv")
        ),
    )


DEFAULT_CSV_PATH = os.path.join("data", "ops_tracking_sheet.csv")


def check_storage_health(csv_path: str | None = None) -> None:
    """Verify tracking spreadsheet storage can be read without lock contention."""
    target_path = csv_path or get_ops_tracking_path()
    _read_all(target_path)


_REASON_KEYWORD_MAP: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        (
            "billed twice",
            "charged twice",
            "duplicate charge",
            "double billed",
            "charged two times",
            "duplicate",
        ),
        "Duplicate charge refund",
    ),
    (
        (
            "overcharged",
            "incorrect charge",
            "wrong amount",
            "charged more",
        ),
        "Overcharge dispute",
    ),
    (
        (
            "cancel",
            "cancellation",
            "subscription renewal",
            "annual renewal",
            "annual subscription",
        ),
        "Subscription dispute",
    ),
    (
        (
            "unauthorized",
            "fraud",
            "stolen card",
            "didn't authorize",
        ),
        "Unauthorized charge dispute",
    ),
    (
        (
            "refund",
            "reimburse",
            "chargeback",
        ),
        "Customer refund request",
    ),
)


def extract_amount(text: str) -> tuple[float, str]:
    """Extract currency amount from text or flag for verification if missing."""
    if not text:
        return 0.0, "Needs amount verification"

    # Match patterns like $1,250.00, $49.99, $ 50, 1,250.00 USD, 50 dollars
    dollar_match = re.search(
        r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)",
        text,
    )
    if dollar_match:
        try:
            return float(dollar_match.group(1).replace(",", "")), ""
        except ValueError:
            pass

    usd_match = re.search(
        r"([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)\s*(?:usd|dollars?)",
        text,
        re.IGNORECASE,
    )
    if usd_match:
        try:
            return float(usd_match.group(1).replace(",", "")), ""
        except ValueError:
            pass

    return 0.0, "Needs amount verification"


class SpreadsheetLockedError(Exception):
    """Raised when the tracking spreadsheet file is locked by an external process."""


def _ensure_file_exists(csv_path: str) -> None:
    """Ensure directory and CSV file with header exist."""
    os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        try:
            with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
                writer.writeheader()
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


def _read_all(csv_path: str) -> list[dict[str, Any]]:
    """Read all rows from the tracking CSV file."""
    _ensure_file_exists(csv_path)
    try:
        with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)
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


def is_ticket_urgent(ticket: OpsTicketRecord | dict[str, Any]) -> bool:
    """Determine whether a ticket is urgent or explicitly escalated."""
    if isinstance(ticket, OpsTicketRecord):
        return ticket.priority == "urgent" or ticket.escalated.lower() == "true"
    return (
        ticket.get("priority") == "urgent"
        or str(ticket.get("escalated", "")).lower() == "true"
        or ticket.get("escalated") is True
    )


def _find_max_ticket_number(path: Path | str) -> int:
    """Extract highest numerical suffix from TCK-<number> in a given CSV file."""
    highest = 1019
    p = Path(path)
    if not p.exists():
        return highest
    try:
        with open(p, mode="r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                tid = row.get("ticket_id", "")
                m = re.search(r"TCK-(\d+)", tid, re.IGNORECASE)
                if m:
                    highest = max(highest, int(m.group(1)))
    except (OSError, csv.Error, ValueError) as err:
        logger.debug("Could not inspect %s for max ID: %s", path, err)
    return highest


def get_next_ticket_id(csv_path: str | None = None) -> str:
    """Generate the next sequential ticket ID (e.g. TCK-1020)."""
    base_dir = Path(__file__).resolve().parent.parent
    sample_path = base_dir / "data" / "tickets_sample.csv"
    tracking_path = csv_path or get_ops_tracking_path()
    max_sample = _find_max_ticket_number(sample_path)
    max_tracking = _find_max_ticket_number(tracking_path)
    highest = max(max_sample, max_tracking)
    return f"TCK-{highest + 1}"


def sanitize_cell(value: Any) -> str:
    """Normalize whitespace and strip newlines to ensure single-line CSV rows."""
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return " ".join(text.split())


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

    for keywords, label in _REASON_KEYWORD_MAP:
        if any(k in full for k in keywords):
            return f"{label}{inv_suffix}"

    clean_subj = sanitize_cell(subject)
    if clean_subj:
        return clean_subj
    clean_text = sanitize_cell(text)
    return clean_text[:80]


def sync_ticket_to_spreadsheet(
    ticket: dict[str, Any], csv_path: str | None = None
) -> dict[str, Any]:
    """Sync a ticket into the operations tracking spreadsheet."""
    path = csv_path or get_ops_tracking_path()
    rows = _read_all(path)
    now_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ticket_id = str(ticket.get("ticket_id", "")).strip()
    if not ticket_id:
        ticket_id = get_next_ticket_id(csv_path=path)

    # Determine amount & verification note (checking subject, reason, and text)
    provided_amount = ticket.get("amount")
    text_content = f"{ticket.get('subject', '')} {ticket.get('reason', '')} {ticket.get('text', '')}".strip()

    verification_note = ""
    if provided_amount is not None and float(provided_amount) > 0:
        amount_val = float(provided_amount)
    else:
        amount_val, verification_note = extract_amount(text_content)

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
        existing_notes = rows[existing_idx].get("notes", "")
    else:
        created_time = now_local
        updated_time = ""
        status_val = str(ticket.get("status", "Pending"))
        existing_notes = ""

    explicit_notes = str(ticket.get("notes") or "").strip()
    notes_parts: list[str] = []
    if explicit_notes:
        notes_parts.append(explicit_notes)
    elif existing_notes:
        notes_parts.append(existing_notes)

    if verification_note and verification_note not in notes_parts:
        notes_parts.append(verification_note)

    notes_val = "; ".join(notes_parts)

    # Determine reason: explicit reason or extracted operational reason
    provided_reason = ticket.get("reason", "")
    if provided_reason:
        reason_val = provided_reason
    else:
        reason_val = extract_operational_reason(
            ticket.get("subject", ""), ticket.get("text", "")
        )

    new_row: dict[str, Any] = {
        "ticket_id": sanitize_cell(ticket_id),
        "customer_name": sanitize_cell(ticket.get("customer_name") or "Customer"),
        "category": sanitize_cell(ticket.get("category", "Billing")),
        "priority": sanitize_cell(ticket.get("priority", "normal")),
        "amount": f"{amount_val:.2f}",
        "reason": sanitize_cell(reason_val),
        "agent": sanitize_cell(ticket.get("agent") or "Mara"),
        "status": sanitize_cell(status_val),
        "escalated": "True" if is_urgent else "False",
        "created_at": sanitize_cell(created_time),
        "updated_at": sanitize_cell(updated_time),
        "notes": sanitize_cell(notes_val),
    }

    validated_record = OpsTicketRecord(**new_row)
    validated_row = validated_record.model_dump()

    if existing_idx is not None:
        rows[existing_idx] = validated_row
    else:
        rows.append(validated_row)

    _write_all(path, rows)
    return validated_row


def get_pending_approvals(csv_path: str | None = None) -> list[dict[str, Any]]:
    """Retrieve all tickets in Pending status from the tracking spreadsheet."""
    path = csv_path or get_ops_tracking_path()
    rows = _read_all(path)
    return [r for r in rows if r["status"] == "Pending"]


def update_approval_status(
    ticket_id: str,
    new_status: str,
    notes: str = "",
    csv_path: str | None = None,
) -> dict[str, Any]:
    """Update the status of a specific ticket in the tracking spreadsheet."""
    path = csv_path or get_ops_tracking_path()
    rows = _read_all(path)
    target = next((r for r in rows if r["ticket_id"] == ticket_id), None)
    if not target:
        raise ValueError(f"Ticket with ID {ticket_id} not found in tracking sheet.")

    target["status"] = new_status
    target["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if notes:
        existing = str(target.get("notes") or "").strip()
        if existing and notes not in existing:
            target["notes"] = sanitize_cell(f"{existing}; {notes}")
        else:
            target["notes"] = sanitize_cell(notes)
    _write_all(path, rows)
    return target
