from __future__ import annotations

import unittest
from unittest.mock import patch

from repairscope_bench.providers import create_adapter
from repairscope_bench.providers.anthropic_messages import AnthropicMessagesAdapter
from repairscope_bench.providers.base import ToolResult
from repairscope_bench.providers.chat_completions import ChatCompletionsAdapter
from repairscope_bench.providers.openai_responses import OpenAIResponsesAdapter


class SequenceTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, url, headers, payload, timeout, max_retries):
        self.requests.append(
            {
                "url": url,
                "headers": headers,
                "payload": payload,
                "timeout": timeout,
                "max_retries": max_retries,
            }
        )
        return self.responses.pop(0)


class ProviderProtocolTest(unittest.TestCase):
    def test_generic_openai_compatible_gateway_factory(self) -> None:
        with patch.dict(
            "os.environ",
            {"OPENAI_COMPATIBLE_API_KEY": "secret"},
            clear=False,
        ):
            adapter = create_adapter(
                "openai-compatible",
                "gateway-model",
                base_url="https://gateway.example/v1",
            )
        self.assertIsInstance(adapter, ChatCompletionsAdapter)
        self.assertEqual(adapter.provider, "openai-compatible")
        self.assertEqual(
            adapter.endpoint, "https://gateway.example/v1/chat/completions"
        )

    def test_openai_replays_reasoning_and_function_output(self) -> None:
        transport = SequenceTransport(
            [
                {
                    "status": "completed",
                    "output": [
                        {"type": "reasoning", "id": "rs_1", "summary": []},
                        {
                            "type": "function_call",
                            "id": "fc_1",
                            "call_id": "call_1",
                            "name": "query_state",
                            "arguments": "{}",
                        },
                    ],
                    "usage": {"input_tokens": 10, "output_tokens": 3},
                },
                {
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {"type": "output_text", "text": "done"}
                            ],
                        }
                    ],
                    "usage": {"input_tokens": 15, "output_tokens": 2},
                },
            ]
        )
        adapter = OpenAIResponsesAdapter(
            "gpt-test", "secret", transport=transport
        )
        session = adapter.start_session("system", "user")
        first = session.advance()
        self.assertEqual(first.tool_calls[0].name, "query_state")
        second = session.advance(
            [ToolResult("call_1", "query_state", {"ok": True})]
        )
        self.assertEqual(second.text, "done")
        second_input = transport.requests[1]["payload"]["input"]
        self.assertTrue(any(item.get("type") == "reasoning" for item in second_input))
        self.assertTrue(
            any(item.get("type") == "function_call_output" for item in second_input)
        )
        self.assertFalse(transport.requests[0]["payload"]["parallel_tool_calls"])

    def test_openai_compatible_chat_loop(self) -> None:
        transport = SequenceTransport(
            [
                {
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_2",
                                        "type": "function",
                                        "function": {
                                            "name": "finish",
                                            "arguments": "{}",
                                        },
                                    }
                                ],
                            },
                        }
                    ],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 2},
                },
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "ok"},
                        }
                    ]
                },
            ]
        )
        adapter = ChatCompletionsAdapter(
            "deepseek",
            "deepseek-test",
            "secret",
            "https://api.example/v1",
            transport=transport,
        )
        session = adapter.start_session("system", "user")
        first = session.advance()
        self.assertEqual(first.tool_calls[0].name, "finish")
        session.advance([ToolResult("call_2", "finish", {"ok": True})])
        messages = transport.requests[1]["payload"]["messages"]
        self.assertEqual(messages[-1]["role"], "tool")
        self.assertEqual(messages[-1]["tool_call_id"], "call_2")

    def test_anthropic_tool_result_loop(self) -> None:
        transport = SequenceTransport(
            [
                {
                    "stop_reason": "tool_use",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "query_state",
                            "input": {},
                        }
                    ],
                    "usage": {"input_tokens": 8, "output_tokens": 2},
                },
                {
                    "stop_reason": "end_turn",
                    "content": [{"type": "text", "text": "done"}],
                    "usage": {"input_tokens": 9, "output_tokens": 1},
                },
            ]
        )
        adapter = AnthropicMessagesAdapter(
            "claude-test", "secret", transport=transport
        )
        session = adapter.start_session("system", "user")
        first = session.advance()
        self.assertEqual(first.tool_calls[0].call_id, "toolu_1")
        second = session.advance(
            [ToolResult("toolu_1", "query_state", {"ok": True})]
        )
        self.assertEqual(second.text, "done")
        last_message = transport.requests[1]["payload"]["messages"][-1]
        self.assertEqual(last_message["content"][0]["type"], "tool_result")
        self.assertEqual(
            last_message["content"][0]["tool_use_id"], "toolu_1"
        )

    def test_qwen_specific_thinking_flag_is_forwarded(self) -> None:
        transport = SequenceTransport(
            [
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "done"},
                        }
                    ]
                }
            ]
        )
        adapter = ChatCompletionsAdapter(
            "qwen",
            "qwen-test",
            "secret",
            "https://dashscope.example/v1",
            extra_body={"enable_thinking": False},
            transport=transport,
        )
        adapter.start_session("system", "user").advance()
        self.assertFalse(transport.requests[0]["payload"]["enable_thinking"])


if __name__ == "__main__":
    unittest.main()
