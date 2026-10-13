"""Day 1 Ticket Summary calculation integration service."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, TypedDict

RESOLVED_STATUSES = {"resolved", "closed"}


class TicketRecord(TypedDict, total=False):
    """Schema for individual ticket records processed by the summary service."""

    ticket_id: str
    category: str
    status: str
    created_at: Any
    created: Any
    resolved_at: Any
    resolved: Any


@dataclass
class TicketMetrics:
    """Computed ticket summary metrics."""

    category_counts: Counter
    overall_average_seconds: Optional[float]
    category_average_seconds: Dict[str, Optional[float]]
    skipped_tickets: Dict[str, List[str]]

    def overall_average_hours(self) -> float:
        """Return overall average resolution duration in hours, rounded to 2 decimals."""
        if self.overall_average_seconds is None:
            return 0.0
        return round(self.overall_average_seconds / 3600.0, 2)

    def category_average_hours(self) -> Dict[str, Optional[float]]:
        """Return category resolution duration averages in hours, rounded to 2 decimals."""
        return {
            cat: round(sec / 3600.0, 2) if sec is not None else None
            for cat, sec in self.category_average_seconds.items()
        }


def parse_timestamp(ts_val: Any) -> Optional[datetime]:
    """Parse timestamp string or datetime into UTC datetime."""
    if isinstance(ts_val, datetime):
        if ts_val.tzinfo is None:
            return ts_val.replace(tzinfo=timezone.utc)
        return ts_val.astimezone(timezone.utc)

    if not ts_val or not str(ts_val).strip():
        return None

    cleaned = str(ts_val).strip()
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return None


def compute_metrics_from_tickets(
    tickets: List[TicketRecord],
) -> Tuple[TicketMetrics, List[str]]:
    """Compute category counts, resolution metrics, and track skipped tickets."""
    category_counts: Counter = Counter(
        ticket.get("category", "Uncategorized") for ticket in tickets
    )
    category_durations: Dict[str, List[float]] = defaultdict(list)
    all_durations: List[float] = []

    skipped_tickets: Dict[str, List[str]] = defaultdict(list)
    resolution_warnings: List[str] = []

    for ticket in tickets:
        ticket_id = ticket.get("ticket_id", "")
        category = ticket.get("category", "Uncategorized")
        created_dt = parse_timestamp(ticket.get("created_at") or ticket.get("created"))
        resolved_val = ticket.get("resolved_at") or ticket.get("resolved")
        status = str(ticket.get("status", "")).strip().lower()

        if not resolved_val:
            skipped_tickets["Unresolved / Missing resolution date"].append(ticket_id)
            continue

        if status not in RESOLVED_STATUSES:
            skipped_tickets["Unresolved / Non-resolved status"].append(ticket_id)
            continue

        resolved_dt = parse_timestamp(resolved_val)
        if resolved_dt is None:
            resolution_warnings.append(
                f"Warning: {ticket_id}: Invalid resolved_at timestamp."
            )
            skipped_tickets["Invalid resolution date"].append(ticket_id)
            continue

        if created_dt and resolved_dt < created_dt:
            resolution_warnings.append(
                f"Warning: {ticket_id}: Resolved date earlier than created date."
            )
            skipped_tickets["Resolved earlier than created"].append(ticket_id)
            continue

        if created_dt and resolved_dt >= created_dt:
            dur_seconds = (resolved_dt - created_dt).total_seconds()
            all_durations.append(dur_seconds)
            category_durations[category].append(dur_seconds)

    overall_avg_sec = (
        sum(all_durations) / len(all_durations) if all_durations else None
    )

    category_averages: Dict[str, Optional[float]] = {}
    for cat in sorted(category_counts.keys()):
        durations = category_durations.get(cat, [])
        category_averages[cat] = (
            sum(durations) / len(durations) if durations else None
        )

    metrics = TicketMetrics(
        category_counts=category_counts,
        overall_average_seconds=overall_avg_sec,
        category_average_seconds=category_averages,
        skipped_tickets=dict(skipped_tickets),
    )
    return metrics, resolution_warnings
