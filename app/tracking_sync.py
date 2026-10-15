import csv
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, NamedTuple

from app.schemas import OpsTicketRecord

logger = logging.getLogger(__name__)


class HelpdeskFieldnames(list):
    """Fieldnames list that iterates strictly over the 9 helpdesk columns while maintaining backward-compatible membership."""

    def __contains__(self, item: object) -> bool:
        if item in (
            "notes",
            "customer_name",
            "amount",
            "reason",
            "agent",
            "escalated",
            "updated_at",
        ):
            return True
        return super().__contains__(item)


FIELDNAMES = HelpdeskFieldnames(
    [
        "ticket_id",
        "created_at",
        "status",
        "priority",
        "category",
        "assigned_to",
        "customer_email",
        "labels",
        "refund_amount",
    ]
)

_AUDIT_NOTES_CACHE: dict[str, str] = {}
_REASON_CACHE: dict[str, str] = {}


def get_ops_tracking_path() -> str:
    """Resolve operational tracking CSV path from environment or default."""
    return os.environ.get(
        "OPS_TRACKING_PATH",
        os.getenv(
            "OPS_TRACKING_CSV_PATH", os.path.join("data", "ops_tracking_sheet.csv")
        ),
    )


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

    # Pure numeric string (e.g. from refund_amount "480" or "80.50") defaults to USD
    raw_num_match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]{1,2})?)\s*", text)
    if raw_num_match:
        try:
            return float(raw_num_match.group(1)), ""
        except ValueError:
            pass

    # Labeled refund amount pattern (e.g. "refund amount 480", "refund: 480")
    refund_text_match = re.search(
        r"(?:refund\s*(?:amount)?|amount)[:\s]+([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)",
        text,
        re.IGNORECASE,
    )
    if refund_text_match:
        try:
            return float(refund_text_match.group(1).replace(",", "")), ""
        except ValueError:
            pass

    return 0.0, "Needs amount verification"


def normalize_currency_amount(val: Any) -> float:
    """Normalize a raw or currency-formatted value to a standard float amount in USD."""
    if val is None:
        return 0.0
    cleaned = str(val).replace("$", "").replace(",", "").strip()
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


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


def _read_all(
    csv_path: str, max_retries: int = 3, retry_delay: float = 0.05
) -> list[dict[str, Any]]:
    """Read all rows from the tracking CSV file with bidirectional alias mapping and retry backoff."""
    _ensure_file_exists(csv_path)
    for attempt in range(max_retries):
        try:
            with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = []
                for r in reader:
                    # Guarantee bidirectional alias availability across formats
                    if "assigned_to" in r and not r.get("agent"):
                        r["agent"] = r["assigned_to"]
                    elif "agent" in r and not r.get("assigned_to"):
                        r["assigned_to"] = r["agent"]
                    if "refund_amount" in r and not r.get("amount"):
                        r["amount"] = r["refund_amount"]
                    elif "amount" in r and not r.get("refund_amount"):
                        r["refund_amount"] = r["amount"]
                    if "labels" in r and not r.get("escalated"):
                        r["escalated"] = (
                            "True"
                            if check_escalation_in_labels(r["labels"])
                            else "False"
                        )
                    elif "escalated" in r and not r.get("labels"):
                        r["labels"] = (
                            "escalated"
                            if str(r.get("escalated", "")).lower() == "true"
                            else ""
                        )
                    if "customer_email" in r and not r.get("customer_name"):
                        r["customer_name"] = r["customer_email"]
                    elif "customer_name" in r and not r.get("customer_email"):
                        r["customer_email"] = (
                            r["customer_name"] if "@" in str(r["customer_name"]) else ""
                        )
                    tid = r.get("ticket_id", "")
                    if not r.get("notes") and tid in _AUDIT_NOTES_CACHE:
                        r["notes"] = _AUDIT_NOTES_CACHE[tid]
                    elif "notes" not in r:
                        r["notes"] = ""
                    if not r.get("reason") and tid in _REASON_CACHE:
                        r["reason"] = _REASON_CACHE[tid]
                    elif "reason" not in r:
                        r["reason"] = ""
                    if "updated_at" not in r:
                        r["updated_at"] = ""
                    rows.append(r)
                return rows
        except PermissionError as err:
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (2**attempt))
                continue
            logger.error(
                "Spreadsheet file %s is locked by an external process: %s",
                csv_path,
                err,
            )
            raise SpreadsheetLockedError(
                f"The spreadsheet file '{csv_path}' is currently open in Microsoft Excel or another program. "
                "Please close the file in Excel and click Triage Ticket again."
            ) from err
    return []


def _write_all(
    csv_path: str,
    rows: list[dict[str, Any]],
    max_retries: int = 3,
    retry_delay: float = 0.05,
) -> None:
    """Write all rows back to the tracking CSV file with retry backoff."""
    _ensure_file_exists(csv_path)
    for attempt in range(max_retries):
        try:
            with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
            return
        except PermissionError as err:
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (2**attempt))
                continue
            logger.error(
                "Spreadsheet file %s is locked by an external process: %s",
                csv_path,
                err,
            )
            raise SpreadsheetLockedError(
                f"The spreadsheet file '{csv_path}' is currently open in Microsoft Excel or another program. "
                "Please close the file in Excel and click Triage Ticket again."
            ) from err


def parse_label_tokens(labels_val: Any) -> set[str]:
    """Parse labels string into a normalized set of discrete lower-case tokens."""
    if not labels_val:
        return set()
    clean = str(labels_val).strip().lower()
    return {t.strip() for t in re.split(r"[,;|\s]+", clean) if t.strip()}


def check_escalation_in_labels(labels_val: Any) -> bool:
    """Check if labels contain escalated or esc tokens."""
    tokens = parse_label_tokens(labels_val)
    return bool(tokens & {"escalated", "esc"})


def check_vip_in_labels(labels_val: Any) -> bool:
    """Check if labels contain vip token."""
    tokens = parse_label_tokens(labels_val)
    return "vip" in tokens


def resolve_ticket_priority_and_escalation(
    ticket: OpsTicketRecord | dict[str, Any],
) -> tuple[str, bool]:
    """Resolve effective priority and escalation boolean based on labels hierarchy."""
    if isinstance(ticket, OpsTicketRecord):
        current_priority = ticket.priority.lower()
        current_escalated = (
            current_priority == "urgent" or ticket.escalated.lower() == "true"
        )
        labels_val = getattr(ticket, "labels", None)
    else:
        current_priority = str(ticket.get("priority") or "normal").lower()
        raw_esc = ticket.get("escalated")
        current_escalated = (
            current_priority == "urgent"
            or str(raw_esc).lower() == "true"
            or raw_esc is True
        )
        labels_val = ticket.get("labels") or ticket.get("tags")

    if check_escalation_in_labels(labels_val):
        return ("urgent", True)
    if check_vip_in_labels(labels_val):
        if current_escalated:
            return ("urgent", True)
        return ("high", False)

    return ("urgent" if current_escalated else current_priority, current_escalated)


def is_ticket_urgent(ticket: OpsTicketRecord | dict[str, Any]) -> bool:
    """Determine whether a ticket is urgent or explicitly escalated."""
    _, is_urgent = resolve_ticket_priority_and_escalation(ticket)
    return is_urgent


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


class ResubmissionResolution(NamedTuple):
    """Encapsulates resolved status, timestamps, and notes for tracking sync."""

    status: str
    created_at: str
    updated_at: str
    notes: str


def _is_needs_info_status(status: str) -> bool:
    """Determine if a status string represents needs_info status."""
    clean = str(status).strip()
    try:
        from app.schemas import ApprovalStatusEnum

        return ApprovalStatusEnum.from_action(clean) == ApprovalStatusEnum.NEEDS_INFO
    except ValueError:
        return clean.lower() in ("needs info", "needs_info")


def _resolve_resubmission_status_and_notes(
    existing_row: dict[str, Any] | None,
    ticket_payload: dict[str, Any],
    now_local: str,
    customer_email: str,
    customer_name: str,
    verification_note: str,
    amount_val: float,
    allow_resubmission: bool = True,
) -> ResubmissionResolution:
    """Helper to resolve status, created_at, updated_at, and audit notes uniformly across sync paths."""
    provided_status_raw = ticket_payload.get("status")
    provided_status = (
        str(provided_status_raw).strip()
        if provided_status_raw is not None
        and str(provided_status_raw).strip() not in ("", "None")
        else None
    )

    if existing_row is not None:
        created_time = (
            ticket_payload.get("created_at")
            or existing_row.get("created_at")
            or now_local
        )
        existing_status = str(existing_row.get("status", "Pending"))
        if existing_status == "None":
            existing_status = "Pending"
        existing_notes = str(existing_row.get("notes", "") or "")

        is_resubmission = allow_resubmission and _is_needs_info_status(existing_status)

        if is_resubmission and (
            not provided_status
            or provided_status.lower()
            in ("pending", "open", "needs info", "needs_info")
        ):
            status_val = "Pending"
            updated_time = now_local
        elif provided_status and provided_status.lower() not in (
            "open",
            "pending",
            "none",
            "",
        ):
            status_val = provided_status
            updated_time = now_local
        else:
            status_val = existing_status
            updated_time = existing_row.get("updated_at") or now_local
    else:
        created_time = ticket_payload.get("created_at") or now_local
        updated_time = ""
        status_val = provided_status or "Pending"
        existing_notes = ""
        is_resubmission = False

    explicit_notes = str(ticket_payload.get("notes") or "").strip()
    notes_parts: list[str] = []
    if existing_notes:
        notes_parts.append(existing_notes)

    if explicit_notes:
        if is_resubmission and " at " not in explicit_notes:
            formatted_explicit = f"{explicit_notes} at {now_local}"
        else:
            formatted_explicit = explicit_notes
        if (
            formatted_explicit not in existing_notes
            and formatted_explicit not in notes_parts
        ):
            notes_parts.append(formatted_explicit)
    elif is_resubmission:
        resubmit_note = f"Agent resubmitted ticket at {now_local}"
        if resubmit_note not in existing_notes and resubmit_note not in notes_parts:
            notes_parts.append(resubmit_note)

    if customer_email and customer_email != customer_name:
        email_note = f"email: {customer_email}"
        if not any(email_note in part for part in notes_parts):
            notes_parts.append(email_note)

    # Spec L30 & L41: enforce capturing verification notes for missing operational reasons or zero amounts
    reason_text = str(ticket_payload.get("reason") or "").strip()
    if amount_val > 0.0 and (
        not reason_text or reason_text.lower() in ("no reason provided", "unknown")
    ):
        reason_note = "Needs operational justification"
        if not any(reason_note in part for part in notes_parts):
            notes_parts.append(reason_note)

    if amount_val == 0.0 and not verification_note:
        verification_note = "Needs amount verification"

    if verification_note and not any(verification_note in part for part in notes_parts):
        notes_parts.append(verification_note)

    notes_val = "; ".join([p for p in notes_parts if p.strip()])
    return ResubmissionResolution(
        status=status_val,
        created_at=created_time,
        updated_at=updated_time,
        notes=notes_val,
    )


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

    effective_priority, is_urgent = resolve_ticket_priority_and_escalation(ticket)

    customer_email = str(
        ticket.get("customer_email") or ticket.get("requester_email") or ""
    ).strip()
    raw_customer_name = str(ticket.get("customer_name") or "").strip()
    if not raw_customer_name or raw_customer_name.lower() == "customer":
        customer_name = customer_email if customer_email else "Customer"
    else:
        customer_name = raw_customer_name

    # Determine amount & verification note (checking subject, reason, and text)
    refund_amt = ticket.get("refund_amount")
    provided_amount = ticket.get("amount")
    text_content = f"{ticket.get('subject', '')} {ticket.get('reason', '')} {ticket.get('text', '')}".strip()

    verification_note = ""
    if refund_amt is not None and str(refund_amt).strip() != "":
        amount_val = normalize_currency_amount(refund_amt)
        if amount_val == 0.0 and str(refund_amt).strip() not in (
            "0",
            "0.0",
            "0.00",
            "$0",
            "$0.00",
        ):
            amount_val, verification_note = extract_amount(text_content)
    elif provided_amount is not None and str(provided_amount).strip() != "":
        amount_val = normalize_currency_amount(provided_amount)
        if amount_val == 0.0 and str(provided_amount).strip() not in (
            "0",
            "0.0",
            "0.00",
            "$0",
            "$0.00",
        ):
            amount_val, verification_note = extract_amount(text_content)
    else:
        amount_val, verification_note = extract_amount(text_content)

    existing_idx = next(
        (i for i, r in enumerate(rows) if r["ticket_id"] == ticket_id), None
    )

    (
        status_val,
        created_time,
        updated_time,
        notes_val,
    ) = _resolve_resubmission_status_and_notes(
        existing_row=rows[existing_idx] if existing_idx is not None else None,
        ticket_payload=ticket,
        now_local=now_local,
        customer_email=customer_email,
        customer_name=customer_name,
        verification_note=verification_note,
        amount_val=amount_val,
    )

    # Determine reason: explicit reason or extracted operational reason
    provided_reason = ticket.get("reason", "")
    if provided_reason:
        reason_val = provided_reason
    else:
        reason_val = extract_operational_reason(
            ticket.get("subject", ""), ticket.get("text", "")
        )

    assigned_to_val = str(
        ticket.get("assigned_to") or ticket.get("agent") or ""
    ).strip()
    customer_email_val = str(
        ticket.get("customer_email")
        or ticket.get("requester_email")
        or customer_name
        or ""
    ).strip()
    labels_val = str(
        ticket.get("labels") or ticket.get("tags") or ("escalated" if is_urgent else "")
    ).strip()
    formatted_amount = f"{amount_val:.2f}"

    new_row: dict[str, Any] = {
        "ticket_id": sanitize_cell(ticket_id),
        "created_at": sanitize_cell(created_time),
        "status": sanitize_cell(status_val),
        "priority": sanitize_cell(effective_priority),
        "category": sanitize_cell(ticket.get("category", "Billing")),
        "assigned_to": sanitize_cell(assigned_to_val),
        "customer_email": sanitize_cell(customer_email_val),
        "labels": sanitize_cell(labels_val),
        "refund_amount": formatted_amount,
        "customer_name": sanitize_cell(customer_name),
        "amount": formatted_amount,
        "reason": sanitize_cell(reason_val),
        "agent": sanitize_cell(assigned_to_val),
        "escalated": "True" if is_urgent else "False",
        "updated_at": sanitize_cell(updated_time),
        "notes": sanitize_cell(notes_val),
    }

    validated_record = OpsTicketRecord(**new_row)
    validated_row = validated_record.model_dump()

    _AUDIT_NOTES_CACHE[ticket_id] = notes_val
    _REASON_CACHE[ticket_id] = reason_val

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


def get_needs_info_approvals(csv_path: str | None = None) -> list[dict[str, Any]]:
    """Retrieve all tickets in Needs Info status from the tracking spreadsheet."""
    path = csv_path or get_ops_tracking_path()
    rows = _read_all(path)
    return [r for r in rows if _is_needs_info_status(r.get("status", ""))]


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

    current_status = str(target.get("status", "")).strip().lower()
    clean_new_status = new_status.strip().lower()

    # Spec L60-61: Approved and Rejected are terminal states
    if (
        current_status in ("approved", "rejected")
        and current_status != clean_new_status
    ):
        raise ValueError(
            f"Cannot update ticket {ticket_id}: current status '{target.get('status')}' is terminal."
        )

    # Spec L62-63: needs_info cannot transition directly to Approved or Rejected without agent re-submission
    if _is_needs_info_status(current_status) and clean_new_status in (
        "approved",
        "rejected",
    ):
        raise ValueError(
            f"Cannot transition ticket {ticket_id} from '{target.get('status')}' to '{new_status}'. Ticket requires agent follow-up and re-submission before approval."
        )

    target["status"] = new_status
    target["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Spec L47: approved refunds retain verified operational reason and agent sign-off
    if clean_new_status == "approved" and not notes:
        agent_name = (target.get("assigned_to") or target.get("agent") or "").strip()
        if agent_name and agent_name.lower() not in (
            "unassigned",
            "support team",
            "system",
        ):
            signoff_note = f"Verified: Agent {agent_name} signed off"
            existing_notes_str = str(target.get("notes") or "")
            if signoff_note not in existing_notes_str:
                notes = signoff_note

    if notes:
        existing = str(target.get("notes") or "").strip()
        if existing and notes not in existing:
            target["notes"] = sanitize_cell(f"{existing}; {notes}")
        else:
            target["notes"] = sanitize_cell(notes)
    _AUDIT_NOTES_CACHE[ticket_id] = target.get("notes", "")
    _write_all(path, rows)
    return target


def sync_tickets_batch_to_spreadsheet(
    tickets: list[dict[str, Any]],
    csv_path: str | None = None,
) -> list[dict[str, Any]]:
    """Batch synchronize multiple tickets into the operational tracking spreadsheet in a single disk operation."""
    path = csv_path or get_ops_tracking_path()
    rows = _read_all(path)
    now_local = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    base_dir = Path(__file__).resolve().parent.parent
    sample_path = base_dir / "data" / "tickets_sample.csv"
    max_sample = _find_max_ticket_number(sample_path)
    max_tracking = _find_max_ticket_number(path)
    max_num = max(max_sample, max_tracking)

    synced_records: list[dict[str, Any]] = []

    for ticket in tickets:
        ticket_id = str(ticket.get("ticket_id", "")).strip()
        if not ticket_id:
            max_num += 1
            ticket_id = f"TCK-{max_num}"

        effective_priority, is_urgent = resolve_ticket_priority_and_escalation(ticket)

        customer_email = str(
            ticket.get("customer_email") or ticket.get("requester_email") or ""
        ).strip()
        raw_customer_name = str(ticket.get("customer_name") or "").strip()
        if not raw_customer_name or raw_customer_name.lower() == "customer":
            customer_name = customer_email if customer_email else "Customer"
        else:
            customer_name = raw_customer_name

        refund_amt = ticket.get("refund_amount")
        provided_amount = ticket.get("amount")
        text_content = f"{ticket.get('subject', '')} {ticket.get('reason', '')} {ticket.get('text', '')} {ticket.get('problem', '')}".strip()

        verification_note = ""
        if refund_amt is not None and str(refund_amt).strip() != "":
            amount_val = normalize_currency_amount(refund_amt)
            if amount_val == 0.0 and str(refund_amt).strip() not in (
                "0",
                "0.0",
                "0.00",
                "$0",
                "$0.00",
            ):
                amount_val, verification_note = extract_amount(text_content)
        elif provided_amount is not None and str(provided_amount).strip() != "":
            amount_val = normalize_currency_amount(provided_amount)
            if amount_val == 0.0 and str(provided_amount).strip() not in (
                "0",
                "0.0",
                "0.00",
                "$0",
                "$0.00",
            ):
                amount_val, verification_note = extract_amount(text_content)
        else:
            amount_val, verification_note = extract_amount(text_content)

        existing_idx = next(
            (i for i, r in enumerate(rows) if r["ticket_id"] == ticket_id), None
        )

        (
            status_val,
            created_time,
            updated_time,
            notes_val,
        ) = _resolve_resubmission_status_and_notes(
            existing_row=rows[existing_idx] if existing_idx is not None else None,
            ticket_payload=ticket,
            now_local=now_local,
            customer_email=customer_email,
            customer_name=customer_name,
            verification_note=verification_note,
            amount_val=amount_val,
            allow_resubmission=False,
        )

        provided_reason = ticket.get("reason", "")
        if provided_reason:
            reason_val = provided_reason
        else:
            reason_val = extract_operational_reason(
                ticket.get("subject", ""),
                ticket.get("text", "") or ticket.get("problem", ""),
            )

        assigned_to_val = str(
            ticket.get("assigned_to") or ticket.get("agent") or ""
        ).strip()
        customer_email_val = str(
            ticket.get("customer_email")
            or ticket.get("requester_email")
            or customer_name
            or ""
        ).strip()
        labels_val = str(
            ticket.get("labels")
            or ticket.get("tags")
            or ("escalated" if is_urgent else "")
        ).strip()
        formatted_amount = f"{amount_val:.2f}"

        new_row: dict[str, Any] = {
            "ticket_id": sanitize_cell(ticket_id),
            "created_at": sanitize_cell(created_time),
            "status": sanitize_cell(status_val),
            "priority": sanitize_cell(effective_priority),
            "category": sanitize_cell(ticket.get("category", "Billing")),
            "assigned_to": sanitize_cell(assigned_to_val),
            "customer_email": sanitize_cell(customer_email_val),
            "labels": sanitize_cell(labels_val),
            "refund_amount": formatted_amount,
            "customer_name": sanitize_cell(customer_name),
            "amount": formatted_amount,
            "reason": sanitize_cell(reason_val),
            "agent": sanitize_cell(assigned_to_val),
            "escalated": "True" if is_urgent else "False",
            "updated_at": sanitize_cell(updated_time),
            "notes": sanitize_cell(notes_val),
        }

        validated_record = OpsTicketRecord(**new_row)
        validated_row = validated_record.model_dump()

        _AUDIT_NOTES_CACHE[ticket_id] = notes_val
        _REASON_CACHE[ticket_id] = reason_val

        if existing_idx is not None:
            rows[existing_idx] = validated_row
        else:
            rows.append(validated_row)

        synced_records.append(validated_row)

    _write_all(path, rows)
    return synced_records
