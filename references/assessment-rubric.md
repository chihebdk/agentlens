# Assessment Rubric

Detailed criteria for classifying agent nodes and identifying antipatterns.

## Node Classification Decision Tree

For each node in the execution graph, walk through these questions in order:

### Question 1: Does this node involve an LLM call?

- **No** → Classification: **Deterministic**. Stop here.
- **Yes** → Continue to Question 2.

### Question 2: Does the LLM output determine which node executes next?

- **No** — The LLM produces a value (summary, extraction, generation) but the next step is hardcoded in the graph. → Classification: **LLM-as-Function**. Stop here.
- **Yes** → Continue to Question 3.

### Question 3: Are the possible next steps enumerated at design time?

Look at the code. Is there a fixed set of branches the LLM can route to?

- **Yes** — The LLM's output is mapped to one of N known paths (even if N is large). The branching logic is `if/elif/else`, a dictionary lookup, or a structured enum. → Classification: **LLM-as-Router**. Stop here.
- **No** — The LLM generates the next action dynamically (e.g., picks from a tool list, generates a plan, or decides whether to continue). → Continue to Question 4.

### Question 4: Is the LLM's action space genuinely open-ended?

- **The LLM selects from tools AND decides iteration count**: It can call different tools in different orders, and it decides when the task is complete. → Classification: **Genuinely Agentic**.
- **The LLM selects from tools BUT iteration is bounded and small** (e.g., always exactly 1 tool call, or max 2 retries): This is closer to a router with tool execution. → Classification: **LLM-as-Router** (with a note about the tool call pattern).
- **The LLM generates a plan then executes it step by step**: If the plan itself is dynamic and revised during execution → **Genuinely Agentic**. If the plan is generated once and then executed linearly → **LLM-as-Function** (the planning step) + **Deterministic** (the execution steps).

### Question 5: Does the node involve Human-in-the-Loop (HITL)?

Apply this question as a modifier to any node that pauses for human input:

- **Human approval gate**: The system pauses for a human to approve/reject before continuing. The human does not change the execution path — they only gate it. → The node itself is **Deterministic** (it's a wait + pass-through). The surrounding flow determines the overall classification. This maps cleanly to a Temporal Signal (see `temporal-patterns.md`).
- **Human provides input that drives routing**: The system pauses for a human to make a decision (e.g., "approve", "reject", "escalate"). The human's choice selects the next branch from a known set. → Classification: **Deterministic Router** (human replaces LLM as the decision-maker). Even simpler than LLM-as-Router — a Temporal Signal + switch/case.
- **Human provides open-ended feedback mid-loop**: The system pauses, a human provides free-text feedback, and the agent incorporates it into subsequent iterations. → The HITL step itself is Deterministic, but the agent loop around it may still be **Genuinely Agentic**. Classify the loop, not the wait.
- **Key insight**: HITL does not make a system more agentic — it makes it *less* agentic. A human gate is deterministic. If the only source of "unpredictability" in a system is human input, the system is a workflow with human tasks, not an agent.

## System-Level Classification

After classifying every node, determine the system-level verdict:

### Pure Workflow Indicators (strong signals)

- All control flow edges are static (hardcoded in the graph definition)
- Every LLM call has a single, specific purpose (summarize, extract, classify)
- The number of steps is fixed or bounded by a small constant
- Nodes execute in a predictable sequence (possibly with branches, but branches are predefined)
- State is passed between nodes in a structured, typed format
- The system would work identically if you replaced LLM calls with lookup tables (assuming perfect classification)

### Hybrid Indicators

- The overall pipeline has a clear beginning, middle, and end with known phases
- Most transitions between phases are deterministic
- But one or more phases contain genuine agency: open-ended tool use, iterative refinement, self-correction loops
- Example: Ingest → Classify → [Agent: research and answer] → Format → Deliver
- Example: Parse → Extract → [Agent: resolve ambiguities] → Validate → Store

### Genuinely Agentic Indicators

- The top-level loop is "observe → think → act → repeat until done"
- The system has no predetermined sequence of steps
- The LLM can dynamically invoke any combination of tools
- The number of iterations is unpredictable and depends on the task
- The system handles open-ended user requests where the path to completion is unknown

## Common Antipatterns

Flag these when found — they are strong signals of over-agentification:

### Antipattern 1: The Single-Path Agent
An "agent" that always calls the same tools in the same order. The ReAct loop exists but in practice never deviates from a fixed sequence.

**Evidence**: Look at logs/traces if available. If the tool call sequence is identical across diverse inputs, it is a workflow pretending to be an agent.

**Code signals**:
- System prompt that says "First do X, then do Y, then do Z"
- Tool list with 2-3 tools that form an obvious pipeline
- No conditional logic in the agent's decision-making

### Antipattern 2: The Forced Router
An LLM used to route between options that could be determined by simple rules, regex, or keyword matching.

**Evidence**: The routing prompt asks the LLM to classify based on obvious signals (file extension, presence of a keyword, numeric threshold).

**Code signals**:
- Routing prompt with very specific, non-ambiguous categories
- Categories that map 1:1 to structured fields in the input
- No nuance or judgment required in the classification

### Antipattern 3: The Chatbot Agent
A system that wraps a single LLM call in an agent framework. One prompt, one response, no tool use, no iteration. The "agent" is just a prompt template with extra infrastructure.

**Evidence**: Single node in the graph that does one LLM call and returns.

### Antipattern 4: The Pipeline Crew
A multi-agent system where agents execute in a fixed sequence, each doing one thing, passing output to the next. No dynamic routing, no parallel execution, no inter-agent negotiation.

**Evidence**:
- Sequential execution with no branching
- Each agent has exactly one predecessor and one successor
- Removing the agent framework and replacing with function calls would produce identical results

### Antipattern 5: The Overthought Retry
An agent loop that exists solely to retry on failure. The "agency" is just error handling dressed up as autonomous behavior.

**Evidence**:
- Loop condition is "did the last step succeed?"
- On failure, the agent retries the same action (possibly with a modified prompt)
- No alternative strategies or tool switching on failure

### Antipattern 6: The Planning Theater
An LLM generates a "plan" that is then executed step-by-step, but the plan is never revised, never adapts to intermediate results, and the steps are predictable from the input.

**Evidence**:
- Plan is generated once and never updated
- Plan steps map directly to a known set of functions
- The "planning" prompt constrains the output to a fixed schema that mirrors the existing pipeline

## Cost & Latency Impact Assessment

For each node classified as **not genuinely agentic**, estimate:

1. **LLM calls eliminated**: How many LLM calls can be removed entirely (replaced by code logic)?
2. **LLM calls downgraded**: How many can use a smaller/cheaper model (e.g., Haiku instead of Opus for simple classification)?
3. **Latency reduction**: Which LLM calls are on the critical path? Removing them directly reduces end-to-end latency.
4. **Reliability improvement**: Each LLM call is a point of non-determinism. Fewer calls = more predictable behavior.

### Reference Pricing (per 1M tokens, as of early 2025 — verify current rates)

Use these to compute concrete dollar estimates in the assessment report. Always note that prices change and the user should verify.

| Model | Input | Output | Best For |
| --- | --- | --- | --- |
| GPT-4o | $2.50 | $10.00 | Complex reasoning, agentic tasks |
| GPT-4o-mini | $0.15 | $0.60 | Simple classification, extraction |
| Claude Opus | $15.00 | $75.00 | Complex reasoning, agentic tasks |
| Claude Sonnet | $3.00 | $15.00 | Balanced quality/cost |
| Claude Haiku | $0.80 | $4.00 | Classification, routing, extraction |
| Gemini 1.5 Pro | $1.25 | $5.00 | Long context tasks |
| Gemini 1.5 Flash | $0.075 | $0.30 | Fast, cheap classification |

### Model Downgrade Map

When a node is classified as LLM-as-Function or LLM-as-Router, suggest model downgrades:

| Task Type | Current (common) | Recommended | Cost Reduction |
| --- | --- | --- | --- |
| Simple classification (< 5 categories) | GPT-4o / Sonnet | GPT-4o-mini / Haiku / Flash | 85-97% |
| Entity extraction (structured output) | GPT-4o / Sonnet | GPT-4o-mini / Haiku | 85-94% |
| Summarization | GPT-4o / Sonnet | GPT-4o-mini / Haiku | 85-94% |
| Translation | GPT-4o / Sonnet | GPT-4o-mini / Haiku | 85-94% |
| Routing (< 10 branches) | GPT-4o / Sonnet | GPT-4o-mini / Haiku / Flash | 85-97% |
| Sentiment analysis | Any LLM | Rule-based / GPT-4o-mini | 95-100% |
| Format conversion | Any LLM | Code logic (no LLM) | 100% |

### Cost Assessment Table Template

Present this in the assessment report with actual numbers filled in:

| Node | Current (LLM calls x model) | Est. Cost/1K runs | Proposed | Est. Cost/1K runs | Savings |
| --- | --- | --- | --- | --- | --- |
| Classify input | 1 x GPT-4o (~500 tokens) | $1.25 | Rule-based classifier | $0.00 | 100% (-$1.25) |
| Summarize document | 1 x GPT-4o (~2K tokens) | $5.00 | 1 x Haiku (~2K tokens) | $0.80 | 84% (-$4.20) |
| Route to handler | 1 x GPT-4o (~300 tokens) | $0.75 | Keyword matcher | $0.00 | 100% (-$0.75) |
| **Total** | **3 LLM calls** | **$7.00/1K** | **1 LLM call** | **$0.80/1K** | **89% (-$6.20/1K)** |

When computing estimates, use: `cost = (input_tokens / 1M × input_price) + (output_tokens / 1M × output_price)`. Estimate token counts from the prompt length and expected output length in the code.
