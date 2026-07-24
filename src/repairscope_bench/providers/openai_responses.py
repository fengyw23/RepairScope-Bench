from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from ..tools import responses_tools
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


class OpenAIResponsesAdapter:
    provider = "openai"

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 120,
        max_retries: int = 3,
        max_output_tokens: int = 4096,
        reasoning_effort: str | None = None,
        transport: Transport = request_json,
    ):
        self.model = model
        self.api_key = api_key
        self.endpoint = normalize_endpoint(base_url, "responses")
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_output_tokens = max_output_tokens
        self.reasoning_effort = reasoning_effort
        self.transport = transport

    def start_session(
        self, system_prompt: str, user_prompt: str
    ) -> "OpenAIResponsesSession":
        return OpenAIResponsesSession(self, system_prompt, user_prompt)


class OpenAIResponsesSession:
    def __init__(
        self,
        adapter: OpenAIResponsesAdapter,
        system_prompt: str,
        user_prompt: str,
    ):
        self.adapter = adapter
        self.instructions = system_prompt
        self.input_items: list[dict[str, Any]] = [
            {"role": "user", "content": user_prompt}
        ]

    def advance(self, tool_results: list[ToolResult] | None = None) -> ModelTurn:
        for result in tool_results or []:
            self.input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": result.call_id,
                    "output": json.dumps(result.output, ensure_ascii=False),
                }
            )
        payload: dict[str, Any] = {
            "model": self.adapter.model,
            "instructions": self.instructions,
            "input": deepcopy(self.input_items),
            "tools": responses_tools(),
            "parallel_tool_calls": False,
            "max_output_tokens": self.adapter.max_output_tokens,
            "store": False,
        }
        if self.adapter.reasoning_effort:
            payload["reasoning"] = {"effort": self.adapter.reasoning_effort}
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
        output = response.get("output", [])
        if not isinstance(output, list):
            raise ProviderError("OpenAI response.output must be a list")
        self.input_items.extend(deepcopy(output))
        calls: list[ToolCall] = []
        text_parts: list[str] = []
        for item in output:
            if item.get("type") == "function_call":
                arguments, error = parse_json_arguments(item.get("arguments"))
                calls.append(
                    ToolCall(
                        str(item.get("call_id", item.get("id", ""))),
                        str(item.get("name", "")),
                        arguments,
                        error,
                    )
                )
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if content.get("type") in {"output_text", "text"}:
                        text_parts.append(str(content.get("text", "")))
        return ModelTurn(
            text="\n".join(part for part in text_parts if part),
            tool_calls=calls,
            usage=_openai_usage(response.get("usage", {})),
            stop_reason=response.get("status"),
        )


def _openai_usage(raw: dict[str, Any]) -> dict[str, int | float]:
    return {
        key: raw[key]
        for key in ("input_tokens", "output_tokens", "total_tokens")
        if key in raw
    }
