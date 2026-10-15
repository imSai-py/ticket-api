# ticket-api

A support ticket analytics service, AI-powered triage platform, and billing operations sync system.

Requires Python 3.8+ (tested on Python 3.11) and Node.js 18+.

---

## 1. Quick Start: Clean-Machine Setup

Follow these exact steps to run the application from scratch on a clean machine.

### Prerequisites

- **Python**: 3.8 or higher (`python --version`)
- **Node.js**: 18 or higher (`node --version`)
- **Git**: Installed and configured (`git --version`)

### Step 1: Clone Repository & Navigate to Execution Root

All git commands, application servers, build scripts, and test suites run inside `ticket-api/`:

```bash
git clone https://github.com/imSai-py/bitcot-technical-assignment.git
cd bitcot-technical-assignment/ticket-api
```

### Step 2: Set Up Python Virtual Environment

Create and activate an isolated virtual environment:

- **Windows (PowerShell)**:
  ```powershell
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  ```

- **Linux / macOS (Bash)**:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

### Step 3: Install Backend Dependencies

Install the locked Python dependencies:

```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables

Copy the example environment template. All default settings work out of the box with offline mock fallbacks:

- **Windows**:
  ```powershell
  Copy-Item .env.example .env
  ```

- **Linux / macOS**:
  ```bash
  cp .env.example .env
  ```

*(Optional: Set `GEMINI_API_KEY` in `.env` if testing live AI inference with Google Gemini).*

### Step 5: Start Backend Application Server

Launch the FastAPI development server on port 8000:

- **Using PowerShell script (auto-kills stale listeners on port 8000)**:
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts/start-server.ps1
  ```

- **Or using standard Uvicorn**:
  ```bash
  uvicorn app.main:app --reload --port 8000
  ```

Verify in your browser or terminal:
- **System Health Check**: http://localhost:8000/health
- **Interactive Swagger Docs**: http://localhost:8000/docs
- **Web Analytics Overview**: http://localhost:8000/

### Step 6: Set Up and Run Frontend UI

Open a second terminal window in `ticket-api/`:

```bash
cd frontend
npm install
npm run dev
```

The frontend launches at http://localhost:5173/ with live triage testing and billing sync.

---

## 2. System Health & Diagnostic Probes

The service exposes an automated health probe designed for container health checks, load balancers, and monitoring agents:

- **Endpoint**: `GET /health`
- **Success Response (HTTP 200 OK)**:
  ```json
  {
    "status": "healthy",
    "version": "1.0.0",
    "storage": "accessible",
    "tickets_data": "loaded",
    "knowledge_base": "indexed"
  }
  ```
- **Degraded Response (HTTP 503 Service Unavailable)**:
  Returned when the underlying tracking spreadsheet or directory is inaccessible or write-locked.

---

## 3. Core Operational Workflows

### Billing Operations Sync

- **Sync Ticket to Spreadsheet**:
  `POST /ops/sync-ticket`
  ```json
  {
    "customer_name": "Alex Morgan",
    "category": "Billing",
    "priority": "urgent",
    "amount": 129.50,
    "reason": "Duplicate charge on annual plan"
  }
  ```
  Appends or updates records in `data/ops_tracking_sheet.csv`. Automatically triggers an escalation alert email to `manager@example.com` if `priority == "urgent"`.

- **Query Pending Approvals**:
  `GET /ops/approvals/pending`
  Returns all billing rows awaiting manager action.

- **Batch Approval Digest**:
  `POST /ops/approvals/send-digest`
  Consolidates pending requests into a single digest email with one-click action links. A background scheduler automatically triggers this daily at 9:00 AM local time.

- **One-Click Approval / Rejection Action**:
  `GET /ops/approvals/{ticket_id}/action?status=Approved` (or `Rejected`)
  Updates the ticket status in the tracking spreadsheet and serves a lightweight confirmation receipt.

---

## 4. Production Basics & Resilience

- **Input Validation**:
  - `SyncTicketRequest` enforces non-negative monetary amounts (`amount >= 0.0`), disallows blank customer names, and validates urgency priority against allowed enumerations.
  - One-click actions strictly require non-empty ticket identifiers and status values of `Approved` or `Rejected`.
  - Violations immediately return `HTTP 422 Unprocessable Entity` or `HTTP 400 Bad Request` with descriptive error details rather than triggering server crashes.
- **Flat-File Concurrency & Excel File Lock Handling**:
  - Windows file locks from Microsoft Excel are detected gracefully via `SpreadsheetLockedError`, returning `HTTP 423 Locked` with actionable user guidance instead of crashing.
  - Cell values are sanitized using `sanitize_cell()` to strip raw newlines (`\r`, `\n`) and tab characters, ensuring CSV record integrity.
- **AI Triage Guardrails**:
  - Gemini model calls feature timeout controls (`GEMINI_TIMEOUT_MS=10000`) and capped fallback candidate loops to eliminate latency spikes.
  - Offline fallback returns safe recommendations (`category: "Technical"`, `priority: "normal"`) if credentials or network are unavailable.

---

## 5. Testing & Verification

Run the unified gate across Python and TypeScript test suites:

- **Windows**:
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts/verify-all.ps1
  ```

- **Linux / macOS**:
  ```bash
  bash scripts/verify-all.sh
  ```

### Targeted Test Commands

- **Backend tests only (83 tests)**:
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts/verify-all.ps1 -BackendOnly
  # Or: pytest
  ```

- **Frontend tests only (Vitest + TypeScript type check)**:
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts/verify-all.ps1 -FrontendOnly
  # Or: cd frontend && npm test
  ```

- **Linting and formatting**:
  ```bash
  ruff check .
  black --check .
  ```

---

## 6. Cloud Deployment (Render.com)

1. Push your repository to GitHub.
2. In the Render Dashboard, create a **New Web Service** connected to your repository.
3. Choose **Docker** as the runtime (Render detects [Dockerfile](https://github.com/imSai-py/bitcot-technical-assignment/blob/master/Dockerfile) and [render.yaml](https://github.com/imSai-py/bitcot-technical-assignment/blob/master/render.yaml)).
4. Under **Environment Variables**, set:
   - `GEMINI_API_KEY`: Your Google Gemini API key.
   - `TICKETS_DATA_PATH`: `data/tickets_sample.csv`
   - `ESCALATION_EMAIL`: `manager@example.com`
5. Click **Deploy Web Service**.
6. Set `VITE_API_BASE_URL` in your frontend environment to point to the live Render deployment.
