"""Temporal activities for the Customer Support Ticket workflow.

Each activity corresponds to one node from the original LangGraph agent.
Node classifications are noted in docstrings.

Original: examples/customer_support_agent.py
"""

import json
import re

from temporalio import activity

from llm_utils import llm_client, DEFAULT_MODEL
from models import (
    AnalyzeSentimentInput,
    AnalyzeSentimentOutput,
    ClassifyTicketInput,
    ClassifyTicketOutput,
    DraftResponseInput,
    DraftResponseOutput,
    FetchOrderInput,
    FetchOrderOutput,
    ReviewRefineInput,
    ReviewRefineOutput,
    SendResponseInput,
    SendResponseOutput,
    Priority,
    Sentiment,
    TicketCategory,
)


# ── Deterministic Activities ─────────────────────────────────────────────────


def _lookup_order(order_id: str) -> dict:
    """Fetch order details from the orders database."""
    # TODO: Replace with real DB call
    return {
        "order_id": order_id,
        "status": "shipped",
        "tracking": "1Z999AA10123456784",
        "estimated_delivery": "2025-04-02",
        "items": ["Wireless Mouse", "USB-C Hub"],
    }


def _send_email(to: str, subject: str, body: str) -> dict:
    """Send an email via the email service."""
    # TODO: Replace with real email service call
    return {"status": "sent", "message_id": f"msg_{to[:5]}_12345"}


def _log_ticket_resolution(ticket_id: str, category: str, resolution: str) -> dict:
    """Log the ticket resolution to the CRM system."""
    # TODO: Replace with real CRM call
    return {"logged": True, "ticket_id": ticket_id}


@activity.defn
async def fetch_order_details(input: FetchOrderInput) -> FetchOrderOutput:
    """DETERMINISTIC: Regex extraction + DB lookup. No LLM involved."""
    order_match = re.search(r"ORD-\d+", input.message)
    if order_match:
        order_info = _lookup_order(order_match.group())
    else:
        order_info = {"note": "No order ID found in message"}
    return FetchOrderOutput(order_info=order_info)


@activity.defn
async def send_response(input: SendResponseInput) -> SendResponseOutput:
    """DETERMINISTIC: Send email + log to CRM. No LLM involved."""
    email_result = _send_email(
        to=input.customer_email,
        subject=f"Re: Support Ticket {input.ticket_id}",
        body=input.response_text,
    )

    log_result = _log_ticket_resolution(
        ticket_id=input.ticket_id,
        category=input.category,
        resolution=input.response_text[:200],
    )

    return SendResponseOutput(
        final_response=input.response_text,
        email_status=email_result["status"],
        logged=log_result["logged"],
    )


# ── LLM-as-Function Activities ──────────────────────────────────────────────


@activity.defn
async def analyze_sentiment(input: AnalyzeSentimentInput) -> AnalyzeSentimentOutput:
    """LLM-AS-FUNCTION: Fixed prompt, classifies sentiment into 4 categories.
    Position in workflow is predetermined. LLM does not decide what happens next."""
    response = await llm_client.chat.completions.create(
        model=DEFAULT_MODEL,
        temperature=0,
        max_tokens=10,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a sentiment analyzer. Classify the customer message "
                    "sentiment as one of: positive, neutral, frustrated, angry. "
                    "Respond with ONLY the sentiment word."
                ),
            },
            {"role": "user", "content": input.message},
        ],
    )
    sentiment_str = response.choices[0].message.content.strip().lower()
    try:
        sentiment = Sentiment(sentiment_str)
    except ValueError:
        sentiment = Sentiment.NEUTRAL
    return AnalyzeSentimentOutput(sentiment=sentiment)


@activity.defn
async def classify_ticket(input: ClassifyTicketInput) -> ClassifyTicketOutput:
    """LLM-AS-FUNCTION: Fixed prompt, classifies category (5) and priority (4).
    Output is used by the workflow for branching, but this activity itself
    does not decide what happens next — the workflow does."""
    response = await llm_client.chat.completions.create(
        model=DEFAULT_MODEL,
        temperature=0,
        max_tokens=50,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a support ticket classifier. Given a customer message, "
                    "classify it.\n\n"
                    "Categories: billing, shipping, product_issue, account, general_inquiry\n"
                    "Priority: low, medium, high, urgent\n\n"
                    "Respond with JSON only: "
                    '{"category": "...", "priority": "..."}'
                ),
            },
            {"role": "user", "content": input.message},
        ],
    )
    raw = response.choices[0].message.content.strip()
    parsed = json.loads(raw)
    return ClassifyTicketOutput(
        category=TicketCategory(parsed["category"]),
        priority=Priority(parsed["priority"]),
    )


@activity.defn
async def draft_response(input: DraftResponseInput) -> DraftResponseOutput:
    """LLM-AS-FUNCTION: Generates a customer response from context.
    Fixed prompt template. LLM does not control flow."""
    response = await llm_client.chat.completions.create(
        model=DEFAULT_MODEL,
        temperature=0.7,
        max_tokens=500,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a customer support agent. Draft a helpful, empathetic "
                    "response to the customer based on the following context.\n\n"
                    f"Category: {input.category}\n"
                    f"Priority: {input.priority}\n"
                    f"Sentiment: {input.sentiment}\n"
                    f"Order info: {json.dumps(input.order_info)}\n\n"
                    "Keep the response concise (2-3 paragraphs). Be professional "
                    "and helpful. If order tracking info is available, include it."
                ),
            },
            {"role": "user", "content": input.message},
        ],
    )
    return DraftResponseOutput(draft_response=response.choices[0].message.content)


@activity.defn
async def review_and_refine(input: ReviewRefineInput) -> ReviewRefineOutput:
    """LLM-AS-FUNCTION: Edits a draft for tone and completeness.
    Fixed editing prompt. No routing, no tool use."""
    response = await llm_client.chat.completions.create(
        model=DEFAULT_MODEL,
        temperature=0.3,
        max_tokens=500,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an editor reviewing a customer support response. "
                    "Check for:\n"
                    "1. Empathetic tone matching the customer sentiment\n"
                    "2. All relevant order/account details included\n"
                    "3. Clear next steps for the customer\n"
                    "4. Professional formatting\n\n"
                    "Output the final polished version of the response. "
                    "Do not add commentary, just output the refined response."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Original customer message: {input.message}\n\n"
                    f"Draft response: {input.draft_response}"
                ),
            },
        ],
    )
    return ReviewRefineOutput(final_response=response.choices[0].message.content)
