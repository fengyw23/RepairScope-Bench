from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from ..tools import anthropic_tools
from .base import (
    ModelTurn,
    ProviderError,
    ToolCall,
    ToolResult,
    Transport,
    normalize_endpoint,
    parse_json_arguments,
    request_json,
)


class AnthropicMessagesAdapter:
    provider = "anthropic"

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = "https://api.anthropic.com/v1",
        timeout: float = 120,
        max_retries: int = 3,
        max_output_tokens: int = 4096,
        transport: Transport = request_json,
    ):
        self.model = model
        self.api_key = api_key
        self.endpoint = normalize_endpoint(base_url, "messages")
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_output_tokens = max_output_tokens
        self.transport = transport

    def start_session(
        self,
        system_prompt: str,
        user_prompt: str,
        tool_definitions: list[dict[str, Any]] | None = None,
    ) -> "AnthropicMessagesSession":
        return AnthropicMessagesSession(
            self, system_prompt, user_prompt, tool_definitions
        )


class AnthropicMessagesSession:
    def __init__(
        self,
        adapter: AnthropicMessagesAdapter,
        system_prompt: str,
        user_prompt: str,
        tool_definitions: list[dict[str, Any]] | None,
    ):
        self.adapter = adapter
        self.tool_definitions = tool_definitions
        self.system_prompt = system_prompt
        self.messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_prompt}
        ]

    def advance(self, tool_results: list[ToolResult] | None = None) -> ModelTurn:
        if tool_results:
            self.messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": result.call_id,
                            "content": json.dumps(result.output, ensure_ascii=False),
                        }
                        for result in tool_results
                    ],
                }
            )
        payload = {
            "model": self.adapter.model,
            "system": self.system_prompt,
            "messages": deepcopy(self.messages),
            "tools": anthropic_tools(self.tool_definitions),
            "tool_choice": {"type": "auto"},
            "max_tokens": self.adapter.max_output_tokens,
        }
        response = self.adapter.transport(
            self.adapter.endpoint,
            {
                "x-api-key": self.adapter.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            payload,
            self.adapter.timeout,
            self.adapter.max_retries,
        )
        content = response.get("content", [])
        if not isinstance(content, list):
            raise ProviderError("Anthropic response.content must be a list")
        self.messages.append({"role": "assistant", "content": deepcopy(content)})
        calls: list[ToolCall] = []
        text_parts: list[str] = []
        for block in content:
            if block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))
            if block.get("type") == "tool_use":
                arguments, error = parse_json_arguments(block.get("input"))
                calls.append(
                    ToolCall(
                        str(block.get("id", "")),
                        str(block.get("name", "")),
                        arguments,
                        error,
                    )
                )
        return ModelTurn(
            text="\n".join(part for part in text_parts if part),
            tool_calls=calls,
            usage=_anthropic_usage(response.get("usage", {})),
            stop_reason=response.get("stop_reason"),
        )


def _anthropic_usage(raw: dict[str, Any]) -> dict[str, int | float]:
    return {
        key: raw[key]
        for key in (
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        )
        if key in raw
    }
