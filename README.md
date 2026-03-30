# agentlens

A Claude Code plugin that looks through the "agent" veneer to find the workflow underneath.

Assess whether agentic AI code is genuinely agentic or a disguised workflow, then generate Temporal workflow replacements with full test coverage.

## Skills

### `/agentlens:assess`

Analyze agent code to determine if it should be a deterministic workflow, a hybrid, or remain fully agentic.

**What it does:**

- Identifies the framework (LangGraph, CrewAI, AutoGen, LlamaIndex, Claude Agent SDK, Semantic Kernel, raw Python)
- Extracts the execution graph (nodes, edges, LLM calls, tools)
- Classifies every node: Deterministic, LLM-as-Function, LLM-as-Router, or Genuinely Agentic
- Detects 6 common over-agentification antipatterns
- Estimates cost savings with concrete dollar figures and model downgrade recommendations
- Produces `assessment-report.md` and `execution-graph.md`

### `/agentlens:convert`

Generate Temporal workflow code from a completed assessment.

**What it does:**

- Reads the assessment report and execution graph from `/agentlens:assess`
- Generates a complete Temporal workflow replacement (Pure Workflow / Hybrid verdicts)
- For Genuinely Agentic verdicts: generates a Temporal wrapper with guardrails and monitoring
- Produces workflows, activities, models, worker, tests, and migration notes
- Includes retry policies, timeout configuration, and equivalence tests

## Supported Frameworks

- LangGraph (including subgraphs and multi-agent patterns)
- CrewAI (sequential and hierarchical crews)
- AutoGen / AG2 (group chat and two-agent patterns)
- LlamaIndex Workflows (event-driven steps)
- Anthropic Claude Agent SDK
- Microsoft Semantic Kernel
- Raw Python (OpenAI / Anthropic SDK direct calls)

## Installation

### Local development

```bash
claude --plugin-dir ./agentlens
```

### From a marketplace

```bash
/plugin install agentlens@<marketplace-name>
```

## Recommended: Temporal Developer Skill

For best results with `/agentlens:convert`, install the [Temporal Developer Skill](https://docs.temporal.io/with-ai). It gives Claude Code expert-level knowledge of Temporal's programming model — workflow determinism, activity patterns, retry policies, error handling, testing strategies, and common gotchas.

```bash
/plugin marketplace add temporalio/agent-skills
```

Then open the plugin manager with `/plugin` and install `temporal-developer`.

If you skip this step, `/agentlens:convert` will offer to install it for you before generating code.

## Usage

1. Share your agent code with Claude
2. Run `/agentlens:assess` to analyze the code
3. Review the assessment report and execution graph
4. Run `/agentlens:convert` to generate the Temporal workflow (installs the Temporal skill if needed)
5. Review the generated code and migration notes

## Example

The `examples/` directory contains a complete walkthrough:

- `examples/customer_support_agent.py` — a LangGraph "agent" that is actually a pipeline (input)
- `examples/generated_workflow/` — the Temporal workflow replacement (output)

The example agent was assessed as **Pure Workflow** (no genuine agency) and converted to a Temporal workflow with 94% cost reduction by downgrading from GPT-4o to GPT-4o-mini.

## Project Structure

```txt
agentlens/
├── .claude-plugin/
│   └── plugin.json              # Plugin manifest
├── skills/
│   ├── assess/
│   │   └── SKILL.md             # /agentlens:assess
│   └── convert/
│       └── SKILL.md             # /agentlens:convert
├── references/
│   ├── assessment-rubric.md     # Decision tree, antipatterns, cost tables
│   ├── framework-parsers.md     # Framework-specific extraction patterns
│   └── temporal-patterns.md     # 7 Temporal workflow patterns + testing
└── examples/
    ├── customer_support_agent.py
    └── generated_workflow/
```

## License

MIT
