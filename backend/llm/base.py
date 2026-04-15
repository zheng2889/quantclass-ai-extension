"""LLM base interface."""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class LLMUsage:
    """LLM token usage."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    """LLM response."""
    content: str
    model: str
    usage: LLMUsage
    finish_reason: str = "stop"
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class LLMMessage:
    """LLM message."""
    role: str  # system, user, assistant
    content: str


class BaseLLM(ABC):
    """Base LLM interface."""
    
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        **kwargs
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.extra_params = kwargs
    
    @abstractmethod
    async def chat(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """Send chat completion request."""
        pass
    
    @abstractmethod
    async def chat_stream(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """Send streaming chat completion request."""
        pass
    
    @abstractmethod
    async def complete(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """Send completion request."""
        pass
    
    def format_messages(self, messages: List[LLMMessage]) -> List[Dict[str, str]]:
        """Format messages for API."""
        return [{"role": m.role, "content": m.content} for m in messages]
