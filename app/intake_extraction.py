"""Automated Ticket Intake Extraction and Auto-Populate Service (Issue #41)."""

import re

from app.retrieval import KBRetriever
from app.schemas import (
    CategoryEnum,
    IntakeExtractionRequest,
    IntakeExtractionResponse,
    PriorityEnum,
)
from app.tracking_sync import extract_amount, extract_operational_reason
from app.triage_ai import classify_and_reply


def extract_customer_identity(
    text: str,
    provided_name: str | None = None,
    provided_email: str | None = None,
) -> tuple[str, str | None]:
    """Extract customer name and email address from message text with clean fallbacks."""
    name: str = "Customer"
    email: str | None = None

    if provided_name and provided_name.strip():
        name = provided_name.strip()
    else:
        # 1. Check for introduction: "My name is <Name>" or "I am <Name>"
        intro_match = re.search(
            r"\b(?:my name is|i am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",
            text,
            re.IGNORECASE,
        )
        if intro_match:
            name = intro_match.group(1).strip()
        else:
            # 2. Check for explicit "Name: <Name>" label
            name_label_match = re.search(
                r"\b(?:name|customer name)[:\s]+([A-Za-z]+(?:\s+[A-Za-z]+)?)\b",
                text,
                re.IGNORECASE,
            )
            if name_label_match:
                name = name_label_match.group(1).strip()
            else:
                # 3. Check for signoff: "Best regards,\n<Name>"
                signoff_match = re.search(
                    r"(?:best regards|regards|sincerely|thanks|thank you|cheers),?\s*\n+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b",
                    text,
                    re.IGNORECASE,
                )
                if signoff_match:
                    name = signoff_match.group(1).strip()

    if provided_email and provided_email.strip():
        email = provided_email.strip()
    else:
        # Match standard email address in text
        email_match = re.search(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
            text,
        )
        if email_match:
            email = email_match.group(0).strip()

    return name, email


def extract_agent_context(
    header_agent: str | None = None,
    provided_agent: str | None = None,
) -> str:
    """Resolve handling agent name from user session, authorization headers, or system defaults."""
    if provided_agent and provided_agent.strip():
        return provided_agent.strip()
    if header_agent and header_agent.strip():
        return header_agent.strip()
    return "Sai"


def extract_or_generate_subject(
    text: str,
    provided_subject: str | None = None,
) -> str:
    """Preserve existing subject or synthesize a concise 5-to-8 word summary subject."""
    if provided_subject and provided_subject.strip():
        return provided_subject.strip()

    lower = text.lower()
    if any(
        k in lower
        for k in (
            "double charge",
            "charged twice",
            "refund",
            "overcharge",
            "billed twice",
        )
    ):
        return "Refund Request for Subscription Charge"
    if any(
        k in lower
        for k in (
            "password",
            "locked out",
            "cannot sign in",
            "login error",
            "sign in",
            "log in",
        )
    ):
        return "Password Reset and Account Access Issue"
    if any(
        k in lower
        for k in (
            "shipping",
            "delivery",
            "track order",
            "tracking",
            "package delayed",
        )
    ):
        return "Shipping and Package Delivery Status"
    if any(
        k in lower
        for k in (
            "cancel subscription",
            "cancel plan",
            "stop renewal",
            "downgrade",
        )
    ):
        return "Subscription Cancellation and Account Update"
    if any(k in lower for k in ("invoice", "statement", "receipt", "billing question")):
        return "Billing Invoice and Payment Receipt Request"

    # Fallback to the first non-empty line truncated to 5-8 words
    for line in text.splitlines():
        line_clean = line.strip()
        if line_clean:
            words = line_clean.split()
            if len(words) >= 3:
                concise = " ".join(words[:8]).rstrip(".,;:!?")
                return concise.capitalize()
            break

    return "General Customer Support Request"


def extract_operational_reason_with_fallback(
    subject: str,
    text: str,
    category: str = "",
) -> str:
    """Derive root cause operational reason for tracking, falling back to clean category defaults."""
    reason = extract_operational_reason(subject, text)
    if reason and reason != subject:
        return reason

    category_clean = category.strip().lower()
    if "refund" in category_clean:
        return "Customer refund request"
    elif "bill" in category_clean:
        return "Customer billing and charge review"
    elif "login" in category_clean:
        return "Account authentication lockout"
    elif "ship" in category_clean:
        return "Shipment tracking and delivery status"
    elif "tech" in category_clean:
        return "Technical issue investigation"
    elif "account" in category_clean:
        return "Customer account update request"

    return reason or "Customer support inquiry"


def perform_intake_extraction(
    req: IntakeExtractionRequest,
    header_agent: str | None = None,
    retriever: KBRetriever | None = None,
) -> IntakeExtractionResponse:
    """Execute complete automated extraction and classification pipeline."""
    # 1. Identity & Agent Resolution
    customer_name, customer_email = extract_customer_identity(
        req.text, req.customer_name, req.customer_email
    )
    agent = extract_agent_context(header_agent, req.agent)
    subject = extract_or_generate_subject(req.text, req.subject)

    # 2. Financial Amount Extraction
    amount_val, _ = extract_amount(req.text)

    # 3. Knowledge Base Retrieval & AI Classification
    matched_articles = []
    if retriever:
        matched_articles = retriever.retrieve(subject, req.text)

    triage_res = classify_and_reply(
        subject, req.text, matched_articles=matched_articles
    )

    # Deterministic category override aligned with Ticket #42 rules
    combined_lower = f"{subject} {req.text}".lower()
    if amount_val > 0.0 or "refund" in combined_lower:
        resolved_category = CategoryEnum.REFUNDS
    elif any(
        kw in combined_lower
        for kw in ("billing", "invoice", "charge", "charged", "payment", "subscription")
    ):
        resolved_category = CategoryEnum.BILLING
    else:
        resolved_category = triage_res.category

    # Priority escalation
    resolved_priority = triage_res.priority
    if amount_val > 0.0 or "urgent" in combined_lower or "immediate" in combined_lower:
        resolved_priority = PriorityEnum.URGENT

    # 4. Operational Reason Derivation
    operational_reason = extract_operational_reason_with_fallback(
        subject, req.text, category=str(resolved_category)
    )

    # 5. Track Auto-Populated Fields
    auto_populated_fields: list[str] = []
    if not req.customer_name or not req.customer_name.strip():
        auto_populated_fields.append("customer_name")
    if (not req.customer_email or not req.customer_email.strip()) and customer_email:
        auto_populated_fields.append("customer_email")
    if not req.agent or not req.agent.strip():
        auto_populated_fields.append("agent")
    if not req.subject or not req.subject.strip():
        auto_populated_fields.append("subject")
    auto_populated_fields.extend(["operational_reason", "category", "priority"])
    if amount_val > 0.0:
        auto_populated_fields.append("refund_amount")

    return IntakeExtractionResponse(
        customer_name=customer_name,
        customer_email=customer_email,
        agent=agent,
        subject=subject,
        operational_reason=operational_reason,
        category=resolved_category,
        priority=resolved_priority,
        suggested_reply=triage_res.suggested_reply,
        article_ids=triage_res.article_ids,
        refund_amount=amount_val,
        auto_populated_fields=auto_populated_fields,
    )
