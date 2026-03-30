---
name: convert
description: "Generate Temporal workflow code from a previously assessed agent codebase. Reads an existing assessment-report.md and execution-graph.md (produced by /agentlens:assess) and generates the full replacement architecture: workflows, activities, models, worker, tests. Use when the user wants to convert an assessed agent to Temporal, or asks to generate the workflow code."
allowed-tools: Read, Grep, Glob, Write, Edit, Bash
disable-model-invocation: true
---

# Convert Agent to Temporal Workflow

Generate Temporal workflow code based on a completed assessment. This skill reads the output of `/agentlens:assess` and produces a full Temporal replacement.

## Prerequisites

This skill requires a prior assessment. Look for these files in the current working directory:

1. **`assessment-report.md`** — contains the system verdict and node classification table
2. **`execution-graph.md`** — contains the structural map and state schema

If these files do not exist, ask the user to run `/agentlens:assess` first, or point to where the assessment output was saved.

Read both files and extract:
- The **system verdict**: Pure Workflow, Hybrid, or Genuinely Agentic
- The **node classification table**: each node's name, classification, LLM usage, and connections
- The **state schema**: data flowing between nodes

## Architecture Generation

Read [temporal-patterns.md](../../references/temporal-patterns.md) for code generation patterns, then generate based on the verdict.

### For Pure Workflow Verdict

Generate a complete Temporal workflow replacement:

- Each original node becomes a Temporal Activity
- LLM-as-Function nodes become activities that call the LLM with a fixed prompt
- LLM-as-Router nodes become activities whose return value drives workflow branching
- Deterministic nodes become simple activities with no LLM
- Preserve all error handling, retry logic, and timeout semantics
- Apply model downgrades where appropriate (see cost analysis in the assessment report)
- Generate the worker, workflow, and activity files separately

### For Hybrid Verdict

Generate the Temporal workflow for the deterministic spine:

- Deterministic and LLM-as-Function nodes become standard Temporal Activities
- Agentic nodes become Temporal Activities with extended timeouts and heartbeating
- The activity wraps the original agent logic (or a simplified version)
- Clearly mark which activities are deterministic vs. agentic in comments
- Generate a diagram showing the workflow with agentic nodes highlighted

### For Genuinely Agentic Verdict

Do NOT generate a full workflow replacement — the agency is justified. Instead:

- **Wrap in Temporal for durability**: Offer to wrap the entire agent as a Temporal Activity within a thin workflow. This gives durability, observability, and retry semantics without removing agency.
- **Add guardrails**: Generate a configuration module with:
  - Max iteration limits (prevent runaway loops)
  - Cost budget caps (total LLM spend per execution)
  - Timeout circuits (hard kill after N minutes)
  - Token usage tracking per step
- **Propose decomposition**: Analyze whether the agentic system can be split so that some sub-tasks become deterministic workflows.
- **Identify optimization opportunities**:
  - Nodes that could be pre-computed or cached
  - LLM calls that could use a smaller/cheaper model (model downgrade map)
  - Tool calls that could be parallelized
  - Context that could be trimmed (token savings estimate)
  - Intermediate results that could be persisted to avoid re-computation on retry
- **Generate a monitoring plan**: Suggest what to track — tool call frequency distribution, iteration counts per run, cost per execution, latency percentiles, failure modes.

## Output Structure

Always produce these files:

```txt
generated_workflow/
├── workflows.py        # Workflow definitions
├── activities.py       # Activity implementations
├── models.py           # Data models (dataclasses for workflow state)
├── worker.py           # Worker bootstrap
├── llm_utils.py        # LLM call helpers (shared by activities that need LLM)
├── tests/
│   ├── conftest.py         # Test fixtures
│   ├── test_workflows.py   # Workflow integration tests
│   └── test_activities.py  # Unit tests for activities
├── requirements.txt    # Dependencies (temporalio>=1.7.0)
└── migration-notes.md  # What changed, how to run, testing checklist
```

## Code Generation Standards

Follow these rules from the temporal patterns reference:

- Use `@dataclass` for all activity inputs and outputs — Temporal serializes these
- Keep data models in a separate `models.py` file
- Every activity must have typed input and output dataclasses
- Avoid passing large blobs; use references (IDs, URLs) for big data
- Make fields JSON-serializable (no complex objects, datetimes as ISO strings)
- Target `temporalio >= 1.7.0` (Python SDK)

### Timeout Guidelines

| Node Type | start_to_close_timeout | heartbeat_timeout |
| --- | --- | --- |
| Deterministic (fast) | 10-30s | Not needed |
| Deterministic (API call) | 30-60s | Not needed |
| LLM-as-Function | 15-60s | Not needed |
| LLM-as-Router | 10-30s | Not needed |
| Agentic node | 5-15 minutes | 30-60s |

### Retry Policies

- **Deterministic**: standard retry (3 attempts, 1s initial, 2x backoff)
- **LLM calls**: retry transient API errors, NOT parse errors (`non_retryable_error_types=["ValueError"]`)
- **Agentic**: limited retry (2 attempts), the agent handles its own errors

### Testing

Always generate tests alongside the workflow code:
- **Integration tests**: use `WorkflowEnvironment.start_local()` — no running Temporal server needed
- **Activity unit tests**: use `ActivityEnvironment` with mocked LLM clients
- **Equivalence tests**: template for comparing workflow output vs original agent output
