"""Day 1 Ticket Summary calculation integration service."""

from datetime import datetime
from typing import Any, TypedDict

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
    priority: str


def parse_timestamp(ts_val: Any) -> datetime | None:
    """Parse timestamp string or datetime into UTC datetime using Day 1 parser."""
    return parse_iso_timestamp(ts_val)


def compute_metrics_from_tickets(
    tickets: list[TicketRecord],
) -> tuple[TicketMetrics, list[str]]:
    """Compute summary metrics from in-memory API tickets using Day 1 calculation engine."""
    return ticket_summary.compute_metrics(tickets)
