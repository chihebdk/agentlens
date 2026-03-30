# Temporal Workflow Generation Patterns

How to translate agent patterns into Temporal workflows using the Python SDK (`temporalio`).

## Project Structure

Always generate the following files:

```
generated_workflow/
├── workflows.py      # Workflow definitions
├── activities.py     # Activity implementations
├── models.py         # Data models (dataclasses for workflow state)
├── worker.py         # Worker bootstrap
├── llm_utils.py      # LLM call helpers (shared by activities that need LLM)
└── README.md         # Migration notes and run instructions
```

## Core Mapping Rules

### Agent Node → Temporal Activity

Every node from the execution graph becomes a Temporal Activity. The activity type depends on the node classification.

#### Deterministic Node → Simple Activity

```python
from temporalio import activity
from dataclasses import dataclass

@dataclass
class FetchDataInput:
    url: str
    headers: dict

@dataclass
class FetchDataOutput:
    status_code: int
    body: str

@activity.defn
async def fetch_data(input: FetchDataInput) -> FetchDataOutput:
    async with aiohttp.ClientSession() as session:
        async with session.get(input.url, headers=input.headers) as resp:
            body = await resp.text()
            return FetchDataOutput(status_code=resp.status, body=body)
```

#### LLM-as-Function Node → Activity with LLM Call

The LLM call is inside the activity, but the activity is invoked deterministically by the workflow.

```python
@dataclass
class SummarizeInput:
    document: str
    max_length: int = 200

@dataclass
class SummarizeOutput:
    summary: str

@activity.defn
async def summarize_document(input: SummarizeInput) -> SummarizeOutput:
    """LLM-as-Function: deterministic position in workflow, LLM does the work."""
    response = await llm_client.messages.create(
        model="claude-haiku-4-5-20251001",  # Use cheapest model sufficient for task
        max_tokens=input.max_length,
        messages=[{
            "role": "user",
            "content": f"Summarize this document in under {input.max_length} words:\n\n{input.document}"
        }]
    )
    return SummarizeOutput(summary=response.content[0].text)
```

#### LLM-as-Router Node → Activity that Returns a Route

The activity returns a classification/route value. The workflow uses it for branching.

```python
from enum import Enum

class DocumentType(str, Enum):
    INVOICE = "invoice"
    CONTRACT = "contract"
    REPORT = "report"
    UNKNOWN = "unknown"

@dataclass
class ClassifyInput:
    document_text: str

@dataclass
class ClassifyOutput:
    doc_type: DocumentType
    confidence: float

@activity.defn
async def classify_document(input: ClassifyInput) -> ClassifyOutput:
    """LLM-as-Router: returns classification, workflow decides the branch."""
    response = await llm_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[{
            "role": "user",
            "content": f"Classify this document as one of: invoice, contract, report, unknown.\n\nDocument:\n{input.document_text}\n\nRespond with JSON: {{\"type\": \"...\", \"confidence\": 0.0-1.0}}"
        }]
    )
    result = json.loads(response.content[0].text)
    return ClassifyOutput(
        doc_type=DocumentType(result["type"]),
        confidence=result["confidence"]
    )
```

#### Genuinely Agentic Node → Activity with Extended Timeout

When keeping an agentic node in a hybrid workflow, wrap it as an activity with appropriate timeouts and heartbeating.

```python
@activity.defn
async def run_research_agent(input: ResearchInput) -> ResearchOutput:
    """AGENTIC NODE: This activity wraps genuine agent logic.
    The agent controls its own execution flow internally.
    Extended timeout and heartbeating required."""
    
    agent = create_research_agent(tools=input.tools)
    
    # Heartbeat during long-running agent execution
    result = None
    async for step in agent.run_stream(input.query):
        activity.heartbeat(f"Agent step: {step.action}")
        if step.is_final:
            result = step.output
    
    return ResearchOutput(findings=result)
```

## Workflow Patterns

### Pattern 1: Linear Pipeline (replaces sequential agent chain)

```python
from temporalio import workflow
from datetime import timedelta

@workflow.defn
class DocumentProcessingWorkflow:
    """Replaces: Sequential CrewAI crew or LangGraph chain."""
    
    @workflow.run
    async def run(self, input: DocumentInput) -> ProcessingOutput:
        # Step 1: Extract text (Deterministic)
        extracted = await workflow.execute_activity(
            extract_text,
            ExtractInput(file_path=input.file_path),
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        # Step 2: Classify document (LLM-as-Router)
        classification = await workflow.execute_activity(
            classify_document,
            ClassifyInput(document_text=extracted.text),
            start_to_close_timeout=timedelta(seconds=15),
        )
        
        # Step 3: Summarize (LLM-as-Function)
        summary = await workflow.execute_activity(
            summarize_document,
            SummarizeInput(document=extracted.text),
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        # Step 4: Store results (Deterministic)
        stored = await workflow.execute_activity(
            store_results,
            StoreInput(
                doc_type=classification.doc_type,
                summary=summary.summary,
                original=extracted.text,
            ),
            start_to_close_timeout=timedelta(seconds=10),
        )
        
        return ProcessingOutput(
            doc_type=classification.doc_type,
            summary=summary.summary,
            stored_id=stored.record_id,
        )
```

### Pattern 2: Branching Pipeline (replaces router agent)

```python
@workflow.defn
class CustomerRequestWorkflow:
    """Replaces: Agent that classifies then routes to handler."""
    
    @workflow.run
    async def run(self, input: RequestInput) -> RequestOutput:
        # Route (LLM-as-Router)
        route = await workflow.execute_activity(
            classify_request,
            ClassifyRequestInput(message=input.message),
            start_to_close_timeout=timedelta(seconds=15),
        )
        
        # Branch based on classification (deterministic switch)
        if route.category == RequestType.BILLING:
            result = await workflow.execute_activity(
                handle_billing,
                BillingInput(message=input.message, customer_id=input.customer_id),
                start_to_close_timeout=timedelta(seconds=30),
            )
        elif route.category == RequestType.TECHNICAL:
            result = await workflow.execute_activity(
                handle_technical,
                TechnicalInput(message=input.message),
                start_to_close_timeout=timedelta(seconds=30),
            )
        elif route.category == RequestType.GENERAL:
            result = await workflow.execute_activity(
                handle_general,
                GeneralInput(message=input.message),
                start_to_close_timeout=timedelta(seconds=30),
            )
        else:
            result = await workflow.execute_activity(
                handle_escalation,
                EscalationInput(message=input.message, reason="unclassified"),
                start_to_close_timeout=timedelta(seconds=15),
            )
        
        return RequestOutput(response=result.response, category=route.category)
```

### Pattern 3: Parallel Fan-Out (replaces multi-agent parallel execution)

```python
@workflow.defn
class AnalysisWorkflow:
    """Replaces: Multi-agent system where agents analyze in parallel."""
    
    @workflow.run
    async def run(self, input: AnalysisInput) -> AnalysisOutput:
        # Fan out: run analyses in parallel (all LLM-as-Function)
        sentiment_task = workflow.execute_activity(
            analyze_sentiment,
            SentimentInput(text=input.text),
            start_to_close_timeout=timedelta(seconds=20),
        )
        entity_task = workflow.execute_activity(
            extract_entities,
            EntityInput(text=input.text),
            start_to_close_timeout=timedelta(seconds=20),
        )
        topic_task = workflow.execute_activity(
            classify_topics,
            TopicInput(text=input.text),
            start_to_close_timeout=timedelta(seconds=20),
        )
        
        # Fan in: await all handles (Temporal futures are directly awaitable)
        sentiment = await sentiment_task
        entities = await entity_task
        topics = await topic_task
        
        # Synthesize (LLM-as-Function — combines parallel results)
        synthesis = await workflow.execute_activity(
            synthesize_analysis,
            SynthesisInput(
                sentiment=sentiment,
                entities=entities,
                topics=topics,
            ),
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        return AnalysisOutput(report=synthesis.report)
```

### Pattern 4: Hybrid — Deterministic Spine with Agentic Node

```python
@workflow.defn
class ResearchAndReportWorkflow:
    """Hybrid: deterministic pipeline with one genuinely agentic step.
    
    Original: LangGraph with 5 agent nodes.
    After analysis: 4 nodes are LLM-as-Function, 1 is genuinely agentic.
    The agentic node (research) needs open-ended tool use.
    """
    
    @workflow.run
    async def run(self, input: ResearchInput) -> ReportOutput:
        # Step 1: Parse research brief (Deterministic)
        brief = await workflow.execute_activity(
            parse_brief,
            ParseInput(raw_brief=input.brief),
            start_to_close_timeout=timedelta(seconds=10),
        )
        
        # Step 2: Generate search queries (LLM-as-Function)
        queries = await workflow.execute_activity(
            generate_queries,
            QueryGenInput(topic=brief.topic, constraints=brief.constraints),
            start_to_close_timeout=timedelta(seconds=15),
        )
        
        # Step 3: AGENTIC — Research with open-ended tool use
        # This node remains an agent because the research path is unpredictable.
        # Extended timeout, heartbeating enabled.
        research = await workflow.execute_activity(
            run_research_agent,  # Wraps the original agent logic
            AgentResearchInput(queries=queries.queries, tools=["web_search", "arxiv", "scholar"]),
            start_to_close_timeout=timedelta(minutes=10),
            heartbeat_timeout=timedelta(seconds=60),
        )
        
        # Step 4: Synthesize findings (LLM-as-Function)
        synthesis = await workflow.execute_activity(
            synthesize_findings,
            SynthesisInput(findings=research.findings, brief=brief),
            start_to_close_timeout=timedelta(seconds=30),
        )
        
        # Step 5: Format report (Deterministic)
        report = await workflow.execute_activity(
            format_report,
            FormatInput(content=synthesis.content, template=input.template),
            start_to_close_timeout=timedelta(seconds=15),
        )
        
        return ReportOutput(report=report.document)
```

### Pattern 5: Retry with Validation (replaces self-correction agent)

```python
@workflow.defn
class DataExtractionWorkflow:
    """Replaces: Agent that extracts data and retries on validation failure.
    The 'agency' was just retry logic — not genuine decision-making."""
    
    @workflow.run
    async def run(self, input: ExtractionInput) -> ExtractionOutput:
        max_attempts = 3
        last_error = None
        
        for attempt in range(max_attempts):
            # Extract (LLM-as-Function)
            extraction = await workflow.execute_activity(
                extract_structured_data,
                ExtractInput(
                    document=input.document,
                    schema=input.schema,
                    previous_error=last_error,  # Feed back validation error
                ),
                start_to_close_timeout=timedelta(seconds=30),
            )
            
            # Validate (Deterministic)
            validation = await workflow.execute_activity(
                validate_extraction,
                ValidateInput(data=extraction.data, schema=input.schema),
                start_to_close_timeout=timedelta(seconds=5),
            )
            
            if validation.is_valid:
                return ExtractionOutput(data=extraction.data, attempts=attempt + 1)
            
            last_error = validation.error_message
        
        # Max retries exceeded
        return ExtractionOutput(
            data=extraction.data,
            attempts=max_attempts,
            validation_warnings=[last_error],
        )
```

## Worker Bootstrap

Always generate a worker file:

```python
# worker.py
import asyncio
from temporalio.client import Client
from temporalio.worker import Worker

from workflows import (
    DocumentProcessingWorkflow,
    # ... other workflows
)
from activities import (
    extract_text,
    classify_document,
    summarize_document,
    store_results,
    # ... other activities
)

async def main():
    client = await Client.connect("localhost:7233")
    
    worker = Worker(
        client,
        task_queue="document-processing",
        workflows=[DocumentProcessingWorkflow],
        activities=[
            extract_text,
            classify_document,
            summarize_document,
            store_results,
        ],
    )
    
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())
```

## Data Model Guidelines

- Use `@dataclass` for all inputs and outputs — Temporal serializes these
- Keep data models in a separate `models.py` file
- Every activity should have typed input and output dataclasses
- Avoid passing large blobs; use references (IDs, URLs) for big data
- Make fields JSON-serializable (no complex objects, datetimes as ISO strings)

## Timeout Guidelines

| Node Type | start_to_close_timeout | heartbeat_timeout |
| --- | --- | --- |
| Deterministic (fast) | 10-30s | Not needed |
| Deterministic (API call) | 30-60s | Not needed |
| LLM-as-Function | 15-60s (depends on model/prompt) | Not needed |
| LLM-as-Router | 10-30s | Not needed |
| Agentic node | 5-15 minutes | 30-60s |

## Retry Policies

```python
from temporalio.common import RetryPolicy

# For deterministic activities — standard retry
DETERMINISTIC_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_attempts=3,
)

# For LLM activities — retry on transient API errors, not on bad output
LLM_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_attempts=3,
    non_retryable_error_types=["ValueError"],  # Don't retry on parse errors
)

# For agentic activities — limited retry, the agent handles its own errors
AGENT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    maximum_attempts=2,
)
```

## Pattern 6: Saga with Compensation (replaces agent rollback logic)

Many agent pipelines perform multi-step operations where failure in a later step should undo earlier steps (e.g., "create account → provision resources → send welcome email" — if email fails, deprovision and delete account). Agents typically handle this ad-hoc or not at all. Temporal Sagas make this explicit and reliable.

```python
@workflow.defn
class ProvisioningWorkflow:
    """Replaces: Agent that creates resources and tries to clean up on failure.
    Saga pattern ensures compensating actions run even if the worker crashes."""

    @workflow.run
    async def run(self, input: ProvisionInput) -> ProvisionOutput:
        compensations: list[tuple[any, any]] = []  # (activity, input) pairs

        try:
            # Step 1: Create account (Deterministic)
            account = await workflow.execute_activity(
                create_account,
                CreateAccountInput(name=input.name, email=input.email),
                start_to_close_timeout=timedelta(seconds=30),
            )
            compensations.append((delete_account, DeleteAccountInput(account_id=account.id)))

            # Step 2: Provision resources (Deterministic)
            resources = await workflow.execute_activity(
                provision_resources,
                ProvisionResourcesInput(account_id=account.id, plan=input.plan),
                start_to_close_timeout=timedelta(seconds=60),
            )
            compensations.append((deprovision_resources, DeprovisionInput(resource_ids=resources.ids)))

            # Step 3: Send welcome email (Deterministic)
            await workflow.execute_activity(
                send_welcome_email,
                EmailInput(email=input.email, account_id=account.id),
                start_to_close_timeout=timedelta(seconds=15),
            )

            return ProvisionOutput(account_id=account.id, status="success")

        except Exception as e:
            # Compensate in reverse order — Temporal guarantees this runs
            for comp_activity, comp_input in reversed(compensations):
                try:
                    await workflow.execute_activity(
                        comp_activity,
                        comp_input,
                        start_to_close_timeout=timedelta(seconds=30),
                    )
                except Exception as comp_error:
                    workflow.logger.error(
                        f"Compensation failed: {comp_activity.__name__}: {comp_error}"
                    )
            raise  # Re-raise after compensation
```

**When to use**: Any agent pipeline that creates external side effects (database records, cloud resources, API calls to third parties, financial transactions) where partial completion is worse than full rollback.

## Pattern 7: Signals and Queries (replaces HITL and status polling)

Temporal Signals allow external input to a running workflow (human approvals, external events). Queries allow reading workflow state without affecting execution (status dashboards, progress checks).

### Signal: Human Approval Gate

```python
@workflow.defn
class ApprovalWorkflow:
    """Replaces: Agent that polls for human approval or blocks on a queue.
    The workflow durably waits — even across worker restarts."""

    def __init__(self):
        self._approved: bool | None = None
        self._approver: str = ""
        self._review_notes: str = ""

    @workflow.signal
    async def approve(self, approver: str, notes: str = "") -> None:
        self._approved = True
        self._approver = approver
        self._review_notes = notes

    @workflow.signal
    async def reject(self, approver: str, reason: str) -> None:
        self._approved = False
        self._approver = approver
        self._review_notes = reason

    @workflow.query
    def get_status(self) -> dict:
        """Query: check workflow state without affecting execution."""
        return {
            "approved": self._approved,
            "approver": self._approver,
            "notes": self._review_notes,
        }

    @workflow.run
    async def run(self, input: ReviewInput) -> ReviewOutput:
        # Step 1: Generate content (LLM-as-Function)
        content = await workflow.execute_activity(
            generate_content,
            GenerateInput(brief=input.brief),
            start_to_close_timeout=timedelta(seconds=60),
        )

        # Step 2: Notify reviewer (Deterministic)
        await workflow.execute_activity(
            notify_reviewer,
            NotifyInput(reviewer=input.reviewer, content_id=content.id),
            start_to_close_timeout=timedelta(seconds=15),
        )

        # Step 3: Wait for human signal — durable wait, survives crashes
        await workflow.wait_condition(lambda: self._approved is not None)

        if not self._approved:
            return ReviewOutput(status="rejected", reason=self._review_notes)

        # Step 4: Publish (Deterministic)
        published = await workflow.execute_activity(
            publish_content,
            PublishInput(content_id=content.id),
            start_to_close_timeout=timedelta(seconds=30),
        )

        return ReviewOutput(status="published", url=published.url)
```

### Signal: External Event Mid-Workflow

```python
@workflow.defn
class DataPipelineWorkflow:
    """Workflow that waits for an external system to signal data readiness."""

    def __init__(self):
        self._data_ready = False
        self._data_location: str = ""

    @workflow.signal
    async def data_available(self, location: str) -> None:
        self._data_ready = True
        self._data_location = location

    @workflow.query
    def progress(self) -> str:
        if not self._data_ready:
            return "waiting_for_data"
        return "processing"

    @workflow.run
    async def run(self, input: PipelineInput) -> PipelineOutput:
        # Step 1: Request data preparation (Deterministic)
        await workflow.execute_activity(
            request_data_prep,
            DataPrepInput(source=input.source),
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Step 2: Wait for external signal with timeout
        try:
            await workflow.wait_condition(
                lambda: self._data_ready,
                timeout=timedelta(hours=24),
            )
        except asyncio.TimeoutError:
            return PipelineOutput(status="timeout", error="Data not received within 24h")

        # Step 3: Process data (LLM-as-Function or Deterministic)
        result = await workflow.execute_activity(
            process_data,
            ProcessInput(location=self._data_location),
            start_to_close_timeout=timedelta(minutes=5),
        )

        return PipelineOutput(status="complete", result=result.output)
```

### Query: Progress Monitoring

```python
# Client-side: query workflow progress (replaces agent "status" endpoints)
async def check_progress(workflow_id: str) -> dict:
    client = await Client.connect("localhost:7233")
    handle = client.get_workflow_handle(workflow_id)
    status = await handle.query(DataPipelineWorkflow.progress)
    return {"workflow_id": workflow_id, "status": status}
```

## Streaming Guidance

Temporal does not natively support streaming activity results back to callers. This matters when converting agents that stream LLM responses to users in real-time.

### Approaches for Streaming in Temporal Workflows

#### Option 1: Queries for Progress Polling (simplest)

Use `@workflow.query` to expose intermediate state. The client polls at an interval.

```python
@workflow.defn
class StreamingWorkflow:
    def __init__(self):
        self._partial_result: str = ""
        self._is_complete: bool = False

    @workflow.query
    def get_partial_result(self) -> dict:
        return {"result": self._partial_result, "complete": self._is_complete}

    @workflow.run
    async def run(self, input: StreamInput) -> StreamOutput:
        # Activity produces result; workflow stores it for queries
        result = await workflow.execute_activity(
            generate_with_llm,
            LLMInput(prompt=input.prompt),
            start_to_close_timeout=timedelta(seconds=60),
        )
        self._partial_result = result.text
        self._is_complete = True
        return StreamOutput(text=result.text)
```

#### Option 2: Thin Streaming Wrapper (recommended for UX-sensitive apps)

Keep Temporal for orchestration and durability, but add a thin WebSocket/SSE layer outside the workflow for streaming the LLM response directly to the user. The workflow still tracks state and handles retries.

```python
# The workflow triggers the LLM activity and stores the result.
# A separate FastAPI/WebSocket service streams the LLM response directly.
# The two are connected via a shared message bus (Redis, NATS, etc.)

# In the activity:
@activity.defn
async def generate_and_stream(input: StreamInput) -> StreamOutput:
    """Streams to the user via side-channel, returns final result to workflow."""
    channel = redis.pubsub_channel(f"stream:{input.request_id}")

    full_response = ""
    async for chunk in llm_client.messages.stream(input.prompt):
        full_response += chunk.text
        await channel.publish(chunk.text)  # Real-time to client

    return StreamOutput(text=full_response)  # Durable to workflow
```

#### Option 3: Skip Temporal for the Streaming Step

If only one step needs streaming and it's a simple LLM call, consider keeping that step outside Temporal and only wrapping the durable orchestration logic in the workflow.

### When to Use Each

| Scenario | Approach |
| --- | --- |
| Internal pipeline, no user-facing output | Option 1 (query) or no streaming needed |
| User-facing chat/response, needs real-time | Option 2 (side-channel) |
| Single LLM call with streaming, minimal orchestration | Option 3 (skip Temporal for that step) |

## Testing Generated Workflows

Always generate tests alongside the workflow code. Use Temporal's test framework for deterministic, fast tests that don't require a running Temporal server.

### Target SDK Version

Generate code targeting `temporalio >= 1.7.0` (Python SDK). Specify this in the generated `requirements.txt`:

```txt
temporalio>=1.7.0
```

### Project Structure (updated)

```txt
generated_workflow/
├── workflows.py        # Workflow definitions
├── activities.py       # Activity implementations
├── models.py           # Data models (dataclasses for workflow state)
├── worker.py           # Worker bootstrap
├── llm_utils.py        # LLM call helpers (shared by activities that need LLM)
├── tests/
│   ├── test_workflows.py   # Workflow integration tests
│   ├── test_activities.py  # Unit tests for activities
│   └── conftest.py         # Test fixtures
├── requirements.txt    # Dependencies
└── README.md           # Migration notes and run instructions
```

### Workflow Integration Test Template

```python
import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from temporalio.client import Client

from workflows import DocumentProcessingWorkflow
from activities import extract_text, classify_document, summarize_document, store_results
from models import DocumentInput, ProcessingOutput


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
    worker = Worker(
        client,
        task_queue="test-queue",
        workflows=[DocumentProcessingWorkflow],
        activities=[extract_text, classify_document, summarize_document, store_results],
    )
    async with worker:
        yield worker


@pytest.mark.asyncio
async def test_document_processing_end_to_end(client: Client, worker):
    """Test that the workflow produces the same output as the original agent."""
    input_data = DocumentInput(file_path="test_data/sample_invoice.pdf")

    result = await client.execute_workflow(
        DocumentProcessingWorkflow.run,
        input_data,
        id="test-doc-processing-1",
        task_queue="test-queue",
    )

    assert isinstance(result, ProcessingOutput)
    assert result.doc_type is not None
    assert result.summary != ""
    assert result.stored_id is not None
```

### Activity Unit Test Template

```python
import pytest
from unittest.mock import AsyncMock, patch
from temporalio.testing import ActivityEnvironment

from activities import classify_document, summarize_document
from models import ClassifyInput, ClassifyOutput, SummarizeInput, SummarizeOutput


@pytest.fixture
def activity_env():
    return ActivityEnvironment()


@pytest.mark.asyncio
async def test_classify_document(activity_env: ActivityEnvironment):
    """Test classification activity in isolation."""
    with patch("activities.llm_client") as mock_llm:
        mock_llm.messages.create = AsyncMock(return_value=MockResponse(
            text='{"type": "invoice", "confidence": 0.95}'
        ))

        result = await activity_env.run(
            classify_document,
            ClassifyInput(document_text="Invoice #12345 — Amount Due: $500"),
        )

        assert result.doc_type == DocumentType.INVOICE
        assert result.confidence >= 0.9


@pytest.mark.asyncio
async def test_summarize_document(activity_env: ActivityEnvironment):
    """Test summarization activity in isolation."""
    with patch("activities.llm_client") as mock_llm:
        mock_llm.messages.create = AsyncMock(return_value=MockResponse(
            text="This is a summary of the document."
        ))

        result = await activity_env.run(
            summarize_document,
            SummarizeInput(document="A very long document...", max_length=200),
        )

        assert len(result.summary) > 0
        assert len(result.summary.split()) <= 200
```

### Equivalence Testing: Agent vs. Workflow

The most critical test is verifying that the generated workflow produces equivalent outputs to the original agent. Generate an equivalence test:

```python
@pytest.mark.asyncio
async def test_equivalence_with_original_agent(client: Client, worker):
    """Verify the Temporal workflow produces the same results as the original agent.

    Run this with real LLM calls (not mocked) on a set of representative inputs.
    Due to LLM non-determinism, compare structure and key fields, not exact text.
    """
    test_cases = [
        DocumentInput(file_path="test_data/invoice.pdf"),
        DocumentInput(file_path="test_data/contract.pdf"),
        DocumentInput(file_path="test_data/report.pdf"),
    ]

    for test_input in test_cases:
        # Run original agent
        agent_result = await run_original_agent(test_input)

        # Run Temporal workflow
        workflow_result = await client.execute_workflow(
            DocumentProcessingWorkflow.run,
            test_input,
            id=f"equiv-test-{test_input.file_path}",
            task_queue="test-queue",
        )

        # Compare structure (not exact text — LLM outputs vary)
        assert workflow_result.doc_type == agent_result.doc_type, (
            f"Classification mismatch for {test_input.file_path}: "
            f"workflow={workflow_result.doc_type}, agent={agent_result.doc_type}"
        )
        assert workflow_result.summary is not None
        assert workflow_result.stored_id is not None
```
