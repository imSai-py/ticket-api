import asyncio
import csv
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.batch_digest import generate_batch_digest
from app.escalation import send_escalation_alert
from app.retrieval import KBRetriever
from app.scheduler import start_daily_digest_scheduler
from app.schemas import (
    ApprovalStatusEnum,
    SyncTicketRequest,
    TriageRequest,
    TriageResponse,
)
from app.tracking_sync import (
    SpreadsheetLockedError,
    check_storage_health,
    get_pending_approvals,
    sanitize_cell,
    sync_ticket_to_spreadsheet,
    update_approval_status,
)
from app.triage_ai import classify_and_reply
from ticket_summary import compute_metrics, parse_iso_timestamp

logger = logging.getLogger(__name__)

load_dotenv()

DEFAULT_DATA_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "tickets_sample.csv"
)
DATA_PATH_ENV = os.environ.get("TICKETS_DATA_PATH")
DATA_PATH = Path(DATA_PATH_ENV).resolve() if DATA_PATH_ENV else DEFAULT_DATA_PATH
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def format_display_date(ts_val: Any) -> str | None:
    """Format an ISO timestamp or datetime object as DD/MM/YYYY."""
    if not ts_val:
        return None
    dt = parse_iso_timestamp(ts_val)
    if dt is None:
        return str(ts_val)
    return dt.strftime("%d/%m/%Y")


def load_tickets(path: Path | str) -> list[dict[str, Any]]:
    tickets = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            row["created"] = parse_iso_timestamp(row.get("created_at"))
            row["resolved"] = parse_iso_timestamp(row.get("resolved_at"))

            for alias_a, alias_b in (
                ("labels", "tags"),
                ("customer_email", "requester_email"),
            ):
                if alias_a in row and alias_b not in row:
                    row[alias_b] = row[alias_a]
                elif alias_b in row and alias_a not in row:
                    row[alias_a] = row[alias_b]

            if "refund_amount" in row:
                raw_amt = (
                    str(row.get("refund_amount") or "")
                    .replace("$", "")
                    .replace(",", "")
                    .strip()
                )
                try:
                    row["refund_amount"] = float(raw_amt) if raw_amt else 0.0
                except ValueError:
                    row["refund_amount"] = 0.0

            if "resolved_at" not in row:
                row["resolved_at"] = None

            tickets.append(row)
    return tickets


TICKETS = load_tickets(DATA_PATH)

LOCAL_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
CORS_ORIGINS_ENV = os.environ.get("CORS_ORIGINS")
ALLOWED_ORIGINS = (
    [orig.strip() for orig in CORS_ORIGINS_ENV.split(",")]
    if CORS_ORIGINS_ENV
    else LOCAL_ORIGINS
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle tasks."""
    scheduler_task = asyncio.create_task(start_daily_digest_scheduler())
    try:
        yield
    finally:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="ticket-api", lifespan=lifespan)


@app.exception_handler(SpreadsheetLockedError)
def spreadsheet_locked_handler(
    request: Request, exc: SpreadsheetLockedError
) -> JSONResponse:
    return JSONResponse(
        status_code=423,
        content={"detail": str(exc)},
    )


@app.exception_handler(RequestValidationError)
def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = exc.errors()
    messages = []
    for err in errors:
        loc = " -> ".join(str(item) for item in err.get("loc", []) if item != "body")
        msg = err.get("msg", "Invalid value")
        messages.append(f"{loc}: {msg}" if loc else msg)
    detail_str = (
        f"Input validation failed: {'; '.join(messages)}"
        if messages
        else "Input validation failed."
    )
    return JSONResponse(
        status_code=422,
        content={"detail": detail_str},
    )


@app.exception_handler(Exception)
def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled internal exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error occurred. Please try again or contact support."
        },
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

retriever = KBRetriever()


@app.get("/health")
def health_check() -> JSONResponse:
    """System health check endpoint with subsystem diagnostics."""
    checks: dict[str, str] = {}
    is_healthy = True

    # 1. Tracking sheet storage
    try:
        check_storage_health()
        checks["storage"] = "accessible"
    except (SpreadsheetLockedError, OSError, PermissionError) as e:
        is_healthy = False
        checks["storage"] = f"error: {e}"

    # 2. Tickets seed data
    if TICKETS is not None:
        checks["tickets_data"] = "loaded"
    else:
        is_healthy = False
        checks["tickets_data"] = "error: tickets not loaded"

    # 3. Knowledge base retrieval index
    if retriever is not None and getattr(retriever, "articles", None):
        checks["knowledge_base"] = "indexed"
    else:
        is_healthy = False
        checks["knowledge_base"] = "error: knowledge base unavailable"

    status_str = "healthy" if is_healthy else "degraded"
    status_code = 200 if is_healthy else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": status_str,
            "version": "1.0.0",
            "storage": checks["storage"],
            "tickets_data": checks["tickets_data"],
            "knowledge_base": checks["knowledge_base"],
        },
    )


def to_public_ticket_dict(ticket: dict[str, Any]) -> dict[str, Any]:
    """Serialize internal ticket record to public API representation."""
    public_dict = {
        "ticket_id": ticket.get("ticket_id"),
        "created_at": format_display_date(ticket.get("created_at")),
        "resolved_at": (
            format_display_date(ticket.get("resolved_at"))
            if ticket.get("resolved_at")
            else None
        ),
        "category": ticket.get("category"),
        "priority": ticket.get("priority"),
        "status": ticket.get("status"),
    }
    customer_email = ticket.get("customer_email") or ticket.get("requester_email")
    if customer_email:
        public_dict["customer_email"] = customer_email

    labels = ticket.get("labels") or ticket.get("tags")
    if labels:
        public_dict["labels"] = labels

    if ticket.get("assigned_to"):
        public_dict["assigned_to"] = ticket.get("assigned_to")

    if ticket.get("refund_amount") is not None and ticket.get("refund_amount") != "":
        try:
            amt = float(
                str(ticket.get("refund_amount"))
                .replace("$", "")
                .replace(",", "")
                .strip()
            )
            public_dict["refund_amount"] = f"{amt:.2f}"
        except ValueError:
            public_dict["refund_amount"] = "0.00"

    return public_dict


@app.get("/tickets")
def list_tickets(page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100)):
    start = (page - 1) * size
    return [to_public_ticket_dict(t) for t in TICKETS[start : start + size]]


@app.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: str):
    for t in TICKETS:
        if t["ticket_id"] == ticket_id:
            return to_public_ticket_dict(t)
    raise HTTPException(status_code=404, detail="ticket not found")


@app.get("/summary")
def summary():
    metrics, _ = compute_metrics(TICKETS)
    return {
        "total": len(TICKETS),
        "by_category": dict(metrics.category_counts),
        "average_resolution_hours": metrics.overall_average_hours(),
        "category_averages": metrics.category_average_hours(),
        "skipped_tickets": metrics.skipped_tickets,
    }


@app.post("/ops/sync-ticket")
def ops_sync_ticket(req: SyncTicketRequest) -> dict[str, Any]:
    row = sync_ticket_to_spreadsheet(req.model_dump())
    alert = send_escalation_alert(row)
    return {"ticket": row, "escalation_alert": alert}


@app.get("/ops/approvals/pending")
def ops_get_pending() -> dict[str, Any]:
    pending = get_pending_approvals()
    return {"pending_count": len(pending), "pending_approvals": pending}


@app.post("/ops/approvals/send-digest")
def ops_send_digest() -> dict[str, Any]:
    digest = generate_batch_digest()
    return digest


@app.get("/ops/approvals/{ticket_id}/action", response_class=HTMLResponse)
def ops_approval_action(ticket_id: str, status: str = Query(...)) -> HTMLResponse:
    clean_ticket_id = ticket_id.strip()
    if not clean_ticket_id:
        raise HTTPException(
            status_code=400,
            detail="Ticket ID cannot be empty or whitespace.",
        )
    try:
        approval_status = ApprovalStatusEnum.from_action(status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        update_approval_status(clean_ticket_id, new_status=approval_status.value)
    except ValueError as e:
        raise HTTPException(
            status_code=404, detail=f"Ticket not found: {clean_ticket_id}"
        ) from e

    receipt_html = f"<html><body><h3>✓ Ticket {clean_ticket_id} marked {approval_status.value}. You may close this tab.</h3></body></html>"
    return HTMLResponse(content=receipt_html, status_code=200)


@app.post("/triage", response_model=TriageResponse)
def triage(req: TriageRequest) -> TriageResponse:
    matched = retriever.retrieve(req.subject, req.text)
    res = classify_and_reply(req.subject, req.text, matched_articles=matched)
    if str(res.category) == "Billing":
        clean_subj = sanitize_cell(req.subject)
        clean_text = sanitize_cell(req.text)

        row = sync_ticket_to_spreadsheet(
            {
                "ticket_id": req.ticket_id,
                "customer_name": req.customer_name,
                "category": "Billing",
                "priority": str(res.priority),
                "reason": req.reason,
                "subject": clean_subj,
                "text": clean_text,
                "agent": req.agent,
            }
        )
        if str(res.priority) == "urgent":
            send_escalation_alert(row)
    return res


@app.get("/triage-ui")
def redirect_triage_ui():
    return RedirectResponse(url="/triage-ui/")


@app.get("/triage")
def redirect_triage():
    return RedirectResponse(url="/triage-ui/")


if FRONTEND_DIR.exists():
    app.mount(
        "/triage-ui",
        StaticFiles(directory=FRONTEND_DIR, html=True),
        name="triage_ui",
    )

app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
