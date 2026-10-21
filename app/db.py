"""MongoDB Atlas database persistence layer module."""

import csv
import logging
import os
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

# Configure DNS resolver with reliable fallbacks for mongodb+srv:// records
try:
    import dns.resolver

    _resolver = dns.resolver.get_default_resolver()
    for _ns in ("8.8.8.8", "1.1.1.1", "8.8.4.4"):
        if _ns not in _resolver.nameservers:
            _resolver.nameservers.append(_ns)
except (ImportError, AttributeError, OSError) as _dns_err:
    logger.debug("Could not configure fallback DNS nameservers: %s", _dns_err)

try:
    import certifi

    _ca_file: str | None = certifi.where()
except (ImportError, OSError) as _cert_err:
    logger.debug("Certifi root CA bundle unavailable: %s", _cert_err)
    _ca_file = None

try:
    from pymongo import MongoClient, UpdateOne
    from pymongo.errors import PyMongoError

    PYMONGO_AVAILABLE = True
except ImportError:
    PYMONGO_AVAILABLE = False
    MongoClient = None
    UpdateOne = None
    PyMongoError = Exception

_client: Any = None
_client_lock = threading.Lock()
_last_connect_attempt: float = 0.0
_CONNECT_RETRY_INTERVAL: float = 10.0
_db_initialized = False
_init_lock = threading.Lock()


def get_mongodb_uri() -> str | None:
    """Return MongoDB connection URI from environment."""
    return os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")


def get_mongodb_db_name() -> str:
    """Return MongoDB database name."""
    return os.getenv("MONGODB_DB_NAME", "ticket_db")


def is_mongodb_enabled() -> bool:
    """Check whether MongoDB persistence is configured and active."""
    if not PYMONGO_AVAILABLE:
        return False
    if "pytest" in sys.modules and os.getenv("TEST_USE_MONGODB") != "1":
        return False
    uri = get_mongodb_uri()
    if not uri or not uri.strip():
        return False
    disabled = os.getenv("DISABLE_MONGODB", "").strip().lower()
    return disabled not in ("1", "true", "yes")


def get_mongodb_client() -> Any | None:
    """Return singleton MongoClient with connection pooling and timeout guards."""
    global _client, _last_connect_attempt
    if not is_mongodb_enabled():
        return None
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        now = time.time()
        if now - _last_connect_attempt < _CONNECT_RETRY_INTERVAL:
            return None
        uri = get_mongodb_uri()
        client_kwargs: dict[str, Any] = {
            "serverSelectionTimeoutMS": 5000,
            "connectTimeoutMS": 5000,
            "socketTimeoutMS": 10000,
            "maxPoolSize": 20,
            "minPoolSize": 1,
        }
        if _ca_file:
            client_kwargs["tlsCAFile"] = _ca_file
        try:
            c = MongoClient(uri, **client_kwargs)
            # Validate connection with ping probe
            c.admin.command("ping")
            _client = c
            _last_connect_attempt = 0.0
        except (PyMongoError, OSError, ValueError) as err:
            logger.warning("Failed to initialize MongoClient: %s", err)
            _last_connect_attempt = now
            _client = None
            return None
    return _client


def get_db() -> Any | None:
    """Return MongoDB database instance or None if unconfigured."""
    client = get_mongodb_client()
    if client is None:
        return None
    try:
        return client[get_mongodb_db_name()]
    except (PyMongoError, OSError, KeyError) as err:
        logger.error("Failed to access MongoDB database: %s", err)
        return None


def close_mongodb_client() -> None:
    """Close the singleton MongoClient connection pool."""
    global _client, _db_initialized, _last_connect_attempt
    with _client_lock:
        if _client is not None:
            try:
                _client.close()
            except (PyMongoError, OSError) as err:
                logger.debug("Error closing MongoClient: %s", err)
            _client = None
            _db_initialized = False
            _last_connect_attempt = 0.0


def check_mongodb_health() -> tuple[bool, str]:
    """Execute ping command to verify live MongoDB connectivity."""
    if not is_mongodb_enabled():
        return (False, "disabled")
    client = get_mongodb_client()
    if client is None:
        return (False, "error: client unavailable")
    try:
        client.admin.command("ping")
        return (True, "connected")
    except (PyMongoError, OSError) as err:
        logger.warning("MongoDB ping failed: %s", err)
        return (False, f"error: {err}")


def _clean_doc(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize dictionary keys and values for clean BSON document persistence."""
    clean: dict[str, Any] = {}
    for k, v in data.items():
        if k == "_id":
            continue
        if isinstance(v, datetime):
            clean[k] = v.isoformat()
        elif isinstance(v, (str, int, float, bool)) or v is None:
            clean[k] = v
        elif isinstance(v, (list, tuple)):
            clean[k] = list(v)
        elif isinstance(v, dict):
            clean[k] = _clean_doc(v)
        else:
            clean[k] = str(v)
    return clean


def seed_initial_data_if_empty(
    seed_tickets_path: Path | str | None = None,
    seed_tracking_path: Path | str | None = None,
) -> tuple[int, int]:
    """Seed tickets and tracking records into MongoDB if collections are empty."""
    global _db_initialized
    db = get_db()
    if db is None:
        return (0, 0)

    with _init_lock:
        seeded_tickets = 0
        seeded_tracking = 0

        # Ensure unique indexes on ticket_id
        try:
            db["tickets"].create_index("ticket_id", unique=True)
            db["tracking_records"].create_index("ticket_id", unique=True)
        except (PyMongoError, OSError) as err:
            logger.warning("Could not create MongoDB indexes: %s", err)

        # 1. Seed tickets if collection is empty
        try:
            count_tickets = db["tickets"].count_documents({})
            if count_tickets == 0:
                target_path = None
                if seed_tickets_path and Path(seed_tickets_path).exists():
                    target_path = Path(seed_tickets_path)
                else:
                    base_dir = Path(__file__).resolve().parent.parent
                    helpdesk_p = base_dir / "data" / "helpdesk_export.csv"
                    sample_p = base_dir / "data" / "tickets_sample.csv"
                    if helpdesk_p.exists():
                        target_path = helpdesk_p
                    elif sample_p.exists():
                        target_path = sample_p

                if target_path and target_path.exists():
                    with open(target_path, mode="r", newline="", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        docs = []
                        for r in reader:
                            clean = {k.strip(): v.strip() for k, v in r.items() if k}
                            if clean.get("ticket_id"):
                                docs.append(clean)
                        if docs:
                            db["tickets"].insert_many(docs, ordered=False)
                            seeded_tickets = len(docs)
                            logger.info(
                                "Seeded %d tickets from %s into MongoDB",
                                seeded_tickets,
                                target_path,
                            )
        except (PyMongoError, OSError, ValueError) as err:
            logger.error("Error seeding tickets into MongoDB: %s", err)

        # 2. Seed tracking records if collection is empty
        try:
            count_tracking = db["tracking_records"].count_documents({})
            if count_tracking == 0:
                target_tracking = None
                if seed_tracking_path and Path(seed_tracking_path).exists():
                    target_tracking = Path(seed_tracking_path)
                else:
                    base_dir = Path(__file__).resolve().parent.parent
                    ops_p = base_dir / "data" / "ops_tracking_sheet.csv"
                    if ops_p.exists() and ops_p.stat().st_size > 0:
                        target_tracking = ops_p

                if target_tracking and target_tracking.exists():
                    with open(
                        target_tracking, mode="r", newline="", encoding="utf-8"
                    ) as f:
                        reader = csv.DictReader(f)
                        docs = []
                        for r in reader:
                            clean = {k.strip(): v.strip() for k, v in r.items() if k}
                            if clean.get("ticket_id"):
                                docs.append(clean)
                        if docs:
                            db["tracking_records"].insert_many(docs, ordered=False)
                            seeded_tracking = len(docs)
                            logger.info(
                                "Seeded %d tracking records from %s into MongoDB",
                                seeded_tracking,
                                target_tracking,
                            )
        except (PyMongoError, OSError, ValueError) as err:
            logger.error("Error seeding tracking records into MongoDB: %s", err)

        _db_initialized = True
        return (seeded_tickets, seeded_tracking)


def fetch_all_tickets() -> list[dict[str, Any]]:
    """Retrieve all tickets from MongoDB with normalized timestamps and aliases."""
    db = get_db()
    if db is None:
        return []
    from app.tracking_sync import normalize_currency_amount
    from ticket_summary import parse_iso_timestamp

    docs = list(db["tickets"].find({}, {"_id": 0}))
    results = []
    for row in docs:
        row["created"] = parse_iso_timestamp(row.get("created_at"))
        row["resolved"] = parse_iso_timestamp(row.get("resolved_at"))
        for a, b in (
            ("labels", "tags"),
            ("customer_email", "requester_email"),
            ("assigned_to", "agent"),
        ):
            if a in row and b not in row:
                row[b] = row[a]
            elif b in row and a not in row:
                row[a] = row[b]
        if "refund_amount" in row and row["refund_amount"] is not None:
            row["refund_amount"] = normalize_currency_amount(row["refund_amount"])
        if "resolved_at" not in row:
            row["resolved_at"] = None
        results.append(row)
    return results


def fetch_ticket_by_id(ticket_id: str) -> dict[str, Any] | None:
    """Retrieve a single ticket by ticket_id from MongoDB."""
    db = get_db()
    if db is None:
        return None
    from app.tracking_sync import normalize_currency_amount
    from ticket_summary import parse_iso_timestamp

    doc = db["tickets"].find_one({"ticket_id": ticket_id}, {"_id": 0})
    if not doc:
        doc = db["tickets"].find_one(
            {
                "ticket_id": {
                    "$regex": f"^{re.escape(ticket_id)}$",
                    "$options": "i",
                }
            },
            {"_id": 0},
        )
    if not doc:
        return None

    doc["created"] = parse_iso_timestamp(doc.get("created_at"))
    doc["resolved"] = parse_iso_timestamp(doc.get("resolved_at"))
    for a, b in (
        ("labels", "tags"),
        ("customer_email", "requester_email"),
        ("assigned_to", "agent"),
    ):
        if a in doc and b not in doc:
            doc[b] = doc[a]
        elif b in doc and a not in doc:
            doc[a] = doc[b]
    if "refund_amount" in doc and doc["refund_amount"] is not None:
        doc["refund_amount"] = normalize_currency_amount(doc["refund_amount"])
    if "resolved_at" not in doc:
        doc["resolved_at"] = None
    return doc


def upsert_ticket(ticket: dict[str, Any]) -> dict[str, Any]:
    """Insert or update a ticket document in MongoDB."""
    db = get_db()
    if db is None:
        return ticket
    clean = _clean_doc(ticket)
    ticket_id = clean.get("ticket_id")
    if not ticket_id:
        return ticket
    db["tickets"].update_one({"ticket_id": ticket_id}, {"$set": clean}, upsert=True)
    return clean


def upsert_tickets_batch(tickets: list[dict[str, Any]]) -> None:
    """Insert or update multiple tickets in MongoDB in a single bulk operation."""
    db = get_db()
    if db is None or not tickets:
        return
    operations = []
    for t in tickets:
        clean = _clean_doc(t)
        ticket_id = clean.get("ticket_id")
        if ticket_id:
            operations.append(
                UpdateOne({"ticket_id": ticket_id}, {"$set": clean}, upsert=True)
            )
    if operations:
        db["tickets"].bulk_write(operations, ordered=False)


def fetch_all_tracking_records() -> list[dict[str, Any]]:
    """Retrieve all operational tracking records from MongoDB with normalized fields."""
    db = get_db()
    if db is None:
        return []
    from app.tracking_sync import (
        _AUDIT_NOTES_CACHE,
        _REASON_CACHE,
        check_escalation_in_labels,
        normalize_category_str,
        normalize_priority_str,
    )

    docs = list(db["tracking_records"].find({}, {"_id": 0}))
    records = []
    for r in docs:
        if r.get("priority"):
            r["priority"] = normalize_priority_str(r["priority"])
        if r.get("category"):
            r["category"] = normalize_category_str(r["category"])
        if "assigned_to" in r and not r.get("agent"):
            r["agent"] = r["assigned_to"]
        elif "agent" in r and not r.get("assigned_to"):
            r["assigned_to"] = r["agent"]
        if "refund_amount" in r and not r.get("amount"):
            r["amount"] = r["refund_amount"]
        elif "amount" in r and not r.get("refund_amount"):
            r["refund_amount"] = r["amount"]
        if "labels" in r and not r.get("escalated"):
            r["escalated"] = (
                "True" if check_escalation_in_labels(r["labels"]) else "False"
            )
        elif "escalated" in r and not r.get("labels"):
            r["labels"] = (
                "escalated" if str(r.get("escalated", "")).lower() == "true" else ""
            )
        if "customer_email" in r and not r.get("customer_name"):
            r["customer_name"] = r["customer_email"]
        elif "customer_name" in r and not r.get("customer_email"):
            r["customer_email"] = (
                r["customer_name"] if "@" in str(r["customer_name"]) else ""
            )
        tid = r.get("ticket_id", "")
        if not r.get("notes") and tid in _AUDIT_NOTES_CACHE:
            r["notes"] = _AUDIT_NOTES_CACHE[tid]
        elif "notes" not in r:
            r["notes"] = ""
        if not r.get("reason") and tid in _REASON_CACHE:
            r["reason"] = _REASON_CACHE[tid]
        elif "reason" not in r:
            r["reason"] = ""
        if "updated_at" not in r:
            r["updated_at"] = ""
        records.append(r)
    return records


def upsert_tracking_record(record: dict[str, Any]) -> dict[str, Any]:
    """Insert or update an operational tracking record in MongoDB."""
    db = get_db()
    if db is None:
        return record
    clean = _clean_doc(record)
    ticket_id = clean.get("ticket_id")
    if not ticket_id:
        return record
    db["tracking_records"].update_one(
        {"ticket_id": ticket_id}, {"$set": clean}, upsert=True
    )
    return clean


def upsert_tracking_records_batch(records: list[dict[str, Any]]) -> None:
    """Insert or update multiple tracking records in MongoDB in a single bulk operation."""
    db = get_db()
    if db is None or not records:
        return
    operations = []
    for r in records:
        clean = _clean_doc(r)
        ticket_id = clean.get("ticket_id")
        if ticket_id:
            operations.append(
                UpdateOne({"ticket_id": ticket_id}, {"$set": clean}, upsert=True)
            )
    if operations:
        db["tracking_records"].bulk_write(operations, ordered=False)


def clear_tracking_records() -> int:
    """Delete all operational tracking records from MongoDB."""
    db = get_db()
    if db is None:
        return 0
    res = db["tracking_records"].delete_many({})
    return int(res.deleted_count)


def get_max_ticket_number_from_db() -> int:
    """Find the highest numerical ticket ID suffix in MongoDB."""
    db = get_db()
    if db is None:
        return 1019
    highest = 1019
    try:
        for doc in db["tickets"].find({}, {"ticket_id": 1, "_id": 0}):
            tid = str(doc.get("ticket_id", ""))
            m = re.search(r"TCK-(\d+)", tid, re.IGNORECASE)
            if m:
                highest = max(highest, int(m.group(1)))
        for doc in db["tracking_records"].find({}, {"ticket_id": 1, "_id": 0}):
            tid = str(doc.get("ticket_id", ""))
            m = re.search(r"TCK-(\d+)", tid, re.IGNORECASE)
            if m:
                highest = max(highest, int(m.group(1)))
    except (PyMongoError, OSError, ValueError) as err:
        logger.debug("Failed scanning max ticket id in MongoDB: %s", err)
    return highest
