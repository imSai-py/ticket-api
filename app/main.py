import asyncio
import csv
import io
import logging
import os
import re
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.batch_digest import generate_batch_digest
from app.escalation import (
    send_agent_action_notification,
    send_agent_info_request_email,
    send_escalation_alert,
)
from app.retrieval import KBRetriever
from app.scheduler import start_daily_digest_scheduler
from app.schemas import (
    ApprovalStatusEnum,
    BatchIngestResponse,
    HelpdeskQueryIngestRequest,
    HelpdeskQueryIngestResponse,
    PriorityEnum,
    SyncTicketRequest,
    TriageRequest,
    TriageResponse,
)
from app.tracking_sync import (
    SpreadsheetLockedError,
    check_storage_health,
    extract_amount,
    extract_operational_reason,
    get_pending_approvals,
    normalize_currency_amount,
    resolve_ticket_priority_and_escalation,
    sanitize_cell,
    sync_ticket_to_spreadsheet,
    sync_tickets_batch_to_spreadsheet,
    update_approval_status,
)
from app.triage_ai import classify_and_reply
from ticket_summary import compute_metrics, parse_iso_timestamp

logger = logging.getLogger(__name__)

load_dotenv()

HELPDESK_EXPORT_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "helpdesk_export.csv"
)
DEFAULT_DATA_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "tickets_sample.csv"
)
DATA_PATH_ENV = os.environ.get("TICKETS_DATA_PATH")
if DATA_PATH_ENV:
    DATA_PATH = Path(DATA_PATH_ENV).resolve()
elif HELPDESK_EXPORT_PATH.exists() and "pytest" not in sys.modules:
    DATA_PATH = HELPDESK_EXPORT_PATH
else:
    DATA_PATH = DEFAULT_DATA_PATH
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
                row["refund_amount"] = normalize_currency_amount(
                    row.get("refund_amount")
                )

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

    agent_val = ticket.get("assigned_to") or ticket.get("agent")
    if agent_val:
        public_dict["assigned_to"] = agent_val

    if ticket.get("refund_amount") is not None and ticket.get("refund_amount") != "":
        amt = normalize_currency_amount(ticket.get("refund_amount"))
        public_dict["refund_amount"] = f"{amt:.2f}"

    return public_dict


def get_dataset_tickets(source: str | None = None) -> list[dict[str, Any]]:
    """Retrieve ticket dataset with optional source selector."""
    if source == "helpdesk" and HELPDESK_EXPORT_PATH.exists():
        return load_tickets(HELPDESK_EXPORT_PATH)
    if source == "sample" and DEFAULT_DATA_PATH.exists():
        return load_tickets(DEFAULT_DATA_PATH)
    return TICKETS


@app.get("/tickets")
def list_tickets(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=1000),
    category: str | None = Query(None),
    priority: str | None = Query(None),
    search: str | None = Query(None),
    source: str | None = Query(None),
):
    filtered = get_dataset_tickets(source)
    if category and category.lower() != "all":
        filtered = [
            t for t in filtered if t.get("category", "").lower() == category.lower()
        ]
    if priority and priority.lower() != "all":
        filtered = [
            t for t in filtered if t.get("priority", "").lower() == priority.lower()
        ]
    if search:
        q = search.lower().strip()
        filtered = [
            t
            for t in filtered
            if q in t.get("ticket_id", "").lower()
            or q in t.get("category", "").lower()
            or q in t.get("priority", "").lower()
            or q in (t.get("assigned_to") or t.get("agent") or "").lower()
            or q in (t.get("customer_email") or "").lower()
        ]
    start = (page - 1) * size
    return [to_public_ticket_dict(t) for t in filtered[start : start + size]]


@app.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: str):
    for t in TICKETS:
        if t["ticket_id"] == ticket_id:
            return to_public_ticket_dict(t)
    raise HTTPException(status_code=404, detail="ticket not found")


@app.get("/summary")
def summary(source: str | None = Query(None)):
    dataset = get_dataset_tickets(source)
    metrics, _ = compute_metrics(dataset)
    return {
        "total": len(dataset),
        "by_category": dict(metrics.category_counts),
        "average_resolution_hours": metrics.overall_average_hours(),
        "category_averages": metrics.category_average_hours(),
        "skipped_tickets": metrics.skipped_tickets,
    }


@app.post("/ops/sync-ticket")
def ops_sync_ticket(req: SyncTicketRequest) -> dict[str, Any]:
    row = sync_ticket_to_spreadsheet(req.model_dump())
    alert = send_escalation_alert(row)
    existing = next(
        (t for t in TICKETS if t.get("ticket_id") == row["ticket_id"]), None
    )
    if existing:
        existing.update(
            {
                "category": row["category"],
                "priority": row["priority"],
                "status": row["status"],
                "agent": row["agent"],
                "assigned_to": row["agent"],
                "customer_email": row.get("customer_email")
                or existing.get("customer_email"),
                "refund_amount": row.get("refund_amount")
                or existing.get("refund_amount"),
                "reason": row.get("reason") or existing.get("reason"),
                "labels": row.get("labels") or existing.get("labels"),
            }
        )
    else:
        TICKETS.insert(
            0,
            {
                "ticket_id": row["ticket_id"],
                "created_at": row["created_at"],
                "created": parse_iso_timestamp(row["created_at"]),
                "category": row["category"],
                "priority": row["priority"],
                "status": row["status"],
                "agent": row["agent"],
                "assigned_to": row["agent"],
                "reason": row["reason"],
            },
        )
    return {"ticket": row, "escalation_alert": alert}


@app.post("/ops/ingest-helpdesk", response_model=HelpdeskQueryIngestResponse)
def ingest_helpdesk_query(
    req: HelpdeskQueryIngestRequest,
) -> HelpdeskQueryIngestResponse:
    """Ingest a single customer query from helpdesk, analyze with AI, and persist 8-column record."""
    clean_subj = sanitize_cell(req.subject)
    clean_prob = sanitize_cell(req.problem)

    # 1. AI analysis: predict category, priority, and grounded reply
    matched = retriever.retrieve(clean_subj, clean_prob)
    ai_res = classify_and_reply(clean_subj, clean_prob, matched_articles=matched)

    # 2. Extract and normalize refund currency amount
    refund_val = 0.0
    combined_text = f"{clean_subj} {clean_prob}"
    if req.refund_amount is not None and str(req.refund_amount).strip() != "":
        refund_val = normalize_currency_amount(req.refund_amount)
    if refund_val == 0.0:
        extracted, _ = extract_amount(combined_text)
        if extracted > 0.0:
            refund_val = extracted

    # 3. Resolve customer name from input or email
    resolved_customer = req.customer_name.strip() if req.customer_name else ""
    if not resolved_customer or resolved_customer.lower() == "customer":
        if req.customer_email and "@" in req.customer_email:
            prefix = req.customer_email.split("@")[0]
            parts = [p.capitalize() for p in re.split(r"[._-]", prefix) if p]
            resolved_customer = " ".join(parts) if parts else "Customer"
        else:
            resolved_customer = "Customer"

    # 4. Resolve operational reason
    operational_reason = extract_operational_reason(clean_subj, clean_prob)

    # 5. Build sync payload
    ticket_payload: dict[str, Any] = {
        "customer_name": resolved_customer,
        "customer_email": req.customer_email,
        "category": str(ai_res.category),
        "priority": str(ai_res.priority),
        "status": req.status or "open",
        "amount": f"{refund_val:.2f}",
        "refund_amount": refund_val,
        "reason": operational_reason,
        "agent": req.assigned_to or "Unassigned",
        "labels": req.labels,
        "subject": clean_subj,
        "text": clean_prob,
    }
    if req.ticket_id.strip():
        ticket_payload["ticket_id"] = req.ticket_id.strip()

    # 6. Sync to operational tracking spreadsheet
    row = sync_ticket_to_spreadsheet(ticket_payload)

    # 7. Check priority and escalation
    effective_priority, is_urgent = resolve_ticket_priority_and_escalation(row)
    if is_urgent:
        send_escalation_alert(row)

    # 8. Update in-memory TICKETS cache
    existing = next(
        (t for t in TICKETS if t.get("ticket_id") == row["ticket_id"]), None
    )
    if existing:
        existing.update(
            {
                "category": row["category"],
                "priority": row["priority"],
                "status": row["status"],
                "agent": row["agent"],
                "assigned_to": row["agent"],
                "customer_email": req.customer_email or existing.get("customer_email"),
                "refund_amount": f"{refund_val:.2f}",
                "labels": req.labels or existing.get("labels"),
            }
        )
    else:
        TICKETS.insert(
            0,
            {
                "ticket_id": row["ticket_id"],
                "created_at": row["created_at"],
                "created": parse_iso_timestamp(row["created_at"]),
                "category": row["category"],
                "priority": row["priority"],
                "status": row["status"],
                "agent": row["agent"],
                "assigned_to": row["agent"],
                "customer_email": req.customer_email,
                "labels": req.labels,
                "refund_amount": f"{refund_val:.2f}",
                "reason": row["reason"],
            },
        )

    return HelpdeskQueryIngestResponse(
        status="success",
        ticket_id=row["ticket_id"],
        category=ai_res.category,
        priority=PriorityEnum(effective_priority.lower()),
        refund_amount=refund_val,
        customer_name=resolved_customer,
        assigned_to=row["agent"],
        suggested_reply=ai_res.suggested_reply,
        record=row,
        escalated=is_urgent,
    )


@app.post("/ops/ingest-batch", response_model=BatchIngestResponse)
async def ingest_batch_csv(
    request: Request,
    file: UploadFile | None = File(None),  # noqa: B008
    refund_threshold: float = Query(
        200.0,
        description="Refund threshold in USD to trigger escalation alerts",
    ),
) -> BatchIngestResponse:
    """Ingest multiple helpdesk tickets from CSV file upload or raw CSV text, batch sync and trigger escalations."""
    csv_text = ""
    if file is not None and getattr(file, "filename", None):
        file_bytes = await file.read()
        if not file_bytes or not file_bytes.strip():
            raise HTTPException(status_code=400, detail="Empty CSV file provided.")
        csv_text = file_bytes.decode("utf-8-sig", errors="replace")
    else:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                body = await request.json()
            except (ValueError, TypeError, KeyError):
                body = {}
            if body.get("csv_content"):
                csv_text = body["csv_content"]
            elif body.get("file_path"):
                p = Path(body["file_path"])
                if not p.exists():
                    raise HTTPException(
                        status_code=404,
                        detail=f"File not found: {body['file_path']}",
                    )
                csv_text = p.read_text(encoding="utf-8-sig")
            if "refund_threshold" in body and body["refund_threshold"] is not None:
                try:
                    refund_threshold = float(body["refund_threshold"])
                except (ValueError, TypeError):
                    pass
        elif "text/csv" in content_type or "text/plain" in content_type:
            raw_body = await request.body()
            csv_text = raw_body.decode("utf-8-sig", errors="replace")

    if not csv_text.strip():
        raise HTTPException(
            status_code=400,
            detail="Empty CSV file or content provided. Please upload a CSV file or provide csv_content.",
        )

    f = io.StringIO(csv_text.strip())
    reader = csv.DictReader(f)
    if not reader.fieldnames:
        raise HTTPException(
            status_code=400, detail="Malformed CSV: missing header row."
        )

    parsed_rows: list[dict[str, Any]] = []
    for r in reader:
        clean_row = {k.strip(): (v.strip() if v else "") for k, v in r.items() if k}
        if any(clean_row.values()):
            parsed_rows.append(clean_row)

    if not parsed_rows:
        raise HTTPException(
            status_code=400,
            detail="Empty CSV file provided: no data rows found.",
        )

    synced_records = sync_tickets_batch_to_spreadsheet(parsed_rows)

    escalations: list[dict[str, Any]] = []
    escalated_records: list[dict[str, Any]] = []
    for row in synced_records:
        alert = send_escalation_alert(
            row, refund_threshold=refund_threshold, dispatch_smtp=False
        )
        if alert.get("dispatched") is True:
            escalations.append(alert)
            escalated_records.append(row)

    # Dispatch ONE consolidated digest email for the entire batch if any tickets escalated
    if escalated_records:
        digest_recipient = (
            os.getenv("ESCALATION_MANAGER_EMAIL")
            or os.getenv("DIGEST_MANAGER_EMAIL")
            or "manager@company.com"
        )
        generate_batch_digest(
            recipient=digest_recipient,
            tickets=escalated_records,
            send_email=True,
        )

    for row in synced_records:
        existing = next(
            (t for t in TICKETS if t.get("ticket_id") == row["ticket_id"]), None
        )
        if existing:
            existing.update(
                {
                    "category": row.get("category"),
                    "priority": row.get("priority"),
                    "status": row.get("status"),
                    "agent": row.get("assigned_to"),
                    "assigned_to": row.get("assigned_to"),
                    "customer_email": row.get("customer_email"),
                    "refund_amount": row.get("refund_amount"),
                    "labels": row.get("labels"),
                }
            )
        else:
            TICKETS.insert(
                0,
                {
                    "ticket_id": row["ticket_id"],
                    "created_at": row["created_at"],
                    "created": parse_iso_timestamp(row["created_at"]),
                    "category": row.get("category"),
                    "priority": row.get("priority"),
                    "status": row.get("status"),
                    "agent": row.get("assigned_to"),
                    "assigned_to": row.get("assigned_to"),
                    "customer_email": row.get("customer_email"),
                    "labels": row.get("labels"),
                    "refund_amount": row.get("refund_amount"),
                },
            )

    return BatchIngestResponse(
        status="success",
        processed_count=len(synced_records),
        records=synced_records,
        escalated_count=len(escalations),
        escalations=escalations,
    )


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

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    action_note = ""
    if approval_status == ApprovalStatusEnum.NEEDS_INFO:
        action_note = f"Manager requested more info at {now_str}"

    try:
        updated_record = update_approval_status(
            clean_ticket_id,
            new_status=approval_status.value,
            notes=action_note,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=404, detail=f"Ticket not found: {clean_ticket_id}"
        ) from e

    # Notify assigned support agent of the manager decision
    try:
        if approval_status == ApprovalStatusEnum.NEEDS_INFO:
            send_agent_info_request_email(updated_record)
        else:
            send_agent_action_notification(updated_record, action=approval_status.value)
    except (OSError, KeyError, ValueError) as err:
        logger.warning(
            "Could not dispatch agent decision notification for %s: %s",
            clean_ticket_id,
            err,
        )

    for t in TICKETS:
        if t.get("ticket_id") == clean_ticket_id:
            t["status"] = approval_status.value
            break

    if approval_status == ApprovalStatusEnum.NEEDS_INFO:
        status_label = "as needing more info. Support agent notified."
    else:
        status_label = f"{approval_status.value}."

    receipt_html = f"<html><body><h3>✓ Ticket {clean_ticket_id} marked {status_label} You may close this tab.</h3></body></html>"
    return HTMLResponse(content=receipt_html, status_code=200)


@app.get("/ops/approvals/action", response_class=HTMLResponse)
def ops_approval_action_query(
    ticket_id: str = Query(...), status: str = Query(...)
) -> HTMLResponse:
    return ops_approval_action(ticket_id=ticket_id, status=status)


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
        existing = next(
            (t for t in TICKETS if t.get("ticket_id") == row["ticket_id"]), None
        )
        if existing:
            existing.update(
                {
                    "category": row["category"],
                    "priority": row["priority"],
                    "status": row["status"],
                    "agent": row["agent"],
                    "assigned_to": row["agent"],
                }
            )
        else:
            TICKETS.insert(
                0,
                {
                    "ticket_id": row["ticket_id"],
                    "created_at": row["created_at"],
                    "created": parse_iso_timestamp(row["created_at"]),
                    "category": row["category"],
                    "priority": row["priority"],
                    "status": row["status"],
                    "agent": row["agent"],
                    "assigned_to": row["agent"],
                    "reason": row["reason"],
                },
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
