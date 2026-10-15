"""Data validation schemas for ticket-api."""

from enum import Enum
from typing import Any

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

    @classmethod
    def from_action(cls, value: str) -> "ApprovalStatusEnum":
        """Validate and convert an action string into an allowed approval status."""
        if value not in (cls.APPROVED.value, cls.REJECTED.value):
            raise ValueError(
                f"Invalid status. Status must be '{cls.APPROVED.value}' or '{cls.REJECTED.value}'."
            )
        return cls(value)


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
