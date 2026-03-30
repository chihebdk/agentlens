"""Shared test fixtures for workflow and activity tests."""

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.client import Client
from temporalio.worker import Worker

from activities import (
    analyze_sentiment,
    classify_ticket,
    draft_response,
    fetch_order_details,
    review_and_refine,
    send_response,
)
from workflows import CustomerSupportTicketWorkflow

TASK_QUEUE = "test-customer-support"


@pytest.fixture
async def env():
    async with await WorkflowEnvironment.start_local() as env:
        yield env


@pytest.fixture
async def client(env: WorkflowEnvironment) -> Client:
    return env.client


@pytest.fixture
async def worker(client: Client):
    """Start a worker with all activities registered."""
    w = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[CustomerSupportTicketWorkflow],
        activities=[
            analyze_sentiment,
            classify_ticket,
            fetch_order_details,
            draft_response,
            review_and_refine,
            send_response,
        ],
    )
    async with w:
        yield w
