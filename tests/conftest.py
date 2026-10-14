import os

import pytest

os.environ.setdefault("TICKETS_DATA_PATH", "data/tickets_sample.csv")


@pytest.fixture(autouse=True)
def isolate_ops_tracking_csv(tmp_path, monkeypatch):
    """Ensure all test runs use an isolated temporary tracking CSV."""
    temp_csv = str(tmp_path / "isolated_ops_tracking.csv")
    monkeypatch.setenv("OPS_TRACKING_CSV_PATH", temp_csv)
    return temp_csv
