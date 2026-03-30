"""LLM client utilities shared by activities that need LLM calls.

Uses OpenAI SDK with GPT-4o-mini (downgraded from GPT-4o — see assessment report).
All LLM calls in this workflow are LLM-as-Function: fixed prompt, no tool use,
no routing decisions made by the LLM.
"""

from openai import AsyncOpenAI

# Shared async client — reused across activity invocations within a worker.
# Configure via OPENAI_API_KEY environment variable.
llm_client = AsyncOpenAI()

# Model selection: downgraded from gpt-4o to gpt-4o-mini.
# All tasks (sentiment, classification, drafting, editing) are simple enough
# for the smaller model. See assessment-report.md for cost analysis.
DEFAULT_MODEL = "gpt-4o-mini"
