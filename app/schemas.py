"""Data validation schemas for ticket-api."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    agent: str = Field(default="Mara", description="Support agent handling the ticket")
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
