"""Unit tests for individual activities.

Tests use mocked LLM calls to verify activity logic in isolation,
without needing an OpenAI API key or a Temporal server.
"""

import json
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from temporalio.testing import ActivityEnvironment

from activities import (
    analyze_sentiment,
    classify_ticket,
    draft_response,
    fetch_order_details,
    review_and_refine,
    send_response,
)
from models import (
    AnalyzeSentimentInput,
    ClassifyTicketInput,
    DraftResponseInput,
    FetchOrderInput,
    Priority,
    ReviewRefineInput,
    SendResponseInput,
    Sentiment,
    TicketCategory,
)


@pytest.fixture
def activity_env():
    return ActivityEnvironment()


def _mock_openai_response(text: str):
    """Create a mock OpenAI chat completion response."""
    mock_message = MagicMock()
    mock_message.content = text
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


# ── Deterministic Activities ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fetch_order_details_with_order_id(activity_env: ActivityEnvironment):
    result = await activity_env.run(
        fetch_order_details,
        FetchOrderInput(message="My order ORD-98765 hasn't arrived"),
    )
    assert result.order_info["order_id"] == "ORD-98765"
    assert result.order_info["status"] == "shipped"


@pytest.mark.asyncio
async def test_fetch_order_details_without_order_id(activity_env: ActivityEnvironment):
    result = await activity_env.run(
        fetch_order_details,
        FetchOrderInput(message="I have a general question about returns"),
    )
    assert "note" in result.order_info
    assert "No order ID" in result.order_info["note"]


@pytest.mark.asyncio
async def test_send_response_calls_email_and_crm(activity_env: ActivityEnvironment):
    result = await activity_env.run(
        send_response,
        SendResponseInput(
            ticket_id="TKT-001",
            customer_email="test@example.com",
            category="shipping",
            response_text="Your package is on the way!",
        ),
    )
    assert result.email_status == "sent"
    assert result.logged is True
    assert result.final_response == "Your package is on the way!"


# ── LLM-as-Function Activities ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_sentiment(activity_env: ActivityEnvironment):
    with patch("activities.llm_client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_openai_response("frustrated")
        )
        result = await activity_env.run(
            analyze_sentiment,
            AnalyzeSentimentInput(message="I'm really frustrated with this service"),
        )
        assert result.sentiment == Sentiment.FRUSTRATED


@pytest.mark.asyncio
async def test_analyze_sentiment_fallback_on_invalid(activity_env: ActivityEnvironment):
    with patch("activities.llm_client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_openai_response("somewhat_annoyed")
        )
        result = await activity_env.run(
            analyze_sentiment,
            AnalyzeSentimentInput(message="I'm not too happy"),
        )
        # Falls back to NEUTRAL for unrecognized values
        assert result.sentiment == Sentiment.NEUTRAL


@pytest.mark.asyncio
async def test_classify_ticket(activity_env: ActivityEnvironment):
    with patch("activities.llm_client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_openai_response(
                json.dumps({"category": "shipping", "priority": "high"})
            )
        )
        result = await activity_env.run(
            classify_ticket,
            ClassifyTicketInput(message="My package hasn't arrived"),
        )
        assert result.category == TicketCategory.SHIPPING
        assert result.priority == Priority.HIGH


@pytest.mark.asyncio
async def test_draft_response(activity_env: ActivityEnvironment):
    with patch("activities.llm_client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_openai_response(
                "We apologize for the delay. Your tracking number is 1Z999."
            )
        )
        result = await activity_env.run(
            draft_response,
            DraftResponseInput(
                message="Where is my order?",
                category="shipping",
                priority="high",
                sentiment="frustrated",
                order_info={"tracking": "1Z999"},
            ),
        )
        assert len(result.draft_response) > 0
        assert "1Z999" in result.draft_response


@pytest.mark.asyncio
async def test_review_and_refine(activity_env: ActivityEnvironment):
    with patch("activities.llm_client") as mock_client:
        mock_client.chat.completions.create = AsyncMock(
            return_value=_mock_openai_response(
                "Dear Customer, we sincerely apologize..."
            )
        )
        result = await activity_env.run(
            review_and_refine,
            ReviewRefineInput(
                message="Where is my order?",
                draft_response="Sorry about that. Here is your tracking.",
            ),
        )
        assert len(result.final_response) > 0
