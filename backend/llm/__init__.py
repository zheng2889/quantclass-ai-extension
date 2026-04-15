"""LLM module."""

from llm.base import BaseLLM, LLMMessage, LLMResponse, LLMUsage
from llm.adapter import LLMAdapter, OpenAILLM, llm_adapter
from llm.prompts import (
    SUMMARY_PROMPT,
    TAG_SUGGESTION_PROMPT,
    POLISH_PROMPT,
    FORMAT_MARKDOWN_PROMPT,
    FORMAT_JSON_PROMPT,
    FORMAT_SQL_PROMPT,
    FORMAT_PYTHON_PROMPT,
    CHECK_CODE_PROMPT,
    SYSTEM_PROMPTS,
    get_prompt,
)

__all__ = [
    # Base
    "BaseLLM",
    "LLMMessage",
    "LLMResponse",
    "LLMUsage",
    # Adapter
    "LLMAdapter",
    "OpenAILLM",
    "llm_adapter",
    # Prompts
    "SUMMARY_PROMPT",
    "TAG_SUGGESTION_PROMPT",
    "POLISH_PROMPT",
    "FORMAT_MARKDOWN_PROMPT",
    "FORMAT_JSON_PROMPT",
    "FORMAT_SQL_PROMPT",
    "FORMAT_PYTHON_PROMPT",
    "CHECK_CODE_PROMPT",
    "SYSTEM_PROMPTS",
    "get_prompt",
]
