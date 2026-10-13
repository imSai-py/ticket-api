"""Day 1 Ticket Summary calculation integration service."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, TypedDict

import ticket_summary
from ticket_summary import TicketMetrics, parse_iso_timestamp

RESOLVED_STATUSES = ticket_summary.RESOLVED_STATUSES


class TicketRecord(TypedDict, total=False):
    """Schema for individual ticket records processed by the summary service."""

    ticket_id: str
    category: str
    status: str
    created_at: Any
    created: Any
    resolved_at: Any
    resolved: Any


def parse_timestamp(ts_val: Any) -> Optional[datetime]:
    """Parse timestamp string or datetime into UTC datetime using Day 1 parser."""
    if isinstance(ts_val, datetime):
        return ts_val if ts_val.tzinfo else ts_val.replace(tzinfo=timezone.utc)
    return parse_iso_timestamp(str(ts_val) if ts_val else "")


def compute_metrics_from_tickets(
    tickets: List[TicketRecord],
) -> Tuple[TicketMetrics, List[str]]:
    """Adapt in-memory API tickets and compute metrics using Day 1 ticket_summary module."""
    raw_rows: List[Dict[str, str]] = []
    for t in tickets:
        created_val = t.get("created")
        if isinstance(created_val, datetime):
            created_str = created_val.isoformat()
        else:
            created_str = str(t.get("created_at") or "")

        resolved_val = t.get("resolved")
        if isinstance(resolved_val, datetime):
            resolved_str = resolved_val.isoformat()
        else:
            resolved_str = str(t.get("resolved_at") or "")

        raw_rows.append(
            {
                "ticket_id": str(t.get("ticket_id") or ""),
                "category": str(t.get("category") or "Uncategorized"),
                "status": str(t.get("status") or ""),
                "created_at": created_str,
                "resolved_at": resolved_str,
                "priority": str(t.get("priority") or ""),
            }
        )

    return ticket_summary.compute_metrics(raw_rows)
