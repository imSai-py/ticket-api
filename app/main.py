import csv
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.retrieval import KBRetriever
from app.schemas import TriageRequest, TriageResponse
from app.triage_ai import classify_and_reply
from ticket_summary import compute_metrics, parse_iso_timestamp

load_dotenv()

DEFAULT_DATA_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "tickets_sample.csv"
)
DATA_PATH_ENV = os.environ.get("TICKETS_DATA_PATH")
DATA_PATH = Path(DATA_PATH_ENV).resolve() if DATA_PATH_ENV else DEFAULT_DATA_PATH
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def load_tickets(path):
    tickets = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            row["created"] = parse_iso_timestamp(row["created_at"])
            row["resolved"] = parse_iso_timestamp(row["resolved_at"])
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
    return {
        k: ticket[k]
        for k in (
            "ticket_id",
            "created_at",
            "resolved_at",
            "category",
            "priority",
            "status",
        )
    }


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


@app.post("/triage", response_model=TriageResponse)
def triage(req: TriageRequest):
    matched = retriever.retrieve(req.subject, req.text)
    return classify_and_reply(req.subject, req.text, matched_articles=matched)


if FRONTEND_DIR.exists():
    app.mount(
        "/triage-ui",
        StaticFiles(directory=FRONTEND_DIR, html=True),
        name="triage_ui",
    )

app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
