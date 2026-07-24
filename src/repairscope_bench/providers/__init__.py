from __future__ import annotations

import os
from typing import Any

from .anthropic_messages import AnthropicMessagesAdapter
from .base import ModelAdapter, ProviderError, Transport, request_json
from .chat_completions import ChatCompletionsAdapter
from .openai_responses import OpenAIResponsesAdapter


PROVIDER_DEFAULTS = {
    "openai": {
        "key_env": "OPENAI_API_KEY",
        "base_env": "OPENAI_BASE_URL",
        "base_url": "https://api.openai.com/v1",
    },
    "anthropic": {
        "key_env": "ANTHROPIC_API_KEY",
        "base_env": "ANTHROPIC_BASE_URL",
        "base_url": "https://api.anthropic.com/v1",
    },
    "qwen": {
        "key_env": "DASHSCOPE_API_KEY",
        "base_env": "DASHSCOPE_BASE_URL",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
    "deepseek": {
        "key_env": "DEEPSEEK_API_KEY",
        "base_env": "DEEPSEEK_BASE_URL",
        "base_url": "https://api.deepseek.com",
    },
    "openai-compatible": {
        "key_env": "OPENAI_COMPATIBLE_API_KEY",
        "base_env": "OPENAI_COMPATIBLE_BASE_URL",
        "base_url": None,
    },
}


def create_adapter(
    provider: str,
    model: str,
    *,
    base_url: str | None = None,
    timeout: float = 120,
    max_retries: int = 3,
    max_output_tokens: int = 4096,
    reasoning_effort: str | None = None,
    qwen_enable_thinking: bool | None = None,
    transport: Transport = request_json,
) -> ModelAdapter:
    name = provider.lower()
    if name not in PROVIDER_DEFAULTS:
        raise ProviderError(f"Unsupported provider: {provider}")
    config = PROVIDER_DEFAULTS[name]
    api_key = os.getenv(config["key_env"], "")
    if not api_key:
        raise ProviderError(
            f"{config['key_env']} is not set; configure it in the environment "
            f"before running {name}"
        )
    resolved_base = (
        base_url
        or os.getenv(config["base_env"])
        or config["base_url"]
    )
    if not resolved_base:
        raise ProviderError(
            f"No base URL configured for {name}; pass --base-url or set "
            f"{config['base_env']}"
        )
    common: dict[str, Any] = {
        "model": model,
        "api_key": api_key,
        "base_url": resolved_base,
        "timeout": timeout,
        "max_retries": max_retries,
        "max_output_tokens": max_output_tokens,
        "transport": transport,
    }
    if name == "openai":
        return OpenAIResponsesAdapter(
            **common, reasoning_effort=reasoning_effort
        )
    if name == "anthropic":
        return AnthropicMessagesAdapter(**common)
    extra_body: dict[str, Any] = {}
    if name == "qwen" and qwen_enable_thinking is not None:
        extra_body["enable_thinking"] = qwen_enable_thinking
    return ChatCompletionsAdapter(
        provider=name, **common, extra_body=extra_body
    )


__all__ = [
    "create_adapter",
    "ModelAdapter",
    "ProviderError",
    "OpenAIResponsesAdapter",
    "AnthropicMessagesAdapter",
    "ChatCompletionsAdapter",
]
