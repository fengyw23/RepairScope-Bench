from __future__ import annotations

from copy import deepcopy
from typing import Any


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "query_state",
        "description": (
            "Read the authoritative post-failure commitments and financial ledger. "
            "Use this before making irreversible changes."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_options",
        "description": "List current options and prices for one required slot.",
        "parameters": {
            "type": "object",
            "properties": {"slot": {"type": "string"}},
            "required": ["slot"],
            "additionalProperties": False,
        },
    },
    {
        "name": "cancel",
        "description": (
            "Cancel one active commitment. The stated refund is applied immediately."
        ),
        "parameters": {
            "type": "object",
            "properties": {"commitment_id": {"type": "string"}},
            "required": ["commitment_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "book",
        "description": "Book an available option and create a persistent commitment.",
        "parameters": {
            "type": "object",
            "properties": {"option_id": {"type": "string"}},
            "required": ["option_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "modify",
        "description": (
            "Modify an active commitment in place when an explicit rule permits it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "commitment_id": {"type": "string"},
                "to_option_id": {"type": "string"},
            },
            "required": ["commitment_id", "to_option_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "finish",
        "description": (
            "Declare recovery complete. Call only after the final state satisfies "
            "the instruction."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "report_infeasible",
        "description": (
            "Declare that no safe constraint-satisfying repair exists. Do not destroy "
            "existing commitments before making this declaration."
        ),
        "parameters": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
            "additionalProperties": False,
        },
    },
]


def responses_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": item["name"],
            "description": item["description"],
            "parameters": deepcopy(item["parameters"]),
            "strict": True,
        }
        for item in TOOL_DEFINITIONS
    ]


def chat_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": item["name"],
                "description": item["description"],
                "parameters": deepcopy(item["parameters"]),
            },
        }
        for item in TOOL_DEFINITIONS
    ]


def anthropic_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": item["name"],
            "description": item["description"],
            "input_schema": deepcopy(item["parameters"]),
        }
        for item in TOOL_DEFINITIONS
    ]
