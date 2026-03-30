"""Temporal workflow for Customer Support Ticket processing.

Replaces: LangGraph StateGraph from examples/customer_support_agent.py
Verdict: Pure Workflow — no genuine agency detected.
Pattern: Branching Pipeline (Pattern 2 from temporal-patterns.md)

The original LangGraph agent had 6 nodes connected by static edges with
one conditional branch (route_by_priority). All LLM calls were
LLM-as-Function. This Temporal workflow preserves identical behavior
with added durability, retry semantics, and observability.
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
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
        TicketWorkflowInput,
        TicketWorkflowOutput,
    )


# ── Retry Policies ───────────────────────────────────────────────────────────

DETERMINISTIC_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_attempts=3,
)

LLM_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_attempts=3,
    non_retryable_error_types=["ValueError"],
)


# ── Workflow ─────────────────────────────────────────────────────────────────


@workflow.defn
class CustomerSupportTicketWorkflow:
    """Process a customer support ticket: analyze, classify, draft, review, send.

    Replaces the LangGraph agent with a deterministic Temporal workflow.

    Flow:
        START
         → analyze_sentiment  (LLM-as-Function)
         → classify_ticket    (LLM-as-Function)
         → fetch_order_details (Deterministic)
         → draft_response     (LLM-as-Function)
         → [if priority != urgent] review_and_refine (LLM-as-Function)
         → send_response      (Deterministic)
        END
    """

    @workflow.run
    async def run(self, input: TicketWorkflowInput) -> TicketWorkflowOutput:
        # Step 1: Analyze sentiment (LLM-as-Function)
        sentiment_result = await workflow.execute_activity(
            analyze_sentiment,
            AnalyzeSentimentInput(message=input.message),
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=LLM_RETRY,
        )

        # Step 2: Classify ticket (LLM-as-Function)
        classification = await workflow.execute_activity(
            classify_ticket,
            ClassifyTicketInput(message=input.message),
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=LLM_RETRY,
        )

        # Step 3: Fetch order details (Deterministic)
        order_result = await workflow.execute_activity(
            fetch_order_details,
            FetchOrderInput(message=input.message),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DETERMINISTIC_RETRY,
        )

        # Step 4: Draft response (LLM-as-Function)
        draft = await workflow.execute_activity(
            draft_response,
            DraftResponseInput(
                message=input.message,
                category=classification.category.value,
                priority=classification.priority.value,
                sentiment=sentiment_result.sentiment.value,
                order_info=order_result.order_info,
            ),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=LLM_RETRY,
        )

        # Step 5: Route by priority (Deterministic — code logic, not LLM)
        # Urgent tickets skip review and go straight to send.
        response_text = draft.draft_response
        if classification.priority != Priority.URGENT:
            # Step 5a: Review and refine (LLM-as-Function)
            refined = await workflow.execute_activity(
                review_and_refine,
                ReviewRefineInput(
                    message=input.message,
                    draft_response=draft.draft_response,
                ),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=LLM_RETRY,
            )
            response_text = refined.final_response

        # Step 6: Send response (Deterministic)
        send_result = await workflow.execute_activity(
            send_response,
            SendResponseInput(
                ticket_id=input.ticket_id,
                customer_email=input.customer_email,
                category=classification.category.value,
                response_text=response_text,
            ),
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=DETERMINISTIC_RETRY,
        )

        return TicketWorkflowOutput(
            ticket_id=input.ticket_id,
            category=classification.category.value,
            priority=classification.priority.value,
            sentiment=sentiment_result.sentiment.value,
            final_response=send_result.final_response,
        )
