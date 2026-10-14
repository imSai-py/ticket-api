from datetime import datetime
from unittest.mock import patch

from app.scheduler import run_scheduler_tick, should_trigger_digest


def test_should_trigger_digest_at_9am():
    at_9am = datetime(2026, 10, 15, 9, 0, 0)
    assert should_trigger_digest(at_9am, last_run_date=None) is True
    assert should_trigger_digest(at_9am, last_run_date="2026-10-15") is False


def test_should_not_trigger_digest_at_other_times():
    at_8am = datetime(2026, 10, 15, 8, 30, 0)
    at_10am = datetime(2026, 10, 15, 10, 0, 0)
    assert should_trigger_digest(at_8am, last_run_date=None) is False
    assert should_trigger_digest(at_10am, last_run_date=None) is False


def test_run_scheduler_tick_dispatches():
    at_9am = datetime(2026, 10, 15, 9, 0, 0)
    with patch("app.scheduler.send_batch_digest") as mock_send:
        mock_send.return_value = {"has_pending": True, "dispatched": True}
        result = run_scheduler_tick(now=at_9am, reset_date=True)
        assert result is not None
        assert mock_send.called
