from __future__ import annotations

from copy import deepcopy
from typing import Any


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "list_commitments",
        "description": "List the persistent commitments that currently exist.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_commitment_details",
        "description": "Read the service or product details of one commitment.",
        "parameters": {
            "type": "object",
            "properties": {"commitment_id": {"type": "string"}},
            "required": ["commitment_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_cancellation_quote",
        "description": (
            "Get the current refund and irrecoverable loss for cancelling one "
            "active commitment. This does not change state."
        ),
        "parameters": {
            "type": "object",
            "properties": {"commitment_id": {"type": "string"}},
            "required": ["commitment_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_options",
        "description": "Search currently available options for one service or product slot.",
        "parameters": {
            "type": "object",
            "properties": {"slot": {"type": "string"}},
            "required": ["slot"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_modification_quote",
        "description": (
            "Check whether one commitment can be changed in place to a specific "
            "option and obtain the current quote. This does not change state."
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
        "name": "check_compatibility",
        "description": "Check whether two specific product or service options are compatible.",
        "parameters": {
            "type": "object",
            "properties": {
                "left_option_id": {"type": "string"},
                "right_option_id": {"type": "string"},
            },
            "required": ["left_option_id", "right_option_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_cost_summary",
        "description": "Read the current task-level cash total without changing state.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "cancel",
        "description": "Cancel one active commitment and apply its current refund.",
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
        "description": "Declare that the requested task is complete.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "report_infeasible",
        "description": "Declare that the requested task cannot be completed.",
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
