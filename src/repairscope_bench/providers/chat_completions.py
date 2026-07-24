from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from ..tools import chat_tools
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


class ChatCompletionsAdapter:
    def __init__(
        self,
        provider: str,
        model: str,
        api_key: str,
        base_url: str,
        timeout: float = 120,
        max_retries: int = 3,
        max_output_tokens: int = 4096,
        extra_body: dict[str, Any] | None = None,
        transport: Transport = request_json,
    ):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.endpoint = normalize_endpoint(base_url, "chat/completions")
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_output_tokens = max_output_tokens
        self.extra_body = deepcopy(extra_body or {})
        self.transport = transport

    def start_session(
        self,
        system_prompt: str,
        user_prompt: str,
        tool_definitions: list[dict[str, Any]] | None = None,
    ) -> "ChatCompletionsSession":
        return ChatCompletionsSession(
            self, system_prompt, user_prompt, tool_definitions
        )


class ChatCompletionsSession:
    def __init__(
        self,
        adapter: ChatCompletionsAdapter,
        system_prompt: str,
        user_prompt: str,
        tool_definitions: list[dict[str, Any]] | None,
    ):
        self.adapter = adapter
        self.tool_definitions = tool_definitions
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def advance(self, tool_results: list[ToolResult] | None = None) -> ModelTurn:
        for result in tool_results or []:
            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": result.call_id,
                    "name": result.name,
                    "content": json.dumps(result.output, ensure_ascii=False),
                }
            )
        payload: dict[str, Any] = {
            "model": self.adapter.model,
            "messages": deepcopy(self.messages),
            "tools": chat_tools(self.tool_definitions),
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "max_tokens": self.adapter.max_output_tokens,
        }
        payload.update(deepcopy(self.adapter.extra_body))
        response = self.adapter.transport(
            self.adapter.endpoint,
            {
                "Authorization": f"Bearer {self.adapter.api_key}",
                "Content-Type": "application/json",
            },
            payload,
            self.adapter.timeout,
            self.adapter.max_retries,
        )
        choices = response.get("choices", [])
        if not choices:
            raise ProviderError(f"{self.adapter.provider} returned no choices")
        choice = choices[0]
        message = choice.get("message", {})
        if not isinstance(message, dict):
            raise ProviderError("Provider returned an invalid assistant message")
        self.messages.append(deepcopy(message))
        calls: list[ToolCall] = []
        for item in message.get("tool_calls", []) or []:
            function = item.get("function", {})
            arguments, error = parse_json_arguments(function.get("arguments"))
            calls.append(
                ToolCall(
                    str(item.get("id", "")),
                    str(function.get("name", "")),
                    arguments,
                    error,
                )
            )
        content = message.get("content") or ""
        return ModelTurn(
            text=content if isinstance(content, str) else json.dumps(content),
            tool_calls=calls,
            usage=_chat_usage(response.get("usage", {})),
            stop_reason=choice.get("finish_reason"),
        )


def _chat_usage(raw: dict[str, Any]) -> dict[str, int | float]:
    mapping = {
        "prompt_tokens": "input_tokens",
        "completion_tokens": "output_tokens",
        "total_tokens": "total_tokens",
    }
    return {target: raw[source] for source, target in mapping.items() if source in raw}
