# Billing Sync and Operations Approval Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate billing ticket synchronization from the help desk into the tracking spreadsheet, generate consolidated batch approval email digests to eliminate manager inbox clutter, and dispatch instant escalation alerts for urgent tickets.

**Architecture:** A lightweight CSV tracking store acts as the operational tracking spreadsheet (`data/ops_tracking_sheet.csv`). The core engine exposes modules for spreadsheet synchronization, single-inbox escalation alerts, and consolidated batch email digest generation. FastAPI endpoints expose these services and hook directly into `POST /triage` when a ticket is classified as Billing.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, pytest.

**Spec:** `day-3/scoping-note-draft.md` and `day-3/Task-and-clarification.md`

## Global Constraints

- Must use standard library and existing dependencies in `ticket-api/requirements.txt` (FastAPI, Pydantic, pytest).
- No new external manager web portal; approvals and reviews must interface via the spreadsheet and email digest.
- Secrets and manager email destinations must be read from environment variables (`ESCALATION_MANAGER_EMAIL`, `DIGEST_MANAGER_EMAIL`).
- Edge cases (empty spreadsheet, corrupted rows, empty queue, non-urgent tickets) must be handled gracefully with 100% test coverage.
- Code style: ASD-STE 100 compliant, type annotations, complete docstrings.

---

### Task 1: Tracking Spreadsheet Synchronization Module

**Files:**
- Create: `ticket-api/app/tracking_sync.py`
- Test: `ticket-api/tests/test_tracking_sync.py`
- Data: `ticket-api/data/ops_tracking_sheet.csv`

**Interfaces:**
- Produces:
  - `sync_ticket_to_spreadsheet(ticket: dict, csv_path: str = "data/ops_tracking_sheet.csv") -> dict`
  - `get_pending_approvals(csv_path: str = "data/ops_tracking_sheet.csv") -> list[dict]`
  - `update_approval_status(ticket_id: str, new_status: str, notes: str = "", csv_path: str = "data/ops_tracking_sheet.csv") -> dict`

- [ ] **Step 1: Write the failing tests for tracking spreadsheet operations**

Create `ticket-api/tests/test_tracking_sync.py`:
```python
import csv
import pytest
from app.tracking_sync import (
    sync_ticket_to_spreadsheet,
    get_pending_approvals,
    update_approval_status,
)


@pytest.fixture
def temp_tracking_csv(tmp_path):
    csv_file = tmp_path / "test_ops_tracking.csv"
    return str(csv_file)


def test_sync_ticket_creates_row(temp_tracking_csv):
    ticket = {
        "ticket_id": "TCK-2001",
        "customer_name": "Jane Doe",
        "category": "Billing",
        "priority": "normal",
        "amount": 49.99,
        "reason": "Charged twice",
        "agent": "Alex",
    }
    result = sync_ticket_to_spreadsheet(ticket, csv_path=temp_tracking_csv)
    assert result["ticket_id"] == "TCK-2001"
    assert result["status"] == "Pending"

    pending = get_pending_approvals(csv_path=temp_tracking_csv)
    assert len(pending) == 1
    assert pending[0]["ticket_id"] == "TCK-2001"
    assert float(pending[0]["amount"]) == 49.99


def test_update_approval_status(temp_tracking_csv):
    ticket = {
        "ticket_id": "TCK-2002",
        "customer_name": "John Smith",
        "category": "Billing",
        "priority": "urgent",
        "amount": 120.00,
        "reason": "Refund requested",
        "agent": "Sam",
    }
    sync_ticket_to_spreadsheet(ticket, csv_path=temp_tracking_csv)

    updated = update_approval_status(
        "TCK-2002", "Approved", notes="Approved by manager", csv_path=temp_tracking_csv
    )
    assert updated["status"] == "Approved"

    pending = get_pending_approvals(csv_path=temp_tracking_csv)
    assert len(pending) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tracking_sync.py -v` (inside `ticket-api`)
Expected: FAIL with `ModuleNotFoundError: No module named 'app.tracking_sync'`

- [ ] **Step 3: Implement minimal tracking sync module**

Create `ticket-api/app/tracking_sync.py`:
```python
import csv
import os
from datetime import datetime
from typing import Any, Dict, List

FIELDNAMES = [
    "ticket_id",
    "customer_name",
    "category",
    "priority",
    "amount",
    "reason",
    "agent",
    "status",
    "escalated",
    "created_at",
    "updated_at",
    "notes",
]


def _ensure_file_exists(csv_path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)
    if not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0:
        with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()


def _read_all(csv_path: str) -> List[Dict[str, Any]]:
    _ensure_file_exists(csv_path)
    with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _write_all(csv_path: str, rows: List[Dict[str, Any]]) -> None:
    _ensure_file_exists(csv_path)
    with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def sync_ticket_to_spreadsheet(
    ticket: Dict[str, Any], csv_path: str = "data/ops_tracking_sheet.csv"
) -> Dict[str, Any]:
    """Sync a ticket into the tracking spreadsheet."""
    rows = _read_all(csv_path)
    now = datetime.utcnow().isoformat()
    ticket_id = str(ticket.get("ticket_id", ""))

    existing_idx = next(
        (i for i, r in enumerate(rows) if r["ticket_id"] == ticket_id), None
    )

    new_row = {
        "ticket_id": ticket_id,
        "customer_name": str(ticket.get("customer_name", "Unknown")),
        "category": str(ticket.get("category", "Billing")),
        "priority": str(ticket.get("priority", "normal")),
        "amount": str(ticket.get("amount", "0.00")),
        "reason": str(ticket.get("reason", "")),
        "agent": str(ticket.get("agent", "System")),
        "status": str(ticket.get("status", "Pending")),
        "escalated": "True"
        if ticket.get("priority") == "urgent" or ticket.get("escalated") is True
        else "False",
        "created_at": now,
        "updated_at": now,
        "notes": str(ticket.get("notes", "")),
    }

    if existing_idx is not None:
        new_row["created_at"] = rows[existing_idx]["created_at"]
        rows[existing_idx] = new_row
    else:
        rows.append(new_row)

    _write_all(csv_path, rows)
    return new_row


def get_pending_approvals(
    csv_path: str = "data/ops_tracking_sheet.csv",
) -> List[Dict[str, Any]]:
    """Retrieve all tickets in Pending status."""
    rows = _read_all(csv_path)
    return [r for r in rows if r["status"] == "Pending"]


def update_approval_status(
    ticket_id: str,
    new_status: str,
    notes: str = "",
    csv_path: str = "data/ops_tracking_sheet.csv",
) -> Dict[str, Any]:
    """Update approval status (e.g. Approved, Rejected)."""
    rows = _read_all(csv_path)
    target = next((r for r in rows if r["ticket_id"] == ticket_id), None)
    if not target:
        raise ValueError(f"Ticket with ID {ticket_id} not found in tracking sheet.")

    target["status"] = new_status
    target["updated_at"] = datetime.utcnow().isoformat()
    if notes:
        target["notes"] = notes

    _write_all(csv_path, rows)
    return target
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_tracking_sync.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/tracking_sync.py tests/test_tracking_sync.py
git commit -m "feat: implement tracking spreadsheet synchronization module"
```

---

### Task 2: Instant Escalation Alert Service

**Files:**
- Create: `ticket-api/app/escalation.py`
- Test: `ticket-api/tests/test_escalation.py`

**Interfaces:**
- Consumes: `ticket: dict`
- Produces: `send_escalation_alert(ticket: dict, recipient_override: str | None = None) -> dict`

- [ ] **Step 1: Write the failing tests for escalation service**

Create `ticket-api/tests/test_escalation.py`:
```python
import os
import pytest
from app.escalation import send_escalation_alert


def test_escalation_alert_urgent_ticket(monkeypatch):
    monkeypatch.setenv("ESCALATION_MANAGER_EMAIL", "ops-manager@company.com")
    ticket = {
        "ticket_id": "TCK-9999",
        "customer_name": "VIP Client",
        "category": "Billing",
        "priority": "urgent",
        "amount": 5000.0,
        "reason": "Account locked due to billing error",
    }
    alert = send_escalation_alert(ticket)
    assert alert["dispatched"] is True
    assert alert["recipient"] == "ops-manager@company.com"
    assert "URGENT" in alert["subject"]
    assert "VIP Client" in alert["body"]


def test_escalation_alert_non_urgent_skipped():
    ticket = {
        "ticket_id": "TCK-1001",
        "customer_name": "Normal User",
        "category": "Billing",
        "priority": "normal",
        "amount": 10.0,
        "reason": "Receipt inquiry",
    }
    alert = send_escalation_alert(ticket)
    assert alert["dispatched"] is False
    assert alert["reason"] == "Not an urgent ticket"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_escalation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.escalation'`

- [ ] **Step 3: Implement minimal escalation service**

Create `ticket-api/app/escalation.py`:
```python
import os
from typing import Any, Dict


def send_escalation_alert(
    ticket: Dict[str, Any], recipient_override: str | None = None
) -> Dict[str, Any]:
    """Dispatch an instant alert for urgent escalated tickets to a single manager inbox."""
    is_urgent = (
        ticket.get("priority") == "urgent" or ticket.get("escalated") is True
    )
    if not is_urgent:
        return {"dispatched": False, "reason": "Not an urgent ticket"}

    recipient = recipient_override or os.getenv(
        "ESCALATION_MANAGER_EMAIL", "manager@company.com"
    )
    ticket_id = ticket.get("ticket_id", "Unknown")
    customer = ticket.get("customer_name", "Unknown")
    reason = ticket.get("reason", "No reason provided")
    amount = ticket.get("amount", "0.00")

    subject = f"[URGENT ESCALATION] Ticket {ticket_id} - {customer}"
    body = (
        f"URGENT TICKET ESCALATED\n"
        f"----------------------\n"
        f"Ticket ID: {ticket_id}\n"
        f"Customer:  {customer}\n"
        f"Category:  {ticket.get('category', 'Billing')}\n"
        f"Amount:    ${amount}\n"
        f"Reason:    {reason}\n"
        f"Action:    Requires immediate management review.\n"
    )

    # In production, dispatch via SMTP or SendGrid. Here we record payload.
    return {
        "dispatched": True,
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "ticket_id": ticket_id,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_escalation.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/escalation.py tests/test_escalation.py
git commit -m "feat: implement single-inbox instant escalation alert service"
```

---

### Task 3: Consolidated Batch Approval Email Digest Module

**Files:**
- Create: `ticket-api/app/batch_digest.py`
- Test: `ticket-api/tests/test_batch_digest.py`

**Interfaces:**
- Consumes: `get_pending_approvals()` from `app.tracking_sync`
- Produces: `generate_batch_digest(csv_path: str = "data/ops_tracking_sheet.csv", recipient: str | None = None) -> dict`

- [ ] **Step 1: Write failing tests for batch digest generation**

Create `ticket-api/tests/test_batch_digest.py`:
```python
import pytest
from app.batch_digest import generate_batch_digest
from app.tracking_sync import sync_ticket_to_spreadsheet


@pytest.fixture
def temp_csv(tmp_path):
    return str(tmp_path / "tracking_digest.csv")


def test_generate_batch_digest_with_tickets(temp_csv):
    sync_ticket_to_spreadsheet(
        {
            "ticket_id": "TCK-3001",
            "customer_name": "Alice",
            "amount": 25.0,
            "reason": "Promo refund",
            "agent": "Sam",
        },
        csv_path=temp_csv,
    )
    sync_ticket_to_spreadsheet(
        {
            "ticket_id": "TCK-3002",
            "customer_name": "Bob",
            "amount": 75.0,
            "reason": "Double billing",
            "agent": "Sam",
        },
        csv_path=temp_csv,
    )

    digest = generate_batch_digest(
        csv_path=temp_csv, recipient="billing-manager@company.com"
    )
    assert digest["has_pending"] is True
    assert digest["pending_count"] == 2
    assert "TCK-3001" in digest["body_table"]
    assert "TCK-3002" in digest["body_table"]
    assert digest["recipient"] == "billing-manager@company.com"
    assert "csv_payload" in digest


def test_generate_batch_digest_empty(temp_csv):
    digest = generate_batch_digest(csv_path=temp_csv)
    assert digest["has_pending"] is False
    assert digest["pending_count"] == 0
    assert "No pending billing approvals" in digest["body_table"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_batch_digest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.batch_digest'`

- [ ] **Step 3: Implement batch digest module**

Create `ticket-api/app/batch_digest.py`:
```python
import io
import os
from datetime import datetime
from typing import Any, Dict
from app.tracking_sync import get_pending_approvals


def generate_batch_digest(
    csv_path: str = "data/ops_tracking_sheet.csv", recipient: str | None = None
) -> Dict[str, Any]:
    """Generate a single consolidated email digest for all pending billing approvals."""
    target_recipient = recipient or os.getenv(
        "DIGEST_MANAGER_EMAIL", "billing-manager@company.com"
    )
    pending_tickets = get_pending_approvals(csv_path=csv_path)
    count = len(pending_tickets)
    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    subject = f"[Daily Digest] Billing Approvals: {count} Pending ({today_str})"

    if count == 0:
        return {
            "has_pending": False,
            "pending_count": 0,
            "recipient": target_recipient,
            "subject": subject,
            "body_table": "No pending billing approvals today.",
            "csv_payload": "",
        }

    header_line = f"{'Ticket ID':<10} | {'Customer':<18} | {'Amount':<9} | {'Agent':<10} | {'Reason'}"
    sep_line = "-" * 75
    data_lines = [
        f"{t['ticket_id']:<10} | {t['customer_name']:<18} | ${float(t.get('amount') or 0):<8.2f} | {t.get('agent', 'System'):<10} | {t.get('reason', '')}"
        for t in pending_tickets
    ]
    body_table = "\n".join([header_line, sep_line] + data_lines)

    # Prepare attached CSV string
    csv_buffer = io.StringIO()
    import csv

    if pending_tickets:
        writer = csv.DictWriter(csv_buffer, fieldnames=list(pending_tickets[0].keys()))
        writer.writeheader()
        writer.writerows(pending_tickets)

    return {
        "has_pending": True,
        "pending_count": count,
        "recipient": target_recipient,
        "subject": subject,
        "body_table": body_table,
        "csv_payload": csv_buffer.getvalue(),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_batch_digest.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/batch_digest.py tests/test_batch_digest.py
git commit -m "feat: implement consolidated batch approval email digest module"
```

---

### Task 4: API Endpoints & Automatic Triage Integration

**Files:**
- Modify: `ticket-api/app/main.py`
- Test: `ticket-api/tests/test_ops_endpoints.py`

**Interfaces:**
- Exposes:
  - `POST /ops/sync-ticket`
  - `GET /ops/approvals/pending`
  - `POST /ops/approvals/{ticket_id}`
  - `POST /ops/approvals/send-digest`
  - Integrated into `POST /triage` (auto-sync billing and escalate urgent)

- [ ] **Step 1: Write failing tests for ops endpoints and triage hook**

Create `ticket-api/tests/test_ops_endpoints.py`:
```python
from fastapi.testclient import TestClient
from app.main import app
import pytest

client = TestClient(app)


def test_ops_sync_and_get_pending():
    response = client.post(
        "/ops/sync-ticket",
        json={
            "ticket_id": "TCK-5001",
            "customer_name": "Carol Danvers",
            "category": "Billing",
            "priority": "normal",
            "amount": 80.0,
            "reason": "Duplicate subscription charge",
            "agent": "Dan",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ticket"]["ticket_id"] == "TCK-5001"

    pending_res = client.get("/ops/approvals/pending")
    assert pending_res.status_code == 200
    items = pending_res.json()["pending_approvals"]
    assert any(i["ticket_id"] == "TCK-5001" for i in items)


def test_ops_approve_ticket():
    client.post(
        "/ops/sync-ticket",
        json={
            "ticket_id": "TCK-5002",
            "customer_name": "Tony Stark",
            "category": "Billing",
            "priority": "urgent",
            "amount": 250.0,
            "reason": "Expedited refund",
            "agent": "Pepper",
        },
    )

    update_res = client.post(
        "/ops/approvals/TCK-5002",
        json={"status": "Approved", "notes": "Authorized per policy"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["status"] == "Approved"


def test_ops_send_digest():
    res = client.post("/ops/approvals/send-digest")
    assert res.status_code == 200
    data = res.json()
    assert "subject" in data
    assert "body_table" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ops_endpoints.py -v`
Expected: FAIL with HTTP 404 Not Found

- [ ] **Step 3: Integrate ops endpoints in `app/main.py`**

Add endpoints to `app/main.py`:
```python
from pydantic import BaseModel
from typing import Optional
from app.tracking_sync import (
    sync_ticket_to_spreadsheet,
    get_pending_approvals,
    update_approval_status,
)
from app.escalation import send_escalation_alert
from app.batch_digest import generate_batch_digest


class SyncTicketRequest(BaseModel):
    ticket_id: str
    customer_name: str
    category: str = "Billing"
    priority: str = "normal"
    amount: float = 0.0
    reason: str = ""
    agent: str = "System"


class UpdateApprovalRequest(BaseModel):
    status: str
    notes: Optional[str] = ""


@app.post("/ops/sync-ticket")
def ops_sync_ticket(req: SyncTicketRequest):
    row = sync_ticket_to_spreadsheet(req.model_dump())
    alert = send_escalation_alert(req.model_dump())
    return {"ticket": row, "escalation_alert": alert}


@app.get("/ops/approvals/pending")
def ops_get_pending():
    pending = get_pending_approvals()
    return {"pending_count": len(pending), "pending_approvals": pending}


@app.post("/ops/approvals/{ticket_id}")
def ops_update_approval(ticket_id: str, req: UpdateApprovalRequest):
    updated = update_approval_status(
        ticket_id, new_status=req.status, notes=req.notes or ""
    )
    return updated


@app.post("/ops/approvals/send-digest")
def ops_send_digest():
    digest = generate_batch_digest()
    return digest
```

And in `/triage` route of `app/main.py`, hook:
```python
    # Auto-sync to ops tracking sheet if Billing
    if triage_result.category == "Billing":
        sync_ticket_to_spreadsheet(
            {
                "ticket_id": f"TCK-AUTO-{abs(hash(req.text)) % 10000}",
                "customer_name": "Incoming Ticket",
                "category": triage_result.category,
                "priority": triage_result.priority,
                "amount": 0.0,
                "reason": req.text[:100],
                "agent": "AI Triage",
            }
        )
        if triage_result.priority == "urgent":
            send_escalation_alert(
                {
                    "ticket_id": f"TCK-AUTO-{abs(hash(req.text)) % 10000}",
                    "customer_name": "Incoming Ticket",
                    "category": triage_result.category,
                    "priority": triage_result.priority,
                    "reason": req.text[:100],
                }
            )
```

- [ ] **Step 4: Run all tests to verify they pass**

Run: `pytest tests/test_ops_endpoints.py tests/test_triage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_ops_endpoints.py
git commit -m "feat: add ops approval endpoints and auto-sync triage hook"
```

---

### Task 5: End-to-End Verification and Documentation

**Files:**
- Modify: `ticket-api/README.md`
- Run: `scripts/verify-all.ps1` (or `pytest`)

- [ ] **Step 1: Update README.md with Operations Workflow documentation**
Document `/ops/sync-ticket`, `/ops/approvals/pending`, `/ops/approvals/{ticket_id}`, and `/ops/approvals/send-digest`.

- [ ] **Step 2: Run complete test suite and verification gate**
Run: `pytest -v` across entire repository.
Ensure all tests (33 existing + new ops tests) pass cleanly.

- [ ] **Step 3: Commit**
```bash
git add README.md
git commit -m "docs: document ops tracking, escalation, and batch digest workflows"
```
