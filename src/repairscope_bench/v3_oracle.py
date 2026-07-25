from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from itertools import product
import json
from typing import Any

from .v3_constraints import check_active_records, check_v3_constraints
from .v3_environment import (
    NativeRecoveryEnvironmentV3,
    term_charge_minor,
    term_credit_minor,
    term_triggered,
)


@dataclass
class V3OracleResult:
    feasible: bool
    unique: bool
    gold: dict[str, Any] | None
    feasible_terminals: list[dict[str, Any]]
    feasible_scope_count: int
    assignment_count: int
    replay_count: int
    second_best_cost_minor: int | None
    cost_margin_minor: int | None
    required_margin_minor: int

    @property
    def optimal_scopes(self) -> list[dict[str, Any]]:
        return [deepcopy(self.gold["scope_signature"])] if self.gold else []

    @property
    def optimal_plans(self) -> list[list[dict[str, Any]]]:
        return [deepcopy(self.gold["tool_calls"])] if self.gold else []

    def as_dict(self) -> dict[str, Any]:
        return {
            "feasible": self.feasible,
            "unique": self.unique,
            "gold": deepcopy(self.gold),
            "feasible_terminals": deepcopy(self.feasible_terminals),
            "feasible_scope_count": self.feasible_scope_count,
            "assignment_count": self.assignment_count,
            "replay_count": self.replay_count,
            "second_best_cost_minor": self.second_best_cost_minor,
            "cost_margin_minor": self.cost_margin_minor,
            "required_margin_minor": self.required_margin_minor,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> V3OracleResult:
        return cls(
            feasible=bool(raw["feasible"]),
            unique=bool(raw["unique"]),
            gold=deepcopy(raw.get("gold")),
            feasible_terminals=deepcopy(raw["feasible_terminals"]),
            feasible_scope_count=int(raw["feasible_scope_count"]),
            assignment_count=int(raw["assignment_count"]),
            replay_count=int(raw["replay_count"]),
            second_best_cost_minor=raw.get("second_best_cost_minor"),
            cost_margin_minor=raw.get("cost_margin_minor"),
            required_margin_minor=int(raw["required_margin_minor"]),
        )


_CACHE: dict[str, V3OracleResult] = {}


def clear_v3_oracle_cache() -> None:
    _CACHE.clear()


def solve_task_v3(task: dict[str, Any]) -> V3OracleResult:
    public = {key: value for key, value in task.items() if not key.startswith("_")}
    key = json.dumps(
        public, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if key not in _CACHE:
        _CACHE[key] = _solve(public)
    return deepcopy(_CACHE[key])


def _solve(task: dict[str, Any]) -> V3OracleResult:
    terminals, assignments = _enumerate_terminals(task)
    scope_best: dict[str, dict[str, Any]] = {}
    for terminal in terminals:
        prior = scope_best.get(terminal["scope_key"])
        if prior is None or terminal["incremental_cost_minor"] < prior[
            "incremental_cost_minor"
        ]:
            scope_best[terminal["scope_key"]] = terminal
    candidates = sorted(
        scope_best.values(),
        key=lambda item: (item["incremental_cost_minor"], item["scope_key"]),
    )
    replay_count = 0
    replayed: list[dict[str, Any]] = []
    for candidate in candidates:
        replay_count += 1
        checked = _replay_terminal(task, candidate)
        if checked is not None:
            replayed.append(checked)
    replayed.sort(
        key=lambda item: (item["incremental_cost_minor"], item["scope_key"])
    )

    boundary_value = sum(
        int(item["paid_minor"]) for item in task["boundary_commitments"]
    )
    required_margin = max(1000, boundary_value // 100)
    if not replayed:
        return V3OracleResult(
            False,
            False,
            None,
            [],
            0,
            assignments,
            replay_count,
            None,
            None,
            required_margin,
        )
    best_cost = replayed[0]["incremental_cost_minor"]
    best = [
        item for item in replayed if item["incremental_cost_minor"] == best_cost
    ]
    second_cost = next(
        (
            item["incremental_cost_minor"]
            for item in replayed
            if item["incremental_cost_minor"] > best_cost
        ),
        None,
    )
    margin = second_cost - best_cost if second_cost is not None else None
    unique = len(best) == 1 and margin is not None and margin >= required_margin
    return V3OracleResult(
        True,
        unique,
        deepcopy(best[0]) if unique else None,
        replayed,
        len(replayed),
        assignments,
        replay_count,
        second_cost,
        margin,
        required_margin,
    )


def _enumerate_terminals(
    task: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    boundary = task["boundary_commitments"]
    options = [
        (option_id, metadata)
        for option_id, metadata in task["option_metadata"].items()
        if metadata.get("available", False)
        and option_id not in {item["option_id"] for item in boundary}
        and metadata.get("candidate", False)
    ]
    terminals: list[dict[str, Any]] = []
    assignments = 0
    for keep_bits in product((False, True), repeat=len(boundary)):
        changed = {
            item["entity_id"]
            for item, keep in zip(boundary, keep_bits, strict=True)
            if not keep
        }
        kept = [
            _boundary_active(item)
            for item, keep in zip(boundary, keep_bits, strict=True)
            if keep
        ]
        for option_bits in product((False, True), repeat=len(options)):
            assignments += 1
            selected = [
                item
                for item, use in zip(options, option_bits, strict=True)
                if use
            ]
            active = kept + [
                _option_active(option_id, metadata)
                for option_id, metadata in selected
            ]
            passed, _ = check_active_records(task, active)
            if not passed:
                continue
            scope = {
                "boundary": {
                    item["entity_id"]: (
                        "KEEP" if item["entity_id"] not in changed else "CANCEL"
                    )
                    for item in boundary
                },
                "added_option_ids": sorted(
                    option_id for option_id, _metadata in selected
                ),
            }
            cost = _static_cost(task, changed, selected, scope, active)
            calls = _tool_calls(task, changed, selected)
            terminals.append(
                {
                    "scope_signature": scope,
                    "scope_key": scope_key(scope),
                    "incremental_cost_minor": cost,
                    "changed_boundary_entities": sorted(changed),
                    "active_option_ids": sorted(
                        item["option_id"] for item in active
                    ),
                    "tool_calls": calls,
                    "minimum_mutations": len(changed) + len(selected),
                    "source": "declarative",
                }
            )
    return terminals, assignments


def _static_cost(
    task: dict[str, Any],
    changed: set[str],
    selected: list[tuple[str, dict[str, Any]]],
    scope: dict[str, Any],
    active: list[dict[str, Any]],
) -> int:
    refund = sum(
        int(item["refund_minor"])
        for item in task["boundary_commitments"]
        if item["entity_id"] in changed
    )
    purchase = sum(
        int(metadata["total_charge_minor"])
        for _option_id, metadata in selected
    )
    settlement = sum(
        term_charge_minor(term) - term_credit_minor(term)
        for term in task.get("economic_terms", [])
        if term_triggered(task, term, scope, active)
    )
    return purchase - refund + settlement


def _replay_terminal(
    task: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any] | None:
    environment = NativeRecoveryEnvironmentV3(task)
    for call in candidate["tool_calls"]:
        result = environment.execute_tool(
            call["name"], deepcopy(call.get("arguments", {}))
        )
        if not result.ok:
            return None
    passed, _ = check_v3_constraints(task, environment)
    if not passed:
        return None
    observed_scope = environment.canonical_scope()
    if scope_key(observed_scope) != candidate["scope_key"]:
        return None
    observed_cost = environment.incremental_recovery_cost_minor
    if observed_cost != candidate["incremental_cost_minor"]:
        raise RuntimeError(
            f"{task['task_id']}: declarative cost "
            f"{candidate['incremental_cost_minor']} != replay {observed_cost}"
        )
    replayed = deepcopy(candidate)
    replayed["source"] = "tool_replay"
    replayed["state_fingerprint"] = environment.state_fingerprint()
    replayed["economic_events"] = environment.economic_events()
    return replayed


def _tool_calls(
    task: dict[str, Any],
    changed: set[str],
    selected: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    if task["domain"] == "travel":
        for entity_id in sorted(changed):
            calls.extend(
                [
                    {
                        "name": "get_travel_terms",
                        "arguments": {"record_id": entity_id},
                    },
                    {
                        "name": "preview_travel_cancellation",
                        "arguments": {"reservation_id": entity_id},
                    },
                    {
                        "name": "cancel_travel_reservation",
                        "arguments": {
                            "reservation_id": entity_id,
                            "confirm": True,
                        },
                    },
                ]
            )
        for option_id, _metadata in sorted(selected):
            calls.append(
                {
                    "name": "book_travel_option",
                    "arguments": {
                        "option_id": option_id,
                        "user_id": task["actor_id"],
                    },
                }
            )
    else:
        for entity_id in sorted(changed):
            calls.extend(
                [
                    {
                        "name": "get_product_terms",
                        "arguments": {"record_id": entity_id},
                    },
                    {
                        "name": "preview_product_return",
                        "arguments": {"item_id": entity_id},
                    },
                    {
                        "name": "return_product",
                        "arguments": {
                            "item_id": entity_id,
                            "confirm": True,
                        },
                    },
                ]
            )
        for option_id, _metadata in sorted(selected):
            calls.append(
                {
                    "name": "purchase_product_option",
                    "arguments": {
                        "product_id": option_id,
                        "customer_id": task["actor_id"],
                    },
                }
            )
    return calls


def _boundary_active(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_id": item["entity_id"],
        "option_id": item["option_id"],
        "category": item["slot"],
        "provides": deepcopy(item["provides"]),
        "attributes": deepcopy(item.get("attributes", {})),
        "paid_minor": int(item["paid_minor"]),
    }


def _option_active(
    option_id: str, metadata: dict[str, Any]
) -> dict[str, Any]:
    return {
        "entity_id": f"NEW:{option_id}",
        "option_id": option_id,
        "category": metadata["slot"],
        "provides": deepcopy(metadata["provides"]),
        "attributes": deepcopy(metadata.get("attributes", {})),
        "paid_minor": int(metadata["total_charge_minor"]),
    }


def scope_key(scope: dict[str, Any]) -> str:
    return json.dumps(
        scope, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


__all__ = [
    "V3OracleResult",
    "clear_v3_oracle_cache",
    "scope_key",
    "solve_task_v3",
]
