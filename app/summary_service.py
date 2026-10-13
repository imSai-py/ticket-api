"""Day 1 Ticket Summary calculation integration."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

RESOLVED_STATUSES = {"resolved", "closed"}


@dataclass
class TicketMetrics:
    """Metrics computed across ticket dataset."""

    category_counts: Counter
    overall_average_seconds: Optional[float]
    category_average_seconds: Dict[str, Optional[float]]
    skipped_tickets: Dict[str, List[str]]


def parse_timestamp(ts_val) -> Optional[datetime]:
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
    tickets: List[Dict],
) -> Tuple[TicketMetrics, List[str]]:
    """Compute category counts, resolution metrics, and track skipped tickets."""
    category_counts: Counter = Counter(
        t.get("category", "Uncategorized") for t in tickets
    )
    category_durations: Dict[str, List[float]] = defaultdict(list)
    all_durations: List[float] = []

    skipped_tickets: Dict[str, List[str]] = defaultdict(list)
    resolution_warnings: List[str] = []

    for t in tickets:
        ticket_id = t.get("ticket_id", "")
        category = t.get("category", "Uncategorized")
        created_dt = parse_timestamp(t.get("created_at") or t.get("created"))
        resolved_val = t.get("resolved_at") or t.get("resolved")
        status = str(t.get("status", "")).strip().lower()

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
            skipped_tickets["Resolved before created"].append(ticket_id)
            continue

        if created_dt and resolved_dt >= created_dt:
            dur_seconds = (resolved_dt - created_dt).total_seconds()
            all_durations.append(dur_seconds)
            category_durations[category].append(dur_seconds)

    overall_avg_sec = sum(all_durations) / len(all_durations) if all_durations else None

    category_averages: Dict[str, Optional[float]] = {}
    for category in sorted(category_counts.keys()):
        durations = category_durations.get(category, [])
        category_averages[category] = (
            sum(durations) / len(durations) if durations else None
        )

    metrics = TicketMetrics(
        category_counts=category_counts,
        overall_average_seconds=overall_avg_sec,
        category_average_seconds=category_averages,
        skipped_tickets=dict(skipped_tickets),
    )
    return metrics, resolution_warnings
