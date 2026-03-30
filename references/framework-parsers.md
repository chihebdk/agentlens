# Framework Parsing Patterns

How to extract the execution graph from different agent frameworks and raw LLM code.

## LangGraph

LangGraph defines graphs explicitly, making extraction straightforward.

### What to look for

```python
# Graph definition
graph = StateGraph(AgentState)       # or MessageGraph

# Nodes — each add_node call is a node
graph.add_node("classify", classify_fn)
graph.add_node("research", research_agent)
graph.add_node("summarize", summarize_fn)

# Edges — static edges are deterministic, conditional edges may be agentic
graph.add_edge("classify", "research")                    # Static = deterministic
graph.add_conditional_edges("research", route_fn, {...})  # Conditional = inspect route_fn
graph.add_edge(START, "classify")

# Entry and exit
graph.set_entry_point("classify")
graph.set_finish_point("summarize")
```

### Extraction steps

1. **Find all `add_node` calls** — each is a node. Read the function/class it references.
2. **Find all `add_edge` calls** — these are deterministic transitions.
3. **Find all `add_conditional_edges` calls** — read the routing function. If it returns one of a fixed set of strings mapped to known nodes, it is an LLM-as-Router. If it involves dynamic tool selection, it may be agentic.
4. **Read the State class** — this shows what data flows between nodes and how it accumulates.
5. **Check for `create_react_agent` or `ToolNode`** — these are strong signals of genuine agency within that node. But read the tool list: if the tools form an obvious pipeline (search → fetch → parse), it may still be a disguised workflow.

### LangGraph subgraphs

LangGraph supports nested subgraphs. Each subgraph is itself a graph that becomes a node in the parent. Analyze each subgraph independently, then compose the results.

```python
# Subgraph used as a node
inner_graph = StateGraph(InnerState)
# ... define inner graph ...
outer_graph.add_node("research_phase", inner_graph.compile())
```

### LangGraph multi-agent patterns

LangGraph implements multi-agent via subgraphs or message passing. Common patterns:

- **Supervisor pattern**: One agent routes to specialist agents. The supervisor is an LLM-as-Router if the specialist set is fixed. The specialists may or may not be genuinely agentic.
- **Sequential chain**: Agents execute in order via static edges. This is a pipeline, not multi-agent.
- **Hierarchical**: Nested supervisors. Analyze each level independently.

## CrewAI

CrewAI uses a higher-level abstraction: Agents, Tasks, and Crews.

### What to look for

```python
# Agents — each Agent has a role, goal, backstory, and tools
researcher = Agent(
    role="Research Analyst",
    goal="Find relevant information",
    tools=[search_tool, web_scraper],
    llm=ChatOpenAI(model="gpt-4")
)

# Tasks — each Task has a description, agent, and expected output
research_task = Task(
    description="Research the topic: {topic}",
    agent=researcher,
    expected_output="A summary of findings"
)

# Crew — defines execution order and process type
crew = Crew(
    agents=[researcher, writer, reviewer],
    tasks=[research_task, write_task, review_task],
    process=Process.sequential  # or Process.hierarchical
)
```

### Extraction steps

1. **List all Agents** — note their tools, LLM, and role description.
2. **List all Tasks** — note which agent owns each task and what the expected output is.
3. **Check the Process type**:
   - `Process.sequential` → tasks execute in list order. This is a pipeline. Each task is a node; edges are the list order. Almost certainly a workflow, not genuine multi-agent.
   - `Process.hierarchical` → a manager agent delegates to other agents. Analyze the manager's delegation logic. If it follows a predictable pattern, it is routing. If it dynamically assigns based on task content, it may be agentic.
4. **Read each agent's tools** — if an agent has tools AND a ReAct-style prompt, it may be genuinely agentic within its task. If it just has an LLM call with a structured output, it is LLM-as-Function.
5. **Check for task dependencies** — `context=[other_task]` means output of one task feeds into another. Map these as edges.

### CrewAI red flags for over-agentification

- A sequential crew with 2-3 agents that each do one specific thing → pipeline
- Agents with no tools (just LLM calls) → LLM-as-Function nodes
- Tasks with very specific `expected_output` that constrains the agent to one behavior → not genuinely agentic

## AutoGen / AG2

AutoGen uses conversational agents that message each other.

### What to look for

```python
# Agents
assistant = AssistantAgent("assistant", llm_config=llm_config)
user_proxy = UserProxyAgent("user_proxy", code_execution_config={...})
critic = AssistantAgent("critic", system_message="Review and critique...")

# Group chat
groupchat = GroupChat(
    agents=[user_proxy, assistant, critic],
    messages=[],
    max_round=10
)

# Or two-agent chat
user_proxy.initiate_chat(assistant, message="...")
```

### Extraction steps

1. **List all agents** — note their type (AssistantAgent, UserProxyAgent, custom).
2. **Check if GroupChat or two-agent chat** — GroupChat with `speaker_selection_method` reveals routing logic.
3. **Read `speaker_selection_method`**:
   - `"round_robin"` → fixed sequence, pure pipeline
   - `"auto"` → LLM decides who speaks next. Check if it always follows the same pattern in practice.
   - Custom function → read the function; if it uses rules, it is deterministic.
4. **Check `max_round`** — a small, fixed number suggests bounded iteration.
5. **Check for `is_termination_msg`** — this defines the stop condition. If trivial (e.g., contains "TERMINATE"), the agent is likely following a script.

## Raw Python (OpenAI / Anthropic SDK)

No framework — just direct API calls.

### What to look for

```python
# Direct LLM calls
response = client.chat.completions.create(
    model="gpt-4",
    messages=[...],
    tools=[...],
    tool_choice="auto"  # or "required" or "none" or specific function
)

# Or Anthropic
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    messages=[...],
    tools=[...]
)
```

### Extraction steps

1. **Find all LLM API calls** — search for `completions.create`, `messages.create`, or similar.
2. **For each call, determine**:
   - Does it have `tools`? If no → LLM-as-Function.
   - Does it have `tool_choice="none"` or no tools? → LLM-as-Function.
   - Does it have `tool_choice="auto"` with multiple tools? → Potentially agentic. Check the surrounding loop.
   - Does it have `tool_choice` set to a specific function? → LLM-as-Function (forced tool call).
3. **Map the control flow** — read the Python code. Follow the if/else, for/while, and function calls to understand the execution path.
4. **Check for while loops around LLM calls** — this is the ReAct pattern. Check the loop condition: is it "until the LLM says stop" (agentic) or "until we get a valid response" (retry)?
5. **Check for structured output** — `response_format` or Pydantic parsing constrains the LLM output, making it more like a function call than an agent decision.

## Semantic Kernel

Microsoft's orchestration framework.

### What to look for

```python
# Plugins (tools)
kernel.add_plugin(TimePlugin(), "time")
kernel.add_plugin(MathPlugin(), "math")

# Planner
planner = SequentialPlanner(kernel)  # or StepwisePlanner, HandlebarsPlanner
plan = await planner.create_plan(goal="...")
result = await plan.invoke(kernel)
```

### Extraction steps

1. **Check the planner type**:
   - `SequentialPlanner` → generates a fixed sequence of function calls. If the sequence is predictable from the input, this is a workflow.
   - `StepwisePlanner` → iterative, closer to ReAct. More likely genuinely agentic.
   - `HandlebarsPlanner` → template-based, usually deterministic.
2. **List all plugins** — these are the available tools.
3. **Check if `auto_invoke_kernel_functions`** is enabled — if yes, the LLM decides which functions to call (potentially agentic). If no, the code controls invocation (deterministic).

## LlamaIndex Workflows

LlamaIndex Workflows use an event-driven step architecture with explicit typed events.

### What to look for

```python
from llama_index.core.workflow import Workflow, StartEvent, StopEvent, step, Event

# Custom events define data flow between steps
class ClassifiedEvent(Event):
    doc_type: str
    confidence: float

class SummarizedEvent(Event):
    summary: str

class MyWorkflow(Workflow):
    @step
    async def classify(self, ev: StartEvent) -> ClassifiedEvent:
        # LLM call to classify
        result = await self.llm.acomplete(f"Classify: {ev.document}")
        return ClassifiedEvent(doc_type=result.text, confidence=0.9)

    @step
    async def summarize(self, ev: ClassifiedEvent) -> SummarizedEvent:
        summary = await self.llm.acomplete(f"Summarize: {ev.get('document')}")
        return SummarizedEvent(summary=summary.text)

    @step
    async def finalize(self, ev: SummarizedEvent) -> StopEvent:
        return StopEvent(result={"summary": ev.summary})
```

### Extraction steps

1. **Find the Workflow subclass** — this is the container for all steps.
2. **Find all `@step` decorated methods** — each is a node. The input event type is the trigger; the return event type is the output.
3. **Map the event flow** — `StartEvent → ClassifiedEvent → SummarizedEvent → StopEvent` defines the graph edges. These are implicit from the type signatures, not explicit like LangGraph.
4. **Check for `@step(num_workers=N)`** — parallel execution of the same step on multiple inputs.
5. **Check for branching** — a step that returns different event types based on conditions acts as a router. If the routing uses LLM output → LLM-as-Router. If it uses code logic → Deterministic.
6. **Check for `ctx.collect_events()`** — this is a fan-in/join pattern where a step waits for multiple upstream events.
7. **Look for agent integration** — `FunctionCallingAgent` or `ReActAgent` used within a step means that specific step is agentic, while the overall workflow structure is deterministic.

### LlamaIndex red flags for over-agentification

- A linear chain of `@step` methods each doing one LLM call → pipeline, not agent
- Steps with no branching and predictable event flow → pure workflow
- `AgentRunner` used for a single tool call with no iteration → LLM-as-Function

## Anthropic Claude Agent SDK

The Claude Agent SDK (`claude-agent-sdk`) provides a structured way to build agents with tools.

### What to look for

```python
from claude_agent_sdk import Agent, tool

@tool
def search_web(query: str) -> str:
    """Search the web for information."""
    return search_api.search(query)

@tool
def read_file(path: str) -> str:
    """Read a file from disk."""
    return open(path).read()

agent = Agent(
    model="claude-sonnet-4-20250514",
    tools=[search_web, read_file],
    system_prompt="You are a research assistant...",
    max_turns=10,
)

result = agent.run("Research topic X and write a summary")
```

### Extraction steps

1. **Find `Agent()` instantiations** — note the model, tools, system_prompt, and max_turns.
2. **List all `@tool` decorated functions** — these are the agent's available actions.
3. **Check `max_turns`**:
   - `max_turns=1` → single LLM call, this is LLM-as-Function regardless of tool count.
   - `max_turns` small and fixed (2-3) → likely a bounded pipeline, not genuinely agentic.
   - `max_turns` large or unset → potentially genuinely agentic.
4. **Read the system prompt** — if it prescribes a fixed sequence ("First search, then read, then summarize"), the agent is following a script → workflow.
5. **Check for multi-agent patterns**:
   - Multiple `Agent` instances orchestrated by code → map the orchestration logic. If sequential → pipeline.
   - An agent that calls other agents as tools → hierarchical. Analyze each level.
   - `Swarm`-style handoffs → check if the handoff routing is fixed or dynamic.
6. **Check tool count and diversity**:
   - 1-2 tools in an obvious sequence → pipeline disguised as agent
   - Many diverse tools with no prescribed order → more likely genuinely agentic
7. **Look for `agent.run()` vs `agent.run_stream()`** — streaming doesn't change classification but matters for Temporal conversion (see temporal-patterns.md streaming section).

### Claude Agent SDK red flags for over-agentification

- Single tool + `max_turns=1` → just a function call wrapper
- System prompt that dictates step-by-step execution order → pipeline
- Two agents passing output sequentially with no branching → pipeline crew

## Observability & Trace Extraction

When trace data is available, use it to validate your classification. Real execution traces reveal whether an "agent" actually behaves dynamically or follows a fixed path.

### Per-Framework Trace Access

| Framework | Tracing Method | How to Extract |
| --- | --- | --- |
| **LangGraph** | LangSmith integration | `LANGCHAIN_TRACING_V2=true` env var. Traces show every node execution, tool call, and routing decision. Export via LangSmith API or UI. |
| **CrewAI** | Built-in verbose mode | `Crew(verbose=True)` logs all agent actions. CrewAI also integrates with LangSmith. Check for `crew.usage_metrics` for token counts. |
| **AutoGen** | Conversation logging | All agent messages are logged by default. Check `GroupChat.messages` or enable `logging_session_id`. |
| **LlamaIndex** | Callback system | `llama_index.core.callbacks.CallbackManager` with `LlamaDebugHandler` captures every step, LLM call, and event. Also integrates with Arize Phoenix. |
| **Claude Agent SDK** | Built-in events | The SDK emits structured events for each turn, tool call, and result. Capture via the `events` iterator on `agent.run_stream()`. |
| **Raw Python** | Manual | Add logging around API calls. Look for existing `print`/`logging` statements. Suggest adding structured logging if none exists. |

### What to Look for in Traces

1. **Tool call sequence consistency** — run the same input 5+ times. If the tool call sequence is identical every time → workflow behavior, not agency.
2. **Iteration count distribution** — if every run takes exactly N iterations → bounded/deterministic. If it varies widely → potentially agentic.
3. **Routing decision patterns** — if the router always picks the same branch for similar inputs → could be replaced with rules.
4. **Token usage per step** — identifies expensive nodes that are candidates for model downgrade.

## General Extraction Checklist

Regardless of framework, always extract:

- [ ] Complete list of nodes/agents/steps
- [ ] For each node: what it does, its prompt (if LLM), its tools (if any)
- [ ] All edges/transitions and whether they are static or conditional
- [ ] All routing logic and what drives the routing decisions
- [ ] Loop structures and their termination conditions
- [ ] State/context schema and how it flows between nodes
- [ ] Error handling and retry logic
- [ ] Which LLM model each node uses
- [ ] Timeout and concurrency settings
