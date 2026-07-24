from __future__ import annotations

from dataclasses import dataclass, field
import json
import time
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ProviderError(RuntimeError):
    """Raised for an unrecoverable model-provider request or response error."""


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any] | None
    parse_error: str | None = None


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    name: str
    output: dict[str, Any]


@dataclass
class ModelTurn:
    text: str
    tool_calls: list[ToolCall]
    usage: dict[str, int | float] = field(default_factory=dict)
    stop_reason: str | None = None


class ModelSession(Protocol):
    def advance(self, tool_results: list[ToolResult] | None = None) -> ModelTurn:
        ...


class ModelAdapter(Protocol):
    provider: str
    model: str

    def start_session(
        self,
        system_prompt: str,
        user_prompt: str,
        tool_definitions: list[dict[str, Any]] | None = None,
    ) -> ModelSession:
        ...


Transport = Callable[
    [str, dict[str, str], dict[str, Any], float, int], dict[str, Any]
]


def request_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
    max_retries: int,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        request = Request(url, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=timeout) as response:
                decoded = response.read().decode("utf-8")
            value = json.loads(decoded)
            if not isinstance(value, dict):
                raise ProviderError("Provider returned a non-object JSON response")
            return value
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:1000]
            last_error = ProviderError(
                f"HTTP {error.code} from model provider: {detail}"
            )
            retryable = error.code == 429 or error.code >= 500
            if not retryable or attempt == max_retries:
                raise last_error from error
        except (URLError, TimeoutError) as error:
            last_error = error
            if attempt == max_retries:
                raise ProviderError(f"Model provider connection failed: {error}") from error
        except json.JSONDecodeError as error:
            raise ProviderError("Provider returned invalid JSON") from error
        time.sleep(min(2**attempt, 8))
    raise ProviderError(f"Model provider request failed: {last_error}")


def parse_json_arguments(raw: Any) -> tuple[dict[str, Any] | None, str | None]:
    if isinstance(raw, dict):
        return raw, None
    if not isinstance(raw, str):
        return None, f"Tool arguments must be an object or JSON string, got {type(raw).__name__}"
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        return None, f"Invalid tool-argument JSON: {error}"
    if not isinstance(value, dict):
        return None, "Tool arguments must decode to a JSON object"
    return value, None


def normalize_endpoint(base_url: str, endpoint: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith(f"/{endpoint}"):
        return base
    return f"{base}/{endpoint}"
