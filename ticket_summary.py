"""Ticket summary CLI tool."""

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


def parse_iso_timestamp(ts_str: Any) -> Optional[datetime]:
    """Parse timestamp string or datetime and normalize to UTC."""
    if isinstance(ts_str, datetime):
        if ts_str.tzinfo is None:
            return ts_str.replace(tzinfo=timezone.utc)
        return ts_str.astimezone(timezone.utc)

    if not ts_str or not str(ts_str).strip():
        return None
    cleaned = str(ts_str).strip()
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


def format_duration(seconds: Optional[float]) -> str:
    """Format duration in seconds into human-readable duration string."""
    if seconds is None:
        return "N/A (No resolved tickets)"

    total_hours = seconds / 3600.0
    total_sec = round(seconds)

    days = total_sec // 86400
    rem_sec = total_sec % 86400
    hours = rem_sec // 3600
    rem_sec = rem_sec % 3600
    minutes = rem_sec // 60

    days_label = f"{days} day" if days == 1 else f"{days} days"
    hours_label = f"{hours} hour" if hours == 1 else f"{hours} hours"
    minutes_label = f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"

    formatted_str = f"{days_label}, {hours_label}, {minutes_label}"
    return f"{formatted_str} ({total_hours:.2f} hours)"


def read_and_validate_csv(
    file_path: Path,
) -> Tuple[List[Dict[str, str]], List[str], List[str]]:
    """Read CSV file, validate headers, trim whitespace, and validate rows.

    Returns:
        Tuple of (valid_rows, fatal_errors, row_warnings)
    """
    if not file_path.exists():
        return [], [f"Error: File '{file_path}' does not exist."], []

    if file_path.is_dir():
        return (
            [],
            [f"Error: Path '{file_path}' is a directory, not a file."],
            [],
        )

    try:
        with open(file_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header_row = next(reader, None)

            if header_row is None:
                return [], [f"Error: File '{file_path}' is empty."], []

            clean_headers = [col.strip() for col in header_row]
            missing_cols = REQUIRED_COLUMNS - set(clean_headers)
            if missing_cols:
                missing_str = ", ".join(sorted(missing_cols))
                return (
                    [],
                    [f"Error: Missing required column(s): {missing_str}."],
                    [],
                )

            valid_rows: List[Dict[str, str]] = []
            row_warnings: List[str] = []

            for row_idx, row in enumerate(reader, start=2):
                if not row or not any(cell.strip() for cell in row):
                    continue

                padded_row = row + [""] * (len(clean_headers) - len(row))
                row_dict = {
                    h: padded_row[idx].strip() for idx, h in enumerate(clean_headers)
                }

                ticket_id = row_dict.get("ticket_id", "").strip()
                if not ticket_id:
                    row_warnings.append(f"Warning: Row {row_idx}: Missing ticket_id.")
                    continue

                category = row_dict.get("category", "").strip()
                if not category:
                    row_warnings.append(f"Warning: {ticket_id}: Missing category.")
                    continue

                priority = row_dict.get("priority", "").strip()
                if not priority:
                    row_warnings.append(f"Warning: {ticket_id}: Missing priority.")
                    continue

                status = row_dict.get("status", "").strip()
                if not status:
                    row_warnings.append(f"Warning: {ticket_id}: Missing status.")
                    continue

                created_str = row_dict.get("created_at", "").strip()
                created_dt = parse_iso_timestamp(created_str)
                if not created_str or created_dt is None:
                    row_warnings.append(
                        f"Warning: {ticket_id}: Invalid or missing created_at."
                    )
                    continue

                valid_rows.append(row_dict)

            return valid_rows, [], row_warnings
    except Exception as exc:
        return [], [f"Error reading '{file_path}': {exc}"], []


def compute_metrics(
    rows: List[Dict[str, str]],
) -> Tuple[TicketMetrics, List[str]]:
    """Compute category counts, resolution metrics, and track skipped tickets.

    Returns:
        Tuple of (TicketMetrics, resolution_warnings)
    """
    category_counts: Counter = Counter(
        row.get("category", "Uncategorized") for row in rows
    )
    category_durations: Dict[str, List[float]] = defaultdict(list)
    all_durations: List[float] = []

    skipped_tickets: Dict[str, List[str]] = defaultdict(list)
    resolution_warnings: List[str] = []

    for row in rows:
        ticket_id = row.get("ticket_id", "")
        category = row.get("category", "Uncategorized")
        created_dt = parse_iso_timestamp(row.get("created_at", ""))
        resolved_str = row.get("resolved_at", "").strip()
        status = row.get("status", "").strip().lower()

        if not resolved_str:
            skipped_tickets["Unresolved / Missing resolution date"].append(ticket_id)
            continue

        if status not in RESOLVED_STATUSES:
            skipped_tickets["Unresolved / Non-resolved status"].append(ticket_id)
            continue

        resolved_dt = parse_iso_timestamp(resolved_str)
        if resolved_dt is None:
            resolution_warnings.append(
                f"Warning: {ticket_id}: Invalid resolved_at timestamp."
            )
            skipped_tickets["Invalid resolution date"].append(ticket_id)
            continue

        if created_dt and resolved_dt < created_dt:
            resolution_warnings.append(
                f"Warning: {ticket_id}: Resolved date earlier than created" " date."
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
        skipped_tickets=skipped_tickets,
    )
    return metrics, resolution_warnings


def format_summary_text(metrics: TicketMetrics) -> str:
    """Format ticket metrics into clean text output."""
    overall_avg_str = format_duration(metrics.overall_average_seconds)

    lines: List[str] = [
        "Ticket Summary",
        "==============",
        f"Average Resolution Time: {overall_avg_str}",
        "",
        "Tickets by Category:",
    ]

    for category in sorted(metrics.category_counts.keys()):
        count = metrics.category_counts[category]
        cat_avg_str = format_duration(metrics.category_average_seconds.get(category))
        lines.append(f"  {category}: {count} (Avg Resolution: {cat_avg_str})")

    if metrics.skipped_tickets:
        lines.append("")
        lines.append("Skipped Tickets (Resolution Time):")
        preferred_reasons = [
            "Unresolved / Missing resolution date",
            "Unresolved / Non-resolved status",
            "Resolved before created",
            "Invalid resolution date",
        ]
        all_reasons = preferred_reasons + [
            r
            for r in sorted(metrics.skipped_tickets.keys())
            if r not in preferred_reasons
        ]
        for reason in all_reasons:
            ticket_ids = metrics.skipped_tickets.get(reason, [])
            if ticket_ids:
                ticket_ids_str = ", ".join(ticket_ids)
                lines.append(f"  {reason}: {ticket_ids_str}")

    return "\n".join(lines)


def format_summary_json(metrics: TicketMetrics) -> str:
    """Format ticket metrics into machine-readable JSON."""
    categories_detail = {}
    for category in sorted(metrics.category_counts.keys()):
        categories_detail[category] = {
            "count": metrics.category_counts[category],
            "average_resolution_time": format_duration(
                metrics.category_average_seconds.get(category)
            ),
        }

    payload = {
        "category_counts": dict(sorted(metrics.category_counts.items())),
        "overall_average_resolution_time": format_duration(
            metrics.overall_average_seconds
        ),
        "categories": categories_detail,
        "skipped_tickets": dict(metrics.skipped_tickets),
    }
    return json.dumps(payload, indent=2)


def process_tickets(file_path: Path, output_json: bool = False) -> int:
    """Core processor for ticket CSV file."""
    rows, fatal_errors, row_warnings = read_and_validate_csv(file_path)
    if fatal_errors:
        for err in fatal_errors:
            print(err, file=sys.stderr)
        return 1

    for warn in row_warnings:
        print(warn, file=sys.stderr)

    metrics, resolution_warnings = compute_metrics(rows)
    for warn in resolution_warnings:
        print(warn, file=sys.stderr)

    if output_json:
        print(format_summary_json(metrics))
    else:
        print(format_summary_text(metrics))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Summarize support ticket CSV reports."
    )
    parser.add_argument(
        "file",
        type=Path,
        help="Path to the ticket CSV file.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output summary as structured JSON.",
    )
    args = parser.parse_args(argv)
    return process_tickets(args.file, output_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
