"""Data validation schemas for ticket-api."""

from enum import Enum
from typing import Any, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CategoryEnum(str, Enum):
    BILLING = "Billing"
    LOGIN = "Login"
    SHIPPING = "Shipping"
    REFUNDS = "Refunds"
    TECHNICAL = "Technical"
    ACCOUNT = "Account"


class PriorityEnum(str, Enum):
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class ApprovalStatusEnum(str, Enum):
    APPROVED = "Approved"
    REJECTED = "Rejected"
    PENDING = "Pending"
    NEEDS_INFO = "needs_info"

    @classmethod
    def from_action(cls, value: str) -> "ApprovalStatusEnum":
        """Validate and convert an action string into an allowed approval status."""
        val_clean = value.strip().lower().replace("_", " ")
        if val_clean in ("approved", "approve"):
            return cls.APPROVED
        elif val_clean in ("rejected", "reject"):
            return cls.REJECTED
        elif val_clean in (
            "needs info",
            "need info",
            "need more info",
            "needs more info",
            "needs_info",
        ):
            return cls.NEEDS_INFO
        raise ValueError(
            f"Invalid status. Status must be '{cls.APPROVED.value}', '{cls.REJECTED.value}', or '{cls.NEEDS_INFO.value}'."
        )


class ApprovalActionUrls(NamedTuple):
    """Container for standardized approval action links."""

    approve_url: str
    reject_url: str
    need_info_url: str


class TriageRequest(BaseModel):
    """Incoming request for ticket triage."""

    subject: str = Field(default="", description="Subject line of customer ticket")
    text: str = Field(
        default="", description="Detailed message body of customer ticket"
    )
    customer_name: str = Field(
        default="Customer", description="Name of the customer (required in UI)"
    )
    ticket_id: str = Field(
        default="", description="Optional help desk ticket ID (e.g. TCK-1020)"
    )
    agent: str = Field(default="", description="Support agent handling the ticket")
    reason: str = Field(
        default="", description="Optional specific reason for ticket approval"
    )

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def validate_content_not_empty(self) -> "TriageRequest":
        if not self.subject.strip() and not self.text.strip():
            raise ValueError(
                "Ticket subject and text cannot both be empty or whitespace."
            )
        return self


class TriageResponse(BaseModel):
    """Structured response for ticket triage."""

    category: CategoryEnum = Field(description="Classified ticket category")
    priority: PriorityEnum = Field(description="Classified urgency priority")
    suggested_reply: str = Field(description="Polite grounded reply for the customer")
    article_ids: list[str] = Field(
        default_factory=list, description="IDs of knowledge base articles used"
    )
    operational_reason: str | None = Field(
        default=None, description="Derived operational justification or root cause"
    )
    suggested_subject: str | None = Field(
        default=None, description="Synthesized or extracted concise ticket subject"
    )

    model_config = ConfigDict(use_enum_values=True)


class OpsTicketRecord(BaseModel):
    """Typed domain model for operational tracking spreadsheet row aligned with Helpdesk Export New Format."""

    ticket_id: str = Field(description="Unique ticket identifier")
    created_at: str = Field(default="", description="Creation timestamp")
    status: str = Field(default="Pending", description="Approval lifecycle state")
    priority: str = Field(default="normal", description="Ticket urgency priority")
    category: str = Field(default="Billing", description="Ticket category")
    assigned_to: str = Field(
        default="", description="Handling agent name (aligned with helpdesk export)"
    )
    customer_email: str = Field(default="", description="Customer contact email")
    labels: str = Field(default="", description="Ticket labels and tags")
    refund_amount: str = Field(
        default="0.00", description="Formatted refund amount in USD"
    )

    customer_name: str = Field(default="Customer", description="Customer full name")
    amount: str = Field(default="0.00", description="Formatted dollar amount")
    reason: str = Field(default="", description="Operational justification")
    agent: str = Field(
        default="", description="Handling agent name (alias for assigned_to)"
    )
    escalated: str = Field(default="False", description="Urgent escalation flag")
    updated_at: str = Field(default="", description="Update timestamp")
    notes: str = Field(default="", description="Verification and audit notes")

    model_config = ConfigDict(extra="ignore")


class SyncTicketRequest(BaseModel):
    """Request model for syncing ticket directly to tracking spreadsheet."""

    ticket_id: str = Field(default="", description="Optional ticket ID")
    customer_name: str = Field(default="Customer", description="Customer full name")
    category: CategoryEnum = Field(
        default=CategoryEnum.BILLING, description="Ticket category"
    )
    priority: PriorityEnum = Field(
        default=PriorityEnum.NORMAL, description="Ticket priority"
    )
    amount: float | None = Field(
        default=None, ge=0.0, description="Monetary amount if known"
    )
    reason: str = Field(default="", description="Ticket reason")
    agent: str = Field(default="", description="Support agent handling ticket")
    escalated: bool = Field(default=False, description="Manual escalation flag")
    notes: str = Field(default="", description="Optional initial notes")
    customer_email: str = Field(default="", description="Customer contact email")
    labels: str = Field(default="", description="Ticket labels or tags")
    refund_amount: float | str | None = Field(
        default=None, description="Pre-populated refund amount"
    )

    model_config = ConfigDict(use_enum_values=True)

    @field_validator("customer_name")
    @classmethod
    def validate_customer_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("customer_name cannot be empty or whitespace.")
        return v.strip()


class HelpdeskQueryIngestRequest(BaseModel):
    """Payload for real-time helpdesk customer query intake."""

    ticket_id: str = Field(
        default="", description="Optional helpdesk ticket identifier (e.g. TCK-5007)"
    )
    subject: str = Field(default="", description="Ticket subject line")
    problem: str = Field(
        default="", description="Detailed message body or customer issue description"
    )
    customer_email: str = Field(default="", description="Customer contact email")
    customer_name: str = Field(
        default="Customer", description="Customer full name if known"
    )
    assigned_to: str = Field(
        default="", description="Support agent handling the ticket"
    )
    status: str = Field(default="open", description="Initial ticket lifecycle state")
    labels: str = Field(
        default="", description="Ticket labels or tags (e.g. escalated, vip)"
    )
    refund_amount: float | str | None = Field(
        default=None, description="Pre-identified refund amount"
    )
    category: CategoryEnum | str | None = Field(
        default=None, description="Optional explicit ticket category"
    )

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="after")
    def validate_content_present(self) -> "HelpdeskQueryIngestRequest":
        if not self.subject.strip() and not self.problem.strip():
            raise ValueError(
                "Ticket subject and problem body cannot both be empty or whitespace."
            )
        return self


class HelpdeskQueryIngestResponse(BaseModel):
    """Structured response for processed helpdesk query."""

    status: str = Field(default="success", description="Processing status")
    ticket_id: str = Field(description="Unique ticket identifier")
    category: CategoryEnum = Field(description="Classified ticket category")
    priority: PriorityEnum = Field(description="Classified urgency priority")
    refund_amount: float = Field(
        default=0.0, description="Normalized refund amount in USD"
    )
    customer_name: str = Field(description="Resolved customer name")
    assigned_to: str = Field(description="Assigned support agent")
    suggested_reply: str = Field(
        default="", description="Grounded customer response draft"
    )
    record: dict[str, Any] = Field(
        description="Structured 8-column record synced to spreadsheet"
    )
    escalated: bool = Field(
        default=False, description="Whether ticket triggered urgent escalation"
    )
    escalation_alert: dict[str, Any] | None = Field(
        default=None,
        description="Manager escalation alert details and HTML template for immediate dispatch",
    )

    model_config = ConfigDict(use_enum_values=True)


class BatchIngestRequest(BaseModel):
    """Optional JSON payload for batch ingestion."""

    csv_content: str | None = Field(default=None, description="Raw CSV string content")
    file_path: str | None = Field(default=None, description="Path to CSV file on disk")
    refund_threshold: float = Field(
        default=200.0, description="Escalation refund threshold in USD"
    )

    model_config = ConfigDict(extra="ignore")


class BatchIngestResponse(BaseModel):
    """Structured response for batch ingestion."""

    status: str = Field(default="success", description="Processing status")
    processed_count: int = Field(default=0, description="Number of tickets processed")
    records: list[dict[str, Any]] = Field(
        default_factory=list, description="List of processed ticket records"
    )
    escalated_count: int = Field(
        default=0, description="Number of tickets that triggered escalation"
    )
    escalations: list[dict[str, Any]] = Field(
        default_factory=list, description="Escalation alerts dispatched"
    )

    model_config = ConfigDict(use_enum_values=True)


class IntakeExtractionRequest(BaseModel):
    """Payload for automated ticket intake extraction."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Raw customer message or ticket body text",
    )
    subject: str | None = Field(
        default=None, max_length=500, description="Optional incoming subject line"
    )
    customer_name: str | None = Field(
        default=None, max_length=200, description="Optional customer name override"
    )
    customer_email: str | None = Field(
        default=None, max_length=200, description="Optional customer email override"
    )
    agent: str | None = Field(
        default=None, max_length=100, description="Optional handling agent context"
    )

    model_config = ConfigDict(extra="ignore")

    @field_validator("text")
    @classmethod
    def validate_text_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Message text cannot be empty or whitespace.")
        return v.strip()


class IntakeExtractionResponse(BaseModel):
    """Structured extraction output for ticket intake form auto-population."""

    customer_name: str = Field(description="Auto-extracted or fallback customer name")
    customer_email: str | None = Field(
        default=None, description="Extracted customer email address if present"
    )
    agent: str = Field(description="Auto-filled handling agent from session or rule")
    subject: str = Field(description="Preserved or synthesized concise subject")
    operational_reason: str = Field(
        description="Derived root cause operational reason for tracking"
    )
    category: CategoryEnum = Field(description="Classified ticket category")
    priority: PriorityEnum = Field(description="Classified urgency priority")
    suggested_reply: str = Field(
        default="", description="Grounded preliminary customer reply"
    )
    article_ids: list[str] = Field(
        default_factory=list, description="Relevant knowledge base article IDs"
    )
    refund_amount: float = Field(
        default=0.0, description="Extracted monetary refund amount if any"
    )
    auto_populated_fields: list[str] = Field(
        default_factory=list,
        description="List of fields that were automatically populated",
    )

    model_config = ConfigDict(use_enum_values=True)
