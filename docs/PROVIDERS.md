# Provider Setup

The benchmark uses raw HTTPS with the Python standard library, so no provider
SDK is required. The implementation follows the providers' official tool-use
protocols:

- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
  with the Responses API;
- [Anthropic tool use](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/overview)
  with the Messages API;
- [Qwen function calling](https://help.aliyun.com/en/model-studio/qwen-function-calling)
  through DashScope's OpenAI-compatible API;
- [DeepSeek function calling](https://api-docs.deepseek.com/guides/function_calling)
  through its OpenAI-compatible API.

## Environment variables

| Provider | Required key | Optional base URL | Default base URL |
|---|---|---|---|
| OpenAI | `OPENAI_API_KEY` | `OPENAI_BASE_URL` | `https://api.openai.com/v1` |
| Anthropic | `ANTHROPIC_API_KEY` | `ANTHROPIC_BASE_URL` | `https://api.anthropic.com/v1` |
| Qwen | `DASHSCOPE_API_KEY` | `DASHSCOPE_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| DeepSeek | `DEEPSEEK_API_KEY` | `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` |
| Any OpenAI-compatible gateway | `OPENAI_COMPATIBLE_API_KEY` | `OPENAI_COMPATIBLE_BASE_URL` | no default; required |

`--base-url` overrides the environment variable. This is useful for another
DashScope region or an organization gateway. Keys are placed only in request
headers and never copied to experiment records.

For a third-party gateway, use the generic provider label so the run record
does not incorrectly claim that the request went directly to a model vendor:

```bash
export OPENAI_COMPATIBLE_API_KEY=...
repairscope run-suite data/v06 \
  --provider openai-compatible \
  --model YOUR_GATEWAY_MODEL_ID \
  --base-url https://gateway.example/v1 \
  --output-dir results/gateway-model
```

## Protocol differences handled by the adapter

OpenAI Responses returns flat `function_call` output items. The adapter replays
all output items, including reasoning items, and appends
`function_call_output` with the original `call_id`.

Anthropic returns `tool_use` content blocks. The adapter appends the complete
assistant content and replies with user-role `tool_result` blocks keyed by
`tool_use_id`.

Qwen and DeepSeek return Chat Completions `tool_calls`. The adapter appends the
assistant message and sends one `role=tool` message per `tool_call_id`.

The environment executes emitted calls serially because order matters for
side effects. OpenAI-compatible requests also set
`parallel_tool_calls=false`. OpenAI tools use strict JSON schemas.

## Reproducibility

Always record the exact model ID shown by the provider, not only a mutable
marketing alias. Use `--repeats` for stochastic runs. Each run stores:

- provider and model;
- exact model-visible system/user input;
- normalized token usage;
- model text, tool calls, tool results, and stop reasons;
- task turn limit and terminal-state score;
- complete evaluator score and environment event log.

By default the harness refuses to mix a new suite with an existing
`runs.jsonl`. Choose a new output directory or explicitly pass `--overwrite`.

CI validates protocol state machines with deterministic mock responses. It
does not make live calls. A live smoke test still requires valid credentials,
network access, billing, and access to the selected model.
