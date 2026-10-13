"""Day 1 Ticket Summary calculation engine module."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

REQUIRED_COLUMNS = {
    "ticket_id",
    "created_at",
    "resolved_at",
    "category",
    "priority",
    "status",
}

RESOLVED_STATUSES = {"resolved", "closed"}


@dataclass
class TicketMetrics:
    """Computed ticket summary metrics."""

    category_counts: Counter
    overall_average_seconds: float | None
    category_average_seconds: dict[str, float | None]
    skipped_tickets: dict[str, list[str]]

    def overall_average_hours(self) -> float:
        """Return overall average resolution duration in hours, rounded to 2 decimals."""
        if self.overall_average_seconds is None:
            return 0.0
        return round(self.overall_average_seconds / 3600.0, 2)

    def category_average_hours(self) -> dict[str, float | None]:
        """Return category resolution duration averages in hours, rounded to 2 decimals."""
        return {
            cat: round(sec / 3600.0, 2) if sec is not None else None
            for cat, sec in self.category_average_seconds.items()
        }


def parse_iso_timestamp(ts_val: Any) -> datetime | None:
    """Parse standard ISO-8601 timestamp string or datetime object and normalize to UTC."""
    if isinstance(ts_val, datetime):
        if ts_val.tzinfo is None:
            return ts_val.replace(tzinfo=UTC)
        return ts_val.astimezone(UTC)
    if not ts_val or not str(ts_val).strip():
        return None
    cleaned = str(ts_val).strip()
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except (ValueError, TypeError):
        return None


def compute_metrics(
    rows: list[dict[str, Any]],
) -> tuple[TicketMetrics, list[str]]:
    """Compute category counts, resolution metrics, and track skipped tickets.

    Returns:
        Tuple of (TicketMetrics, resolution_warnings)
    """
    category_counts: Counter = Counter(
        row.get("category", "Uncategorized") for row in rows
    )
    category_durations: dict[str, list[float]] = defaultdict(list)
    all_durations: list[float] = []

    skipped_tickets: dict[str, list[str]] = defaultdict(list)
    resolution_warnings: list[str] = []

    for row in rows:
        ticket_id = str(row.get("ticket_id") or "")
        category = str(row.get("category") or "Uncategorized")
        created_val = row.get("created") if "created" in row else row.get("created_at")
        created_dt = parse_iso_timestamp(created_val)
        resolved_val = (
            row.get("resolved") if "resolved" in row else row.get("resolved_at")
        )
        status = str(row.get("status") or "").strip().lower()

        if not resolved_val:
            skipped_tickets["Unresolved / Missing resolution date"].append(ticket_id)
            continue

        if status not in RESOLVED_STATUSES:
            skipped_tickets["Unresolved / Non-resolved status"].append(ticket_id)
            continue

        resolved_dt = parse_iso_timestamp(resolved_val)
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

    category_averages: dict[str, float | None] = {}
    for category in sorted(category_counts.keys()):
        durations = category_durations.get(category, [])
        category_averages[category] = (
            sum(durations) / len(durations) if durations else None
        )

    metrics = TicketMetrics(
        category_counts=category_counts,
        overall_average_seconds=overall_avg_sec,
        category_average_seconds=category_averages,
        skipped_tickets=skipped_tickets,
    )
    return metrics, resolution_warnings
