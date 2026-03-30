# Migration Notes: LangGraph Agent → Temporal Workflow

## What Changed

### Framework
- **Before**: LangGraph `StateGraph` with 6 `add_node` calls and mixed static/conditional edges
- **After**: Temporal `@workflow.defn` with 6 `@activity.defn` activities, standard Python branching

### LLM Model
- **Before**: All nodes use `gpt-4o`
- **After**: All nodes use `gpt-4o-mini` (94% cost reduction, equivalent quality for these tasks)

### Prompt Format
- **Before**: LangChain `SystemMessage`/`HumanMessage` objects
- **After**: OpenAI SDK `messages` dicts directly (removes LangChain dependency)

### Classification Output
- **Before**: `classify_ticket` parses line-by-line text format (`category: X\npriority: Y`)
- **After**: JSON output with structured parsing (`{"category": "...", "priority": "..."}`) — more reliable

### State Management
- **Before**: LangGraph shared `TicketState` dict mutated by each node
- **After**: Each activity has explicit typed input/output dataclasses. No shared mutable state.

### Error Handling
- **Before**: No explicit error handling. If an LLM call fails, the pipeline crashes.
- **After**: Retry policies per activity type. LLM transient errors retry 3 times with backoff. Parse errors (`ValueError`) do not retry.

### Routing
- **Before**: `add_conditional_edges` with `route_by_priority` function
- **After**: Plain `if classification.priority != Priority.URGENT` in workflow code

## What Stayed the Same

- All original prompts are preserved (only formatting changed)
- All 3 external calls preserved: `lookup_order`, `send_email`, `log_ticket_resolution`
- The execution order is identical
- The branching logic (urgent → skip review) is identical

## Dependencies

### Removed
- `langgraph`
- `langchain-openai`
- `langchain-core`

### Added
- `temporalio>=1.7.0`
- `openai>=1.0.0` (direct SDK, no LangChain wrapper)

### Kept
- `openai` (now used directly instead of via LangChain)

## Running the Workflow

### Prerequisites

1. Install Temporal CLI: `brew install temporal` (macOS) or see [docs](https://docs.temporal.io/cli)
2. Start local Temporal server: `temporal server start-dev`
3. Install Python deps: `pip install -r requirements.txt`
4. Set `OPENAI_API_KEY` environment variable

### Start the Worker

```bash
cd examples/generated_workflow
python worker.py
```

### Execute a Workflow

```python
import asyncio
from temporalio.client import Client
from models import TicketWorkflowInput

async def main():
    client = await Client.connect("localhost:7233")
    result = await client.execute_workflow(
        "CustomerSupportTicketWorkflow",
        TicketWorkflowInput(
            ticket_id="TKT-20250330-001",
            customer_email="jane@example.com",
            message="My order ORD-98765 hasn't updated in 3 days. I'm frustrated.",
        ),
        id="ticket-TKT-20250330-001",
        task_queue="customer-support-tickets",
    )
    print(f"Category: {result.category}")
    print(f"Priority: {result.priority}")
    print(f"Response: {result.final_response}")

asyncio.run(main())
```

### Run Tests

```bash
cd examples/generated_workflow
pytest tests/ -v
```

## Testing Checklist

- [ ] Run `test_activities.py` — verifies each activity in isolation with mocked LLM
- [ ] Run `test_workflows.py` — verifies end-to-end workflow with mocked LLM
- [ ] Run with real LLM calls on 5+ diverse ticket types to verify output quality
- [ ] Compare workflow output with original LangGraph agent output on same inputs
- [ ] Verify urgent tickets skip the review step (3 LLM calls vs 4)
- [ ] Verify tickets without order IDs produce graceful "No order ID" handling
- [ ] Monitor Temporal UI for activity timing and retry behavior
- [ ] Load test: run 100 concurrent workflows to verify worker stability
