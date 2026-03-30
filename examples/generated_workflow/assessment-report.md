# Assessment Report: Customer Support Agent

**Source**: `examples/customer_support_agent.py`
**Framework**: LangGraph (`StateGraph`)
**LLM**: GPT-4o (all nodes share a single instance)

## System-Level Verdict: Pure Workflow

This system is **not an agent**. It is a deterministic pipeline built in an agent framework. Every node executes in a fixed sequence, every LLM call has a single predetermined purpose, and the one conditional branch is a simple code-level `if/else`. Removing LangGraph and replacing with plain function calls would produce identical behavior.

## Node Classification

| Node | Classification | LLM? | Evidence |
| --- | --- | --- | --- |
| `analyze_sentiment` | LLM-as-Function | Yes (GPT-4o) | Fixed prompt: "Respond with ONLY the sentiment word". Output stored in state, does not drive routing. Next node hardcoded via `add_edge` (line 180). |
| `classify_ticket` | LLM-as-Function | Yes (GPT-4o) | Fixed prompt with 5 categories and 4 priorities. Structured output format. The `priority` field is later used by `route_by_priority`, but *this node itself* does not control flow. Next node hardcoded (line 181). |
| `fetch_order_details` | Deterministic | No | Regex `ORD-\d+` extraction + `lookup_order()` DB call. No LLM. |
| `draft_response` | LLM-as-Function | Yes (GPT-4o) | Prompt template incorporating context from prior nodes. Generates text. Does not decide next step. |
| `route_by_priority` | Deterministic | No | `if state["priority"] == "urgent"` — pure Python branching. Two branches, both enumerated (lines 183-190). |
| `review_and_refine` | LLM-as-Function | Yes (GPT-4o) | Editing prompt. No tool use, no routing. Next node hardcoded (line 191). |
| `send_response` | Deterministic | No | Calls `send_email()` and `log_ticket_resolution()`. No LLM. |

## Antipatterns Detected

### Antipattern 4: The Pipeline Crew

The graph is a linear pipeline with one branch:

```
START → sentiment → classify → fetch → draft → [branch] → send → END
                                                    ↘ review ↗
```

Every node has exactly one predecessor and one successor. The `add_conditional_edges` on `draft_response` routes via `route_by_priority`, which is a trivial `if/else`. This is a pipeline, not an agent.

### Antipattern 2: The Forced Router (partial)

`analyze_sentiment` uses GPT-4o to pick from 4 words (positive/neutral/frustrated/angry). `classify_ticket` uses GPT-4o for 5 categories and 4 priorities. While these *do* require NLP judgment (not simple regex), GPT-4o is overkill — GPT-4o-mini handles these with equivalent accuracy.

## Cost & Latency Analysis

All 4 LLM calls use GPT-4o. Estimating token counts from prompt lengths:

| Node | Current | Est. Cost/1K runs | Proposed | Est. Cost/1K runs | Savings |
| --- | --- | --- | --- | --- | --- |
| `analyze_sentiment` | 1x GPT-4o (~100 in + ~5 out) | $0.30 | 1x GPT-4o-mini | $0.02 | 94% |
| `classify_ticket` | 1x GPT-4o (~150 in + ~20 out) | $0.58 | 1x GPT-4o-mini | $0.03 | 94% |
| `draft_response` | 1x GPT-4o (~400 in + ~300 out) | $4.00 | 1x GPT-4o-mini | $0.24 | 94% |
| `review_and_refine` | 1x GPT-4o (~500 in + ~300 out) | $4.25 | 1x GPT-4o-mini | $0.25 | 94% |
| `fetch_order_details` | No LLM | $0.00 | No change | $0.00 | — |
| `route_by_priority` | No LLM | $0.00 | No change | $0.00 | — |
| `send_response` | No LLM | $0.00 | No change | $0.00 | — |
| **Total** | **4x GPT-4o** | **$9.13/1K** | **4x GPT-4o-mini** | **$0.54/1K** | **94% (-$8.59/1K)** |

**Latency**: 4 sequential LLM calls on the critical path (3 if urgent). GPT-4o-mini is ~2-3x faster per call. Estimated end-to-end latency reduction: 50-60%.

## Recommendation

Replace the LangGraph agent with a Temporal workflow. All generated code is in the `generated_workflow/` directory. Key benefits:

1. **Durability**: If the worker crashes mid-pipeline, Temporal resumes from the last completed activity.
2. **Observability**: Every activity execution is visible in the Temporal UI with timing, inputs, outputs.
3. **Retry semantics**: Transient LLM API failures are retried automatically. Parse errors (`ValueError`) are not retried.
4. **Cost reduction**: Model downgrade from GPT-4o to GPT-4o-mini saves ~94% on LLM costs.
5. **Simplicity**: The workflow code is shorter and clearer than the LangGraph equivalent — no framework overhead for what is fundamentally a function pipeline.
