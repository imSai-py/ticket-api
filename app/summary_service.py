"""Integration adapter for Day 1 Ticket Summary calculation."""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TypedDict

# Ensure ticket_summary from repository root is importable
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from ticket_summary import (
    TicketMetrics,
    compute_metrics,
    parse_iso_timestamp,
    RESOLVED_STATUSES,
)


class TicketRecord(TypedDict, total=False):
    """Schema for individual ticket records processed by the summary service."""

    ticket_id: str
    category: str
    status: str
    created_at: Any
    created: Any
    resolved_at: Any
    resolved: Any


def parse_timestamp(ts_val: Any):
    """Parse timestamp string or datetime into UTC datetime using Day 1 parser."""
    return parse_iso_timestamp(ts_val)


def compute_metrics_from_tickets(
    tickets: List[TicketRecord],
) -> Tuple[TicketMetrics, List[str]]:
    """Compute category counts, resolution metrics, and track skipped tickets using Day 1 module."""
    return compute_metrics(tickets)
