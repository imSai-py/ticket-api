"""Background scheduler service for daily 9:00 AM and 3:00 PM batch approval digest."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from app.batch_digest import generate_batch_digest

logger = logging.getLogger(__name__)

_LAST_RUN_DATE: str | None = None


def get_digest_time_window(now: datetime) -> tuple[datetime, datetime, str]:
    """Calculate the start time, end time, and slot label for the digest batch.

    - 9:00 AM slot: from yesterday 3:00 PM (15:00:00) to today 9:00 AM (09:00:00).
    - 3:00 PM slot: from today 9:00 AM (09:00:00) to today 3:00 PM (15:00:00).
    - For ad-hoc execution: calculates active window up to current execution time.
    """
    if now.hour == 9 and now.minute == 0 and now.second == 0:
        slot_label = "9:00 AM"
        end_time = datetime(now.year, now.month, now.day, 9, 0, 0)
        yesterday = now - timedelta(days=1)
        start_time = datetime(yesterday.year, yesterday.month, yesterday.day, 15, 0, 0)
        return start_time, end_time, slot_label

    if now.hour == 15 and now.minute == 0 and now.second == 0:
        slot_label = "3:00 PM"
        end_time = datetime(now.year, now.month, now.day, 15, 0, 0)
        start_time = datetime(now.year, now.month, now.day, 9, 0, 0)
        return start_time, end_time, slot_label

    # Ad-hoc / running window computation
    if now.hour < 9:
        slot_label = "9:00 AM"
        yesterday = now - timedelta(days=1)
        start_time = datetime(yesterday.year, yesterday.month, yesterday.day, 15, 0, 0)
        end_time = now
    elif now.hour < 15:
        slot_label = "3:00 PM"
        start_time = datetime(now.year, now.month, now.day, 9, 0, 0)
        end_time = now
    else:
        slot_label = "9:00 AM"
        start_time = datetime(now.year, now.month, now.day, 15, 0, 0)
        end_time = now

    return start_time, end_time, slot_label


def should_trigger_digest(now: datetime, last_run_date: str | None) -> bool:
    """Check if current time is within 9:00 AM or 3:00 PM windows and has not run for this slot."""
    if now.minute != 0 or now.hour not in (9, 15):
        return False

    today_str = now.strftime("%Y-%m-%d")
    slot_str = f"{today_str}_{now.hour:02d}"

    if last_run_date:
        if last_run_date == slot_str:
            return False
        # Backward compatibility with legacy whole-day string (e.g. "2026-10-15") for 9 AM
        if last_run_date == today_str and now.hour == 9:
            return False

    return True


def run_scheduler_tick(
    now: datetime | None = None, reset_date: bool = False
) -> dict[str, Any] | None:
    """Execute a single check of the scheduler, triggering the digest if due."""
    global _LAST_RUN_DATE
    if reset_date:
        _LAST_RUN_DATE = None

    current_time = now or datetime.now()
    if should_trigger_digest(current_time, _LAST_RUN_DATE):
        today_str = current_time.strftime("%Y-%m-%d")
        slot_str = f"{today_str}_{current_time.hour:02d}"
        _LAST_RUN_DATE = slot_str
        start_time, end_time, slot_label = get_digest_time_window(current_time)
        digest = generate_batch_digest(
            start_time=start_time,
            end_time=end_time,
            slot_label=slot_label,
        )
        if not digest.get("has_pending"):
            logger.debug(
                "Suppressing scheduled %s digest: zero pending tickets.",
                slot_label,
            )
            return digest
        logger.info("Executing scheduled %s batch approval digest...", slot_label)
        return digest
    return None


async def start_daily_digest_scheduler(
    poll_interval_seconds: int = 30,
) -> None:
    """Async background task that runs while the server is active."""
    logger.info(
        "Starting daily 9:00 AM and 3:00 PM approval digest background scheduler."
    )
    while True:
        try:
            run_scheduler_tick()
        except (OSError, RuntimeError, ValueError) as e:
            logger.error("Error during scheduled digest execution: %s", e)
        await asyncio.sleep(poll_interval_seconds)


def check_scheduler_health() -> bool:
    """Verify digest scheduler configuration and trigger viability."""
    try:
        sample_time = datetime(2026, 1, 1, 9, 0)
        return should_trigger_digest(sample_time, None) is True
    except (OSError, ValueError, RuntimeError, TypeError) as e:
        logger.warning("Scheduler health diagnostic failed: %s", e)
        return False
