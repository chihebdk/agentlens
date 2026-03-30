"""Temporal worker for the Customer Support Ticket workflow.

Run with: python worker.py

Requires a running Temporal server (localhost:7233 by default).
Start one with: temporal server start-dev
"""

import asyncio

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

TASK_QUEUE = "customer-support-tickets"


async def main():
    client = await Client.connect("localhost:7233")

    worker = Worker(
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

    print(f"Worker started, listening on task queue: {TASK_QUEUE}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
