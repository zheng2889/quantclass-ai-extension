"""FakeLLM for L2 integration tests.

Implements the minimum surface of ``llm.base.BaseLLM`` that the routers and
services actually touch: ``chat``, ``chat_stream``, plus a ``.model`` attribute
(summary_service reads it to populate ``model_used``). No real network calls,
no real OpenAI client construction.

Responses are prompt-aware so one fixture covers every caller:
  * Tag suggestion  → comma-separated tag list
  * Compare         → <TABLE>/<SUMMARY>/<RECOMMENDATION> structure
  * Code check      → "Line N: [severity] msg" line (parser regex target)
  * Polish / format → short deterministic string
  * Summary default → a short Chinese summary sentence

If a test needs a very specific content, it can push onto ``FakeLLM.queue``
before making the call; the queued content wins over the auto-detected one.
"""

from __future__ import annotations

from typing import AsyncIterator, List, Optional
from collections import deque

from llm.base import BaseLLM, LLMMessage, LLMResponse, LLMUsage


# Shared queue — tests can push a canned response before hitting an endpoint.
_response_queue: "deque[str]" = deque()


def push_response(content: str) -> None:
    """Queue the next chat() content, bypassing prompt-based detection."""
    _response_queue.append(content)


def clear_queue() -> None:
    _response_queue.clear()


def _detect_mode(prompt: str) -> str:
    """Pick a mode from prompt markers. Most specific matcher wins."""
    # Tag suggestion prompt ends with "Suggested tags:" (unique to TAG_SUGGESTION_PROMPT).
    if "Suggested tags:" in prompt:
        return "tags"
    # Compare prompt requires <TABLE>/<RECOMMENDATION> wrappers (unique).
    if "<TABLE>" in prompt and "<RECOMMENDATION>" in prompt:
        return "compare"
    # Code review prompt literally says "code review expert".
    if "code review expert" in prompt:
        return "code_check"
    # Polish prompt ends with "Polished text:".
    if "Polished text:" in prompt:
        return "polish"
    # Format prompts from assist router are inline templates, start with "Format".
    # They also typically say "proper Markdown" / "proper JSON" / "SQL with proper"
    # / "Python code (PEP 8 style)". Match on "Format the following".
    if "Format the following" in prompt:
        return "format"
    # Summary prompt (zh or en): contains "标题：" / "Title:" and "摘要：" / "Summary:".
    if ("标题：" in prompt or "Title:" in prompt) and ("摘要：" in prompt or "Summary:" in prompt):
        return "summary"
    return "default"


_MODE_CONTENT = {
    "tags": "量化策略, 回测, 趋势跟踪",
    "compare": (
        "<TABLE>\n"
        "| 帖子 | 策略 | 指标 |\n"
        "|---|---|---|\n"
        "| 帖子1 | 动量 | 夏普1.2 |\n"
        "| 帖子2 | 回归 | 夏普0.9 |\n"
        "</TABLE>\n"
        "<SUMMARY>两个帖子分别探讨动量与回归策略，侧重点不同。</SUMMARY>\n"
        "<RECOMMENDATION>优先阅读帖子1。</RECOMMENDATION>"
    ),
    "code_check": (
        "Line 3: [warning] Variable name not following PEP8 convention\n"
        "Line 5: [error] Possible null pointer access"
    ),
    "polish": "这是一段经过润色的文本，保持原意但表达更清晰。",
    "format": "```markdown\n# Title\n- item\n```",
    "summary": "该帖子主要讨论了量化策略的回测方法与实盘表现。作者总结了三点关键结论。",
    "default": "模拟返回内容。",
}


def _pick_content(messages: List[LLMMessage]) -> str:
    # Test-queued content takes priority.
    if _response_queue:
        return _response_queue.popleft()
    # Otherwise detect by the last user message's prompt.
    last_user = next(
        (m.content for m in reversed(messages) if m.role == "user"),
        "",
    )
    return _MODE_CONTENT[_detect_mode(last_user)]


class FakeLLM(BaseLLM):
    """In-process LLM double. Never touches the network."""

    def __init__(self, model: str = "fake-model-v1") -> None:
        super().__init__(api_key="fake", base_url="http://fake", model=model)
        self.provider_name = "fake"
        # Track call counts so tests can assert how many LLM hops happened.
        self.calls = 0
        self.stream_calls = 0

    async def chat(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        self.calls += 1
        content = _pick_content(messages)
        return LLMResponse(
            content=content,
            model=self.model,
            usage=LLMUsage(
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
            ),
            finish_reason="stop",
            raw_response=None,
        )

    async def chat_stream(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        self.stream_calls += 1
        content = _pick_content(messages)
        # Yield in small chunks so tests can observe the SSE framing.
        mid = max(1, len(content) // 3)
        chunks = [content[:mid], content[mid : 2 * mid], content[2 * mid :]]
        for c in chunks:
            if c:
                yield c

    async def complete(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        return await self.chat(
            [LLMMessage(role="user", content=prompt)],
            temperature=temperature,
            max_tokens=max_tokens,
        )


# Shared instance used by the conftest fixture. Exposed so tests can reset
# counters or push queued responses.
fake_llm_singleton = FakeLLM()
