# Root Cause Analysis: Inherited `ticket-api` Defects

## 1. Initial Run Step-by-Step Execution Notes (Task 2.1)

Following the legacy `README.md` instructions step-by-step produced the following chronological observations:

1. **Step 1 — Dependency Installation**:
   - Command: `pip install -r requirements.txt`
   - Result: Packages installed cleanly.
2. **Step 2 — Launch Development Server**:
   - Command: `uvicorn main:app --reload`
   - Result: Immediate process failure with `ModuleNotFoundError: No module named 'main'` because `main.py` is inside the `app/` package directory.
3. **Step 3 — Launch with Module Path**:
   - Command: `uvicorn app.main:app`
   - Result: Immediate process crash with `KeyError: 'TICKETS_DATA_PATH'` because startup code accessed `os.environ["TICKETS_DATA_PATH"]` without a fallback default.
4. **Step 4 — Provide Environment Variable and Open Web UI**:
   - Command: `$env:TICKETS_DATA_PATH="data/tickets_sample.csv"; uvicorn app.main:app`
   - Result: Server booted. Visiting `http://localhost:8000` revealed date display defect: March dates rendered as `2024-02-...` due to zero-indexed `d.getMonth()`.
5. **Step 5 — Inspect Ticket Pagination**:
   - Command: `curl http://localhost:8000/tickets?page=1&size=10`
   - Result: The first returned ticket was `TCK-1002` instead of `TCK-1001` due to off-by-one formula `start = (page - 1) * size + 1`.
6. **Step 6 — Inspect Summary Metrics**:
   - Command: `curl http://localhost:8000/summary`
   - Result: Endpoint returned `average_resolution_hours: 17.69`, contradicting Day 1 metric (25.27 hours) by dividing by all 60 tickets instead of 42 resolved tickets.

---

## 2. Detailed Root Cause Analysis by Defect

## 1. Missing Fallback for `TICKETS_DATA_PATH`

- **What was broken**:
  At startup, `app/main.py` directly accessed `os.environ["TICKETS_DATA_PATH"]`. If the variable was unset in the running environment, Python raised an unhandled `KeyError` and halted the process immediately.
- **How it was found**:
  Following the README instructions (`uvicorn main:app --reload`) in a fresh environment failed immediately upon module load with `KeyError: 'TICKETS_DATA_PATH'`.
- **How it was fixed**:
  Added safe fallback resolution using `os.environ.get("TICKETS_DATA_PATH")` pointing to the bundled default dataset at `data/tickets_sample.csv`.

---

## 2. Incorrect Entrypoint in README

- **What was broken**:
  The README documented running `uvicorn main:app --reload`. Because `main.py` is located inside the `app/` package directory, running this command from the repository root raised `ModuleNotFoundError: No module named 'main'`.
- **How it was found**:
  Running the command from the repository root as directed by the original documentation.
- **How it was fixed**:
  Updated the README documentation to `uvicorn app.main:app --reload`.

---

## 3. Off-by-One Pagination Offset in `GET /tickets`

- **What was broken**:
  The pagination offset calculation was written as `start = (page - 1) * size + 1`. For `page=1` and `size=10`, `start` evaluated to `1` instead of `0`. This skipped the first record in the dataset (`TCK-1001`) and shifted all subsequent pages.
- **How it was found**:
  Authored an automated test in `tests/test_api.py` checking whether the first returned ticket on page 1 was `TCK-1001`. The test failed, receiving `TCK-1002`.
- **How it was fixed**:
  Corrected the formula to `start = (page - 1) * size`, aligning zero-based slice indexing with 1-based page queries.

---

## 4. Zero-Indexed Calendar Months in Frontend

- **What was broken**:
  In `web/index.html`, the date formatting function used `d.getMonth()`. In JavaScript, `getMonth()` returns 0–11. Tickets created in March (`03`) were formatted and displayed as month `2`.
- **How it was found**:
  Code review of the client-side date formatting script in `web/index.html`.
- **How it was fixed**:
  Updated the formatting logic to `d.getMonth() + 1`.

---

## 5. Skewed Resolution Average Calculation in `/summary`

- **What was broken**:
  The summary endpoint accumulated resolution durations across resolved tickets, but divided the sum by `len(TICKETS)` (total ticket count = 60). Because 18 tickets in `tickets_sample.csv` are still open (unresolved), dividing by 60 treated open tickets as if they were resolved in 0 hours, artificially deflating the reported average resolution from 25.27 hours down to 17.69 hours.
- **How it was found**:
  Compared endpoint output against Day 1 metrics computed from `tickets_sample.csv` and verified with an automated test in `tests/test_api.py`.
- **How it was fixed & Day 1 Decision**:
  Integrated the Day 1 `TicketMetrics` calculation engine in `ticket_summary.py` directly into `app/main.py`. The calculation computes resolution duration strictly across tickets with valid resolved timestamps and statuses matching `resolved` or `closed`.
  - **Decision on Disagreement**: We decided that only resolved tickets must be included in resolution time metrics. Unresolved tickets are tracked separately under `skipped_tickets` so operational reporting remains mathematically sound without breaking backward compatibility for `total`, `by_category`, and `average_resolution_hours`.
