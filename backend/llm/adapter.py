"""Unified LLM adapter for different providers."""

import asyncio
import time
import json
from typing import AsyncIterator, Dict, Any, List, Optional, Literal
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionChunk
from anthropic import AsyncAnthropic

from config import load_config, ProviderConfig
from llm.base import BaseLLM, LLMMessage, LLMResponse, LLMUsage
from llm.prompts import SYSTEM_PROMPTS
from database.connection import db


async def _log_llm_call(
    provider_name: str,
    model: str,
    endpoint: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    success: bool = True,
    error_message: Optional[str] = None
):
    """Log LLM API call to database."""
    try:
        await db.execute(
            """INSERT INTO llm_logs
               (provider, model, endpoint, input_tokens, output_tokens, latency_ms, success, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (provider_name, model, endpoint, input_tokens, output_tokens, latency_ms,
             1 if success else 0, error_message)
        )
    except Exception:
        pass


class OpenAILLM(BaseLLM):
    """OpenAI-compatible LLM implementation."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        provider_name: str = "unknown",
        **kwargs
    ):
        super().__init__(api_key, base_url, model, **kwargs)
        self.provider_name = provider_name

        # Browser-like default headers to bypass WAF on some relay proxies.
        # The openai SDK's own headers (Authorization, Content-Type, etc.)
        # are added separately and not affected by default_headers.
        default_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
        }

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=60.0,
            default_headers=default_headers,
        )

    def _requires_temperature_one(self) -> bool:
        """Some models only accept temperature=1 (reject anything else with 400).

        Known offenders:
            - Kimi k2.5  (moonshot-v1-k2.5, kimi-k2.5): "only 1 is allowed for this model"
            - OpenAI reasoning models (o1, o1-preview, o1-mini, o3, o3-mini, o4-mini):
              silently ignore or reject non-default temperature

        Rather than pushing this constraint out to every call site, we coerce
        the parameter here. Callers stay model-agnostic.
        """
        m = (self.model or "").lower()
        if "k2.5" in m:  # Kimi k2.5 variants
            return True
        # OpenAI reasoning models — match model id prefix with a hyphen or
        # end-of-string so we do not accidentally match "octopus-..." etc.
        for prefix in ("o1", "o3", "o4-mini"):
            if m == prefix or m.startswith(prefix + "-") or m.startswith(prefix + "_"):
                return True
        return False

    async def chat(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """Send chat completion request with 1 retry on failure.

        Always uses ``stream=True`` under the hood and reassembles the
        full response from chunks. Some third-party relay proxies reject
        ``stream=False`` with ``400 Stream must be set to true`` — by
        always streaming we stay compatible with every known proxy while
        still returning a single ``LLMResponse`` to the caller.
        """
        # Silently coerce temperature for models that only allow temperature=1.
        # See _requires_temperature_one() for the list.
        if self._requires_temperature_one() and temperature != 1:
            temperature = 1
        last_error = None
        for attempt in range(2):  # 最多 2 次尝试（1 次重试）
            start_time = time.time()
            try:
                # Stream + reassemble: compatible with relays that reject
                # stream=False. We collect chunks into a buffer and build
                # the LLMResponse at the end, so the caller sees no
                # difference vs a non-streaming call.
                content_parts: list[str] = []
                finish_reason = "stop"
                model_name = self.model
                stream = await self.client.chat.completions.create(
                    model=self.model,
                    messages=self.format_messages(messages),
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                    **kwargs
                )
                async for chunk in stream:
                    if chunk.choices:
                        choice = chunk.choices[0]
                        if choice.delta and choice.delta.content:
                            content_parts.append(choice.delta.content)
                        if choice.finish_reason:
                            finish_reason = choice.finish_reason
                    if chunk.model:
                        model_name = chunk.model

                latency_ms = int((time.time() - start_time) * 1000)

                # Token counts are not reliably available from streamed
                # responses on all providers; approximate from char count.
                full_content = "".join(content_parts)
                output_tokens = max(1, len(full_content) // 4)
                input_tokens = 0
                total_tokens = output_tokens

                await _log_llm_call(self.provider_name, self.model,
                    endpoint="/chat/completions",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    success=True
                )

                return LLMResponse(
                    content=full_content,
                    model=model_name,
                    usage=LLMUsage(
                        prompt_tokens=input_tokens,
                        completion_tokens=output_tokens,
                        total_tokens=total_tokens
                    ),
                    finish_reason=finish_reason,
                )

            except Exception as e:
                last_error = e
                latency_ms = int((time.time() - start_time) * 1000)
                await _log_llm_call(self.provider_name, self.model,
                    endpoint="/chat/completions",
                    input_tokens=0,
                    output_tokens=0,
                    latency_ms=latency_ms,
                    success=False,
                    error_message=str(e)
                )
                if attempt == 0:
                    await asyncio.sleep(1)  # 等 1 秒后重试

        raise last_error
    
    async def chat_stream(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Send streaming chat completion request."""
        if self._requires_temperature_one() and temperature != 1:
            temperature = 1
        start_time = time.time()
        input_tokens = 0
        output_tokens = 0

        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=self.format_messages(messages),
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                **kwargs
            )
            
            last_finish_reason = None
            chunk_count = 0
            total_chars = 0
            async for chunk in stream:
                if chunk.choices:
                    choice = chunk.choices[0]
                    if choice.delta and choice.delta.content:
                        output_tokens += 1  # Approximation
                        chunk_count += 1
                        total_chars += len(choice.delta.content)
                        yield choice.delta.content
                    if choice.finish_reason:
                        last_finish_reason = choice.finish_reason

            # Log detailed stream outcome — crucial for diagnosing "it stopped
            # mid-sentence" reports. Proxies sometimes emit finish_reason="stop"
            # early or drop the connection silently; this line lets us tell the
            # two cases apart.
            import logging
            logging.getLogger(__name__).info(
                f"[stream_done] provider={self.provider_name} model={self.model} "
                f"chunks={chunk_count} chars={total_chars} finish={last_finish_reason!r}"
            )

            # OpenAI-compatible endpoints report finish_reason="length" when
            # the output was capped by max_tokens. Surface a visible marker
            # so users see why the reply was cut off instead of assuming
            # the stream dropped.
            if last_finish_reason == "length":
                yield (
                    "\n\n---\n\n"
                    "⚠️ _响应因达到 max_tokens 上限被截断。"
                    "如需更长回复，请调高后端 max_tokens。_"
                )
            elif last_finish_reason is None and chunk_count > 0:
                # Stream ended without any finish_reason — almost always an
                # upstream proxy that dropped the SSE mid-flight. Tell the
                # user so they don't stare at a half-sentence wondering why.
                yield (
                    "\n\n---\n\n"
                    "⚠️ _上游代理在未发送结束信号的情况下断开了流式连接。"
                    "如果频繁出现，可能是代理的 SSE 实现不完整。_"
                )

            latency_ms = int((time.time() - start_time) * 1000)
            await _log_llm_call(self.provider_name, self.model,
                endpoint="/chat/completions (stream)",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                success=True
            )
            
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            await _log_llm_call(self.provider_name, self.model,
                endpoint="/chat/completions (stream)",
                input_tokens=0,
                output_tokens=0,
                latency_ms=latency_ms,
                success=False,
                error_message=str(e)
            )
            raise
    
    async def complete(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """Send completion request (using chat API)."""
        messages = [LLMMessage(role="user", content=prompt)]
        return await self.chat(messages, temperature, max_tokens, **kwargs)


class AnthropicLLM(BaseLLM):
    """Anthropic native API implementation.

    NOTE: No longer wired up by LLMAdapter.get_llm() — we now route every
    provider (including ``anthropic``) through OpenAILLM, because virtually
    every third-party Claude proxy implements the OpenAI-compatible schema
    rather than Anthropic's native one, and the official Anthropic API also
    supports /v1/chat/completions since 2024. This class is kept for
    possible future use (prompt caching, advanced tool use).
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        provider_name: str = "anthropic",
        **kwargs
    ):
        # Anthropic SDK appends "/v1/messages" to base_url internally, so
        # the base_url must NOT end with /v1. Strip a trailing /v1 so
        # OpenAI-style URLs (ending in /v1) still work.
        if base_url:
            trimmed = base_url.rstrip("/")
            if trimmed.endswith("/v1"):
                base_url = trimmed[:-3]
        super().__init__(api_key, base_url, model, **kwargs)
        self.provider_name = provider_name
        self.client = AsyncAnthropic(
            api_key=api_key,
            base_url=base_url,
            timeout=60.0,
            default_headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/136.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
            },
        )

    def _split_system(self, messages: List[LLMMessage]):
        """Extract system message from the list; Anthropic takes it as a separate param."""
        system = None
        user_msgs = []
        for m in messages:
            if m.role == "system":
                system = m.content
            else:
                user_msgs.append({"role": m.role, "content": m.content})
        return system, user_msgs

    async def chat(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """Send chat request with 1 retry on failure."""
        last_error = None
        for attempt in range(2):
            start_time = time.time()
            try:
                system, user_msgs = self._split_system(messages)
                create_kwargs: Dict[str, Any] = dict(
                    model=self.model,
                    messages=user_msgs,
                    temperature=temperature,
                    max_tokens=max_tokens or 8192,
                )
                if system:
                    create_kwargs["system"] = system

                response = await self.client.messages.create(**create_kwargs)

                latency_ms = int((time.time() - start_time) * 1000)
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens

                await _log_llm_call(
                    self.provider_name, self.model,
                    endpoint="/messages",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    success=True,
                )

                content = ""
                for block in response.content:
                    if block.type == "text":
                        content += block.text

                return LLMResponse(
                    content=content,
                    model=response.model,
                    usage=LLMUsage(
                        prompt_tokens=input_tokens,
                        completion_tokens=output_tokens,
                        total_tokens=input_tokens + output_tokens,
                    ),
                    finish_reason=response.stop_reason or "end_turn",
                )

            except Exception as e:
                last_error = e
                latency_ms = int((time.time() - start_time) * 1000)
                await _log_llm_call(
                    self.provider_name, self.model,
                    endpoint="/messages",
                    input_tokens=0, output_tokens=0,
                    latency_ms=latency_ms,
                    success=False,
                    error_message=str(e),
                )
                if attempt == 0:
                    await asyncio.sleep(1)

        raise last_error

    async def chat_stream(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Send streaming chat request."""
        start_time = time.time()
        input_tokens = 0
        output_tokens = 0

        try:
            system, user_msgs = self._split_system(messages)
            create_kwargs: Dict[str, Any] = dict(
                model=self.model,
                messages=user_msgs,
                temperature=temperature,
                max_tokens=max_tokens or 4096,
            )
            if system:
                create_kwargs["system"] = system

            final = None
            async with self.client.messages.stream(**create_kwargs) as stream:
                async for text in stream.text_stream:
                    output_tokens += 1
                    yield text
                final = await stream.get_final_message()

            if final:
                # If the model hit the max_tokens ceiling mid-thought, append
                # a visible marker so users know the output was cut off
                # (rather than silently ending mid-sentence like Claude does).
                if getattr(final, "stop_reason", None) == "max_tokens":
                    yield (
                        "\n\n---\n\n"
                        "⚠️ _响应因达到 max_tokens 上限被截断。"
                        f"如需更长回复，请调高后端 max_tokens（当前 {create_kwargs['max_tokens']}）。_"
                    )
                if final.usage:
                    input_tokens = final.usage.input_tokens
                    output_tokens = final.usage.output_tokens

            latency_ms = int((time.time() - start_time) * 1000)
            await _log_llm_call(
                self.provider_name, self.model,
                endpoint="/messages (stream)",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                success=True,
            )

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            await _log_llm_call(
                self.provider_name, self.model,
                endpoint="/messages (stream)",
                input_tokens=0, output_tokens=0,
                latency_ms=latency_ms,
                success=False,
                error_message=str(e),
            )
            raise

    async def complete(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """Send completion request (using messages API)."""
        messages = [LLMMessage(role="user", content=prompt)]
        return await self.chat(messages, temperature, max_tokens, **kwargs)


class LLMAdapter:
    """Adapter to get appropriate LLM instance based on configuration."""
    
    def __init__(self):
        self._config = load_config()
        self._llm_cache: Dict[str, BaseLLM] = {}

    def get_llm(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None
    ) -> BaseLLM:
        """Get LLM instance for specified provider and model."""
        self._config = load_config()  # Reload to get latest config
        
        # Determine provider
        if provider is None:
            provider = self._config.default_provider
        
        # Get provider config
        provider_config = self._config.providers.get(provider)
        if not provider_config:
            raise ValueError(f"Unknown provider: {provider}")
        
        # Determine model.
        #
        # Rationale for NOT falling back to provider_config.models[0]:
        # The `models` list is a UI hint for the dropdown, not the source of
        # truth. The authoritative value is `default_model` — if the user
        # typed/selected it, trust it and pass it through to the upstream API.
        # A mismatch between default_model and the models list used to silently
        # coerce the request to a wrong model and produced a 400 from the
        # upstream that the user could not diagnose (e.g. "claude-4.6-opus is
        # not supported" when they had already picked a different model).
        if model is None:
            model = self._config.default_model
        
        cache_key = f"{provider}:{model}"

        if cache_key not in self._llm_cache:
            # Route by the provider's `protocol` field:
            #   "openai"    → OpenAILLM (AsyncOpenAI, /v1/chat/completions)
            #   "anthropic" → AnthropicLLM (AsyncAnthropic, /v1/messages)
            #
            # Default is "openai" because virtually every third-party proxy
            # implements the OpenAI-compatible schema. Users who talk to the
            # official Anthropic API (or a proxy that mirrors its native
            # /v1/messages schema) can set protocol="anthropic" in the
            # custom LLM creation UI.
            protocol = getattr(provider_config, "protocol", "openai") or "openai"
            if protocol == "anthropic":
                self._llm_cache[cache_key] = AnthropicLLM(
                    api_key=provider_config.api_key,
                    base_url=provider_config.base_url,
                    model=model,
                    provider_name=provider,
                )
            else:
                self._llm_cache[cache_key] = OpenAILLM(
                    api_key=provider_config.api_key,
                    base_url=provider_config.base_url,
                    model=model,
                    provider_name=provider,
                )

        return self._llm_cache[cache_key]
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        provider: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> LLMResponse:
        """Simple chat interface."""
        llm = self.get_llm(provider, model)
        llm_messages = [LLMMessage(role=m["role"], content=m["content"]) for m in messages]
        
        if stream:
            # For streaming, caller should use chat_stream directly
            raise ValueError("Use chat_stream method for streaming")
        
        return await llm.chat(llm_messages, temperature, max_tokens)
    
    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        provider: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> AsyncIterator[str]:
        """Streaming chat interface."""
        llm = self.get_llm(provider, model)
        llm_messages = [LLMMessage(role=m["role"], content=m["content"]) for m in messages]
        
        async for chunk in llm.chat_stream(llm_messages, temperature, max_tokens):
            yield chunk
    
    def list_available_models(self) -> Dict[str, List[str]]:
        """List all available models by provider."""
        return {
            name: config.models 
            for name, config in self._config.providers.items()
        }


# Global adapter instance
llm_adapter = LLMAdapter()
