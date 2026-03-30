---
name: assess
description: "Analyze agentic AI code to determine if it is genuinely agentic, a disguised workflow, or a hybrid. Extracts the execution graph, classifies every node, identifies antipatterns, and estimates cost savings. Use when the user asks to review, audit, simplify, or optimize agent code, or asks 'is this really an agent?' or 'should this be a workflow?'. Supports LangGraph, CrewAI, AutoGen, LlamaIndex, Claude Agent SDK, Semantic Kernel, and raw Python."
allowed-tools: Read, Grep, Glob, Write, Edit, Bash
---

# Agent Assessment

Analyze agent code to determine if it should be a deterministic workflow, a hybrid workflow-with-agent-nodes, or remain fully agentic.

## Core Principle

An LLM call inside a workflow node does NOT make the workflow agentic. Summarization, entity extraction, classification, and routing are all **deterministic workflow nodes that happen to use an LLM as a function**. A system is only genuinely agentic when the LLM controls the execution flow — deciding what to do next, which tools to call, and when to stop.

## Phase 1: Code Ingestion & Graph Extraction

Read the agent code the user provides. Before analyzing, build a structural map.

1. **Identify the framework** — Read [framework-parsers.md](../../references/framework-parsers.md) for framework-specific parsing patterns (LangGraph, CrewAI, AutoGen, Semantic Kernel, LlamaIndex, Claude Agent SDK, raw Python with OpenAI/Anthropic calls, or custom orchestration).

2. **Extract the execution graph** by identifying:
   - Every node/step/agent in the system
   - What each node does (its function body, prompt, tools)
   - How control flows between nodes (edges, conditionals, routers)
   - Where LLM calls happen and what they do
   - What tools/APIs are called and by whom
   - Loop structures — are they bounded or unbounded?
   - State/context passing patterns between nodes

3. **For multi-agent systems** (chains, graphs, crews), also extract:
   - The inter-agent communication pattern (sequential, hierarchical, peer)
   - Whether agents share state or have independent contexts
   - Whether agents have independent goals or are executing subtasks of a fixed plan

4. **Produce an execution graph summary** — a table or diagram showing every node, its type, its inputs/outputs, and the edges between them. Present this to the user before proceeding.

## Phase 2: Assessment

Read [assessment-rubric.md](../../references/assessment-rubric.md) and apply the rubric to every node and to the system as a whole.

For **each node**, classify it as one of:

| Classification | Definition | Examples |
| --- | --- | --- |
| **Deterministic** | No LLM involved. Pure code logic, API calls, data transforms. | DB queries, HTTP calls, file I/O, data validation |
| **LLM-as-Function** | LLM is called but with a fixed, predictable purpose. The node's position in the flow is predetermined. The LLM does not decide what happens next. | Summarization, entity extraction, translation, classification, sentiment analysis, structured output generation |
| **LLM-as-Router** | LLM classifies input to select a branch. This is a switch/case — the set of possible branches is known at design time. | Intent classification, document type routing, priority triage |
| **Genuinely Agentic** | LLM decides the next action from an open-ended action space. The number of steps is not predetermined. The agent reasons about what to do, executes, observes, and decides again. | ReAct loops, open-ended tool selection, autonomous research, self-correcting code generation |

For the **overall system**, determine:

- **Pure Workflow**: Every node is Deterministic, LLM-as-Function, or LLM-as-Router. No genuine agency anywhere. → Replace entirely with a deterministic workflow.
- **Hybrid**: Some nodes are genuinely agentic, but the spine connecting them is deterministic. The order of major phases is known; only certain steps within require agency. → Extract the deterministic spine into a workflow; keep agentic nodes as activities within it.
- **Genuinely Agentic**: The top-level control flow itself is LLM-driven. What happens next is truly unpredictable and depends on LLM reasoning. → Keep as agent, but potentially optimize individual nodes.

## Output

Produce two files:

### 1. `assessment-report.md`

Must include:
- Source file path and framework identified
- Node-by-node classification table with reasoning
- Overall system verdict (Pure Workflow / Hybrid / Genuinely Agentic)
- Specific evidence for each classification (quote the code patterns that led to the decision)
- Identified antipatterns (see rubric)
- Cost/latency impact estimate with concrete dollar figures (see rubric pricing tables)
- Recommendation summary

### 2. `execution-graph.md`

Must include:
- Mermaid diagram of the execution flow with nodes colored by classification
- Node detail table (node, type, LLM model, inputs, outputs, edges in, edges out)
- State schema

Present the assessment to the user. Get confirmation before proceeding.

## Important Guidelines

- Never assume a system is over-agentified just because it uses an agent framework. LangGraph is sometimes used for legitimate agent patterns. Assess the actual code behavior.
- Be precise about what makes something agentic. "It uses tools" is not sufficient — tools called in a fixed sequence are not agentic. "The LLM picks which tool to call" is getting closer. "The LLM picks from an open set of tools AND decides when to stop" is genuinely agentic.
- When in doubt between LLM-as-Router and Genuinely Agentic, ask: "Are the possible next steps enumerated in the code, or does the LLM generate them?" If enumerated → Router. If generated → Agentic.
- Multi-agent systems that are just sequential pipelines with handoffs are workflows, not multi-agent systems. A crew of agents that execute in a fixed order with no dynamic routing is a pipeline.
- Pay attention to the prompt engineering. Sometimes the prompts reveal that the "agent" is heavily constrained to follow a specific sequence — meaning the framework is agentic but the actual behavior is deterministic.

## Next Step

After the assessment is reviewed, the user can run `/agentlens:convert` to generate Temporal workflow code based on this assessment.
