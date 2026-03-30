"""Data models for the Customer Support Ticket workflow.

Replaces: TicketState TypedDict from the original LangGraph agent.
Each activity has typed input/output dataclasses for Temporal serialization.
"""

from dataclasses import dataclass, field
from enum import Enum


# ── Enums ────────────────────────────────────────────────────────────────────


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    FRUSTRATED = "frustrated"
    ANGRY = "angry"


class TicketCategory(str, Enum):
    BILLING = "billing"
    SHIPPING = "shipping"
    PRODUCT_ISSUE = "product_issue"
    ACCOUNT = "account"
    GENERAL_INQUIRY = "general_inquiry"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


# ── Activity I/O Models ─────────────────────────────────────────────────────


@dataclass
class AnalyzeSentimentInput:
    message: str


@dataclass
class AnalyzeSentimentOutput:
    sentiment: Sentiment


@dataclass
class ClassifyTicketInput:
    message: str


@dataclass
class ClassifyTicketOutput:
    category: TicketCategory
    priority: Priority


@dataclass
class FetchOrderInput:
    message: str


@dataclass
class FetchOrderOutput:
    order_info: dict = field(default_factory=dict)


@dataclass
class DraftResponseInput:
    message: str
    category: str
    priority: str
    sentiment: str
    order_info: dict = field(default_factory=dict)


@dataclass
class DraftResponseOutput:
    draft_response: str


@dataclass
class ReviewRefineInput:
    message: str
    draft_response: str


@dataclass
class ReviewRefineOutput:
    final_response: str


@dataclass
class SendResponseInput:
    ticket_id: str
    customer_email: str
    category: str
    response_text: str


@dataclass
class SendResponseOutput:
    final_response: str
    email_status: str
    logged: bool


# ── Workflow I/O ─────────────────────────────────────────────────────────────


@dataclass
class TicketWorkflowInput:
    ticket_id: str
    customer_email: str
    message: str


@dataclass
class TicketWorkflowOutput:
    ticket_id: str
    category: str
    priority: str
    sentiment: str
    final_response: str
