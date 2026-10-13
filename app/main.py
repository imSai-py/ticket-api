import csv
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.retrieval import KBRetriever
from app.schemas import TriageRequest, TriageResponse
from app.summary_service import compute_metrics_from_tickets
from app.triage_ai import classify_and_reply

DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "tickets_sample.csv"
DATA_PATH_ENV = os.environ.get("TICKETS_DATA_PATH")
DATA_PATH = Path(DATA_PATH_ENV).resolve() if DATA_PATH_ENV else DEFAULT_DATA_PATH
FMT = "%Y-%m-%d %H:%M"
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def load_tickets(path):
    tickets = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            row["created"] = datetime.strptime(row["created_at"], FMT).replace(tzinfo=timezone.utc)
            row["resolved"] = (
                datetime.strptime(row["resolved_at"], FMT).replace(tzinfo=timezone.utc)
                if row["resolved_at"]
                else None
            )
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
ALLOWED_ORIGINS = [orig.strip() for orig in CORS_ORIGINS_ENV.split(",")] if CORS_ORIGINS_ENV else LOCAL_ORIGINS

app = FastAPI(title="ticket-api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

retriever = KBRetriever()


def to_public_ticket_dict(ticket):
    return {k: ticket[k] for k in ("ticket_id", "created_at", "resolved_at", "category", "priority", "status")}


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
    metrics, _ = compute_metrics_from_tickets(TICKETS)
    avg_hours = (
        round(metrics.overall_average_seconds / 3600.0, 2)
        if metrics.overall_average_seconds is not None
        else 0.0
    )
    cat_avg_hours = {
        cat: round(sec / 3600.0, 2) if sec is not None else None
        for cat, sec in metrics.category_average_seconds.items()
    }
    return {
        "total": len(TICKETS),
        "by_category": dict(metrics.category_counts),
        "average_resolution_hours": avg_hours,
        "category_averages": cat_avg_hours,
        "skipped_tickets": metrics.skipped_tickets,
    }


@app.post("/triage", response_model=TriageResponse)
def triage(req: TriageRequest):
    matched = retriever.retrieve(req.subject, req.text, top_k=2)
    return classify_and_reply(req.subject, req.text, matched_articles=matched)


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
