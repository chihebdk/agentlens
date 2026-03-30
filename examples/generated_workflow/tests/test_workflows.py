"""Integration tests for the CustomerSupportTicketWorkflow.

These tests require a local Temporal server (started automatically by
WorkflowEnvironment.start_local()). LLM calls are mocked.

Run with: pytest tests/ -v
"""

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from temporalio.client import Client

from models import TicketWorkflowInput, TicketWorkflowOutput

TASK_QUEUE = "test-customer-support"


def _mock_openai_response(text: str):
    mock_message = MagicMock()
    mock_message.content = text
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


def _setup_llm_mock(mock_client):
    """Configure the mock to return appropriate responses for each activity."""
    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        messages = kwargs.get("messages", [])
        system_msg = messages[0]["content"] if messages else ""

        if "sentiment analyzer" in system_msg:
            return _mock_openai_response("frustrated")
        elif "ticket classifier" in system_msg:
            return _mock_openai_response(
                json.dumps({"category": "shipping", "priority": "high"})
            )
        elif "customer support agent" in system_msg:
            return _mock_openai_response(
                "We apologize for the inconvenience. Your order ORD-98765 "
                "is currently shipped with tracking 1Z999AA10123456784."
            )
        elif "editor reviewing" in system_msg:
            return _mock_openai_response(
                "Dear valued customer, we sincerely apologize for the delay "
                "with your order ORD-98765. Your package is currently in transit "
                "with tracking number 1Z999AA10123456784, estimated delivery April 2."
            )
        else:
            return _mock_openai_response("default response")

    mock_client.chat.completions.create = AsyncMock(side_effect=side_effect)


@pytest.mark.asyncio
async def test_full_workflow_non_urgent(client: Client, worker):
    """Test the full workflow with a non-urgent ticket (includes review step)."""
    with patch("activities.llm_client") as mock_client:
        _setup_llm_mock(mock_client)

        result = await client.execute_workflow(
            "CustomerSupportTicketWorkflow",
            TicketWorkflowInput(
                ticket_id="TKT-TEST-001",
                customer_email="jane@example.com",
                message=(
                    "My order ORD-98765 hasn't updated in 3 days. "
                    "I'm frustrated because I need it for work."
                ),
            ),
            id="test-workflow-non-urgent",
            task_queue=TASK_QUEUE,
        )

        assert result.ticket_id == "TKT-TEST-001"
        assert result.category == "shipping"
        assert result.priority == "high"
        assert result.sentiment == "frustrated"
        assert len(result.final_response) > 0
        # 4 LLM calls: sentiment, classify, draft, review
        assert mock_client.chat.completions.create.call_count == 4


@pytest.mark.asyncio
async def test_full_workflow_urgent_skips_review(client: Client, worker):
    """Test that urgent tickets skip the review step."""
    with patch("activities.llm_client") as mock_client:
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            messages = kwargs.get("messages", [])
            system_msg = messages[0]["content"] if messages else ""

            if "sentiment analyzer" in system_msg:
                return _mock_openai_response("angry")
            elif "ticket classifier" in system_msg:
                return _mock_openai_response(
                    json.dumps({"category": "shipping", "priority": "urgent"})
                )
            elif "customer support agent" in system_msg:
                return _mock_openai_response("Urgent: We are escalating this now.")
            else:
                return _mock_openai_response("default")

        mock_client.chat.completions.create = AsyncMock(side_effect=side_effect)

        result = await client.execute_workflow(
            "CustomerSupportTicketWorkflow",
            TicketWorkflowInput(
                ticket_id="TKT-TEST-002",
                customer_email="angry@example.com",
                message="This is UNACCEPTABLE. My order ORD-11111 never arrived!",
            ),
            id="test-workflow-urgent",
            task_queue=TASK_QUEUE,
        )

        assert result.priority == "urgent"
        assert result.sentiment == "angry"
        # Only 3 LLM calls: sentiment, classify, draft (review skipped)
        assert mock_client.chat.completions.create.call_count == 3


@pytest.mark.asyncio
async def test_workflow_without_order_id(client: Client, worker):
    """Test ticket without an order ID — fetch_order_details still works."""
    with patch("activities.llm_client") as mock_client:
        _setup_llm_mock(mock_client)

        # Override classify to return general_inquiry
        original_side_effect = mock_client.chat.completions.create.side_effect

        async def custom_side_effect(*args, **kwargs):
            messages = kwargs.get("messages", [])
            system_msg = messages[0]["content"] if messages else ""
            if "ticket classifier" in system_msg:
                return _mock_openai_response(
                    json.dumps({"category": "general_inquiry", "priority": "low"})
                )
            return await original_side_effect(*args, **kwargs)

        mock_client.chat.completions.create = AsyncMock(side_effect=custom_side_effect)

        result = await client.execute_workflow(
            "CustomerSupportTicketWorkflow",
            TicketWorkflowInput(
                ticket_id="TKT-TEST-003",
                customer_email="curious@example.com",
                message="What is your return policy?",
            ),
            id="test-workflow-no-order",
            task_queue=TASK_QUEUE,
        )

        assert result.category == "general_inquiry"
        assert result.priority == "low"
