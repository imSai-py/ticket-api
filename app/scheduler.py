"""Background scheduler service for daily 9:00 AM batch approval digest."""

import asyncio
import logging
from datetime import datetime
from typing import Any

from app.batch_digest import generate_batch_digest

logger = logging.getLogger(__name__)

_LAST_RUN_DATE: str | None = None


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
        digest = generate_batch_digest()
        slot_label = current_time.strftime("%I:%M %p")
        if not digest.get("has_pending"):
            logger.debug(
                "Suppressing scheduled %s digest: zero pending billing approvals.",
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
    logger.info("Starting daily 9:00 AM approval digest background scheduler.")
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
