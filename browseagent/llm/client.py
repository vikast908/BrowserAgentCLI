"""Unified LLM client supporting LM Studio (local) and cloud providers."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel

from browseagent.config import Settings

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> str:
    """Extract JSON from LLM output that may contain thinking tags or extra text.

    Handles Qwen3's <think>...</think> tags, markdown code blocks, and
    other common LLM response patterns.
    """
    # Strip <think>...</think> blocks (Qwen3 reasoning)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Strip markdown code blocks: ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, flags=re.DOTALL)
    if match:
        text = match.group(1).strip()

    # If text doesn't start with {, try to find the first { ... } block
    if not text.startswith("{"):
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            text = match.group(0)

    return text


class LLMClient:
    """Async LLM client that works with OpenAI-compatible APIs and cloud providers."""

    def __init__(self, settings: Settings, provider: str | None = None, model: str | None = None) -> None:
        self.settings = settings
        self.provider = provider or settings.default_provider
        self.model = model or settings.default_model
        self._client = self._build_client()

    def _build_client(self) -> AsyncOpenAI:
        """Create the appropriate OpenAI-compatible client."""
        if self.provider == "lm_studio":
            return AsyncOpenAI(
                base_url=f"{self.settings.lm_studio_url}/v1",
                api_key="lm-studio",
            )
        elif self.provider == "openai":
            return AsyncOpenAI(api_key=self.settings.openai_api_key)
        elif self.provider == "anthropic":
            # Use anthropic SDK via OpenAI-compatible proxy is not ideal;
            # we handle Anthropic natively below
            return AsyncOpenAI(api_key=self.settings.openai_api_key)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    async def chat(
        self,
        messages: list[dict[str, Any]],
        response_schema: type[BaseModel] | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.1,
    ) -> str:
        """Send a chat completion request and return the response text.

        If response_schema is provided, requests JSON output and validates it.
        """
        if self.provider == "anthropic":
            return await self._chat_anthropic(messages, response_schema, max_tokens, temperature)

        return await self._chat_openai(messages, response_schema, max_tokens, temperature)

    async def _chat_openai(
        self,
        messages: list[dict[str, Any]],
        response_schema: type[BaseModel] | None,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Chat via OpenAI-compatible API (LM Studio or OpenAI)."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if response_schema is not None:
            if self.provider == "lm_studio":
                # LM Studio requires json_schema format with a schema definition
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_schema.__name__,
                        "schema": response_schema.model_json_schema(),
                    },
                }
            else:
                kwargs["response_format"] = {"type": "json_object"}

        response = await self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""

        if response_schema is not None:
            # Clean up LLM output and validate the JSON response
            content = _extract_json(content)
            parsed = json.loads(content)
            response_schema.model_validate(parsed)

        return content

    async def _chat_anthropic(
        self,
        messages: list[dict[str, Any]],
        response_schema: type[BaseModel] | None,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Chat via Anthropic API natively."""
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self.settings.anthropic_api_key)

        # Convert OpenAI message format to Anthropic format
        system_msg = ""
        anthropic_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"] if isinstance(msg["content"], str) else ""
            else:
                anthropic_messages.append(msg)

        if response_schema is not None and system_msg:
            system_msg += "\n\nYou MUST respond with valid JSON only. No other text."

        response = await client.messages.create(
            model=self.model or "claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_msg,
            messages=anthropic_messages,
        )

        content = response.content[0].text

        if response_schema is not None:
            parsed = json.loads(content)
            response_schema.model_validate(parsed)

        return content

    async def chat_structured(
        self,
        messages: list[dict[str, Any]],
        schema: type[BaseModel],
        max_tokens: int = 2000,
        temperature: float = 0.1,
        retries: int = 2,
    ) -> BaseModel:
        """Chat and return a validated Pydantic model instance.

        Retries on JSON parse / validation failure with a stricter prompt.
        """
        last_error: Exception | None = None

        for attempt in range(retries + 1):
            try:
                raw = await self.chat(messages, response_schema=schema, max_tokens=max_tokens, temperature=temperature)
                cleaned = _extract_json(raw)
                parsed = json.loads(cleaned)
                return schema.model_validate(parsed)
            except (json.JSONDecodeError, Exception) as exc:
                last_error = exc
                logger.warning("LLM JSON attempt %d failed: %s", attempt + 1, exc)
                # Add a retry hint to the messages
                if attempt < retries:
                    messages = messages + [
                        {"role": "assistant", "content": raw if "raw" in dir() else ""},
                        {
                            "role": "user",
                            "content": (
                                f"Your response was not valid JSON. Error: {exc}\n"
                                "Please respond with ONLY valid JSON matching the required schema."
                            ),
                        },
                    ]

        raise ValueError(f"Failed to get valid JSON after {retries + 1} attempts: {last_error}")
