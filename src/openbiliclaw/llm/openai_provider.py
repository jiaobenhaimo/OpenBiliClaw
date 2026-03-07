"""OpenAI-compatible LLM provider.

Supports OpenAI API and any compatible APIs (e.g. DeepSeek, local vLLM).
"""

from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI

from .base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """OpenAI and compatible API provider."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: str = "",
        provider_name: str = "openai",
    ) -> None:
        self._model = model
        self._provider_name = provider_name
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url or None,
        )

    @property
    def name(self) -> str:
        return self._provider_name

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            provider=self._provider_name,
            usage=usage,
            raw=response,
        )


class DeepSeekProvider(OpenAIProvider):
    """DeepSeek provider (OpenAI-compatible API)."""

    def __init__(self, api_key: str, model: str = "deepseek-chat") -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            base_url="https://api.deepseek.com",
            provider_name="deepseek",
        )
