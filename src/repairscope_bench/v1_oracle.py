from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from itertools import product
import json
from typing import Any

from .v1_environment import (
    CommitmentRecoveryEnvironment,
    EconomicVector,
    contract_triggered,
    snapshot_hash,
)


@dataclass
class V1OracleResult:
    feasible: bool
    frontier: list[dict[str, Any]]
    independent_frontier: list[dict[str, Any]]
    feasible_terminals: list[dict[str, Any]]
    feasible_terminal_count: int
    feasible_scope_count: int
    assignment_count: int
    explored_state_count: int

    @property
    def frontier_vectors(self) -> list[EconomicVector]:
        return [_vector(item) for item in self.frontier]

    @property
    def optimal_scopes(self) -> list[dict[str, str]]:
        return _deduplicate([item["scope"] for item in self.frontier])

    def as_dict(self) -> dict[str, Any]:
        return {
            "feasible": self.feasible,
            "frontier": deepcopy(self.frontier),
            "independent_frontier": deepcopy(self.independent_frontier),
            "feasible_terminals": deepcopy(self.feasible_terminals),
            "feasible_terminal_count": self.feasible_terminal_count,
            "feasible_scope_count": self.feasible_scope_count,
            "assignment_count": self.assignment_count,
            "explored_state_count": self.explored_state_count,
        }


_CACHE: dict[str, V1OracleResult] = {}


def clear_v1_oracle_cache() -> None:
    _CACHE.clear()


def solve_task_v1(task: dict[str, Any]) -> V1OracleResult:
    public = {key: value for key, value in task.items() if not key.startswith("_")}
    key = json.dumps(public, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if key not in _CACHE:
        _CACHE[key] = _solve(public)
    return deepcopy(_CACHE[key])


def _solve(task: dict[str, Any]) -> V1OracleResult:
    assignments, assignment_count = _terminal_assignment_solver(task)
    searched, explored = _public_tool_state_search(task)
    frontier = _pareto_frontier(assignments)
    independent = _pareto_frontier(searched)
    return V1OracleResult(
        feasible=bool(assignments),
        frontier=frontier,
        independent_frontier=independent,
        feasible_terminals=assignments,
        feasible_terminal_count=len(assignments),
        feasible_scope_count=len(_deduplicate([item["scope"] for item in assignments])),
        assignment_count=assignment_count,
        explored_state_count=explored,
    )


def _terminal_assignment_solver(
    task: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    """Independent terminal-state enumerator; it never invokes runtime tools."""
    boundary = task["boundary_commitments"]
    inventory = [item for item in task["inventory"] if item.get("available", False)]
    terminals: list[dict[str, Any]] = []
    assignment_count = 0
    buy_subsets = _compatible_option_subsets(task, inventory)
    for keep_bits in product((False, True), repeat=len(boundary)):
        changed = {
            item["entity_id"]
            for item, keep in zip(boundary, keep_bits, strict=True)
            if not keep
        }
        kept = [
            _boundary_as_active(item)
            for item, keep in zip(boundary, keep_bits, strict=True)
            if keep
        ]
        for bought in buy_subsets:
            assignment_count += 1
            active = kept + bought
            if not _assignment_goal_pass(task, active):
                continue
            vector = _assignment_economics(task, changed, bought)
            terminals.append(
                {
                    "economic_vector": vector.as_dict(),
                    "scope": _assignment_scope(boundary, changed, bought),
                    "active_option_ids": sorted(item["option_id"] for item in active),
                    "changed_boundary_entities": sorted(changed),
                    "tool_calls": _canonical_tool_calls(task, changed, bought),
                    "state_hash": _terminal_hash(changed, bought),
                }
            )
    return _deduplicate_terminals(terminals), assignment_count


def _compatible_option_subsets(
    task: dict[str, Any], inventory: list[dict[str, Any]]
) -> list[list[dict[str, Any]]]:
    forbidden = {
        frozenset(rule["option_ids"])
        for rule in task.get("compatibility_rules", [])
        if rule["type"] == "forbid_pair"
    }
    result: list[list[dict[str, Any]]] = []

    def visit(index: int, selected: list[dict[str, Any]]) -> None:
        if index == len(inventory):
            result.append(
                [
                    _option_as_active(item, position)
                    for position, item in enumerate(selected, start=1)
                ]
            )
            return
        visit(index + 1, selected)
        candidate = inventory[index]
        if any(
            frozenset({candidate["option_id"], item["option_id"]}) in forbidden
            for item in selected
        ):
            return
        selected.append(candidate)
        visit(index + 1, selected)
        selected.pop()

    visit(0, [])
    return result


def _public_tool_state_search(
    task: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    """Second Oracle: enumerate legal mutations and replay public tools."""
    names = CommitmentRecoveryEnvironment(task).names
    boundary_ids = [item["entity_id"] for item in task["boundary_commitments"]]
    inventory_records = [
        item for item in task["inventory"] if item.get("available", False)
    ]
    compatible_subsets = _compatible_option_subsets(task, inventory_records)
    terminals: list[dict[str, Any]] = []
    explored = 0
    for cancel_bits in product((False, True), repeat=len(boundary_ids)):
        cancelled = frozenset(
            entity_id
            for entity_id, cancel in zip(boundary_ids, cancel_bits, strict=True)
            if cancel
        )
        for subset in compatible_subsets:
            explored += 1
            purchased = frozenset(item["option_id"] for item in subset)
            environment = CommitmentRecoveryEnvironment(task)
            valid = True
            for entity_id in sorted(cancelled):
                result = environment.execute_tool(
                    names["cancel"],
                    {names["id"]: entity_id, "confirm": True},
                )
                if not result.ok:
                    valid = False
                    break
            if not valid:
                continue
            for option_id in sorted(purchased):
                result = environment.execute_tool(
                    names["book"], {names["option"]: option_id}
                )
                if not result.ok:
                    valid = False
                    break
            if not valid:
                continue
            passed, _ = environment.goal_status()
            if not passed:
                continue
            active_option_ids = sorted(
                item["option_id"] for item in environment.active_commitments()
            )
            terminals.append(
                {
                    "economic_vector": environment.economic_vector.as_dict(),
                    "scope": environment.dispositions(),
                    "active_option_ids": active_option_ids,
                    "changed_boundary_entities": sorted(cancelled),
                    "tool_calls": _calls_from_event_log(environment.event_log),
                    "state_hash": _terminal_hash_from_options(
                        cancelled, purchased
                    ),
                }
            )
    return _deduplicate_terminals(terminals), explored


def _assignment_goal_pass(
    task: dict[str, Any], active: list[dict[str, Any]]
) -> bool:
    totals: dict[str, int] = {}
    for item in active:
        for capability, amount in item["provides"].items():
            totals[capability] = totals.get(capability, 0) + int(amount)
    for requirement in task["hard_goals"]["capabilities"]:
        observed = totals.get(requirement["capability"], 0)
        if observed < int(requirement.get("min", 0)):
            return False
        if requirement.get("max") is not None and observed > int(
            requirement["max"]
        ):
            return False
    active_options = {item["option_id"] for item in active}
    for rule in task.get("compatibility_rules", []):
        if rule["type"] == "forbid_pair":
            if set(rule["option_ids"]).issubset(active_options):
                return False
        elif rule["type"] == "requires_any":
            if (
                rule["if_option_id"] in active_options
                and not active_options.intersection(rule["any_option_ids"])
            ):
                return False
        elif rule["type"] == "requires_all":
            if (
                rule["if_option_id"] in active_options
                and not set(rule["all_option_ids"]).issubset(active_options)
            ):
                return False
        elif rule["type"] == "requires_bridge":
            if set(rule["option_ids"]).issubset(active_options) and not (
                active_options.intersection(rule["bridge_option_ids"])
            ):
                return False
    for requirement in task["hard_goals"].get("attribute_requirements", []):
        providers = [
            item
            for item in active
            if item["provides"].get(requirement["capability"], 0) > 0
        ]
        if not providers:
            return False
        for item in providers:
            observed = item.get("attributes", {}).get(requirement["attribute"])
            op = requirement["op"]
            expected = requirement["value"]
            if op == "eq" and observed != expected:
                return False
            if op == "le" and (observed is None or observed > expected):
                return False
            if op == "ge" and (observed is None or observed < expected):
                return False
            if op == "in" and observed not in expected:
                return False
    max_total = task["hard_goals"].get("max_active_value_cents")
    if max_total is not None and sum(int(item["paid_cents"]) for item in active) > int(
        max_total
    ):
        return False
    return True


def _assignment_economics(
    task: dict[str, Any],
    changed: set[str],
    bought: list[dict[str, Any]],
) -> EconomicVector:
    boundary = {item["entity_id"]: item for item in task["boundary_commitments"]}
    loss = sum(
        int(boundary[item]["paid_cents"]) - int(boundary[item]["refund_cents"])
        for item in changed
    )
    outlay = -sum(int(boundary[item]["refund_cents"]) for item in changed)
    for item in bought:
        outlay += int(item["paid_cents"])
    for contract in task["contracts"]:
        if contract_triggered(
            contract["trigger"],
            changed,
            task["boundary_commitments"],
            {item["option_id"] for item in bought}
            | {
                item["option_id"]
                for entity_id, item in boundary.items()
                if entity_id not in changed
            },
        ):
            charge = int(contract["charge_cents"])
            loss += charge
            outlay += charge
    return EconomicVector(loss, outlay)


def _assignment_scope(
    boundary: list[dict[str, Any]],
    changed: set[str],
    bought: list[dict[str, Any]],
) -> dict[str, str]:
    result = {}
    for item in boundary:
        entity_id = item["entity_id"]
        if entity_id not in changed:
            result[entity_id] = "KEEP"
        else:
            capability = item["primary_capability"]
            result[entity_id] = (
                "REPLACE"
                if any(new["provides"].get(capability, 0) > 0 for new in bought)
                else "CANCEL"
            )
    return result


def _canonical_tool_calls(
    task: dict[str, Any],
    changed: set[str],
    bought: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    names = CommitmentRecoveryEnvironment(task).names
    calls = []
    for entity_id in sorted(changed):
        calls.extend(
            [
                {
                    "name": names["preview"],
                    "arguments": {names["id"]: entity_id},
                },
                {
                    "name": names["cancel"],
                    "arguments": {names["id"]: entity_id, "confirm": True},
                },
            ]
        )
    for item in sorted(bought, key=lambda value: value["option_id"]):
        calls.append(
            {
                "name": names["book"],
                "arguments": {names["option"]: item["option_id"]},
            }
        )
    return calls


def _boundary_as_active(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_id": item["entity_id"],
        "option_id": item["option_id"],
        "paid_cents": int(item["paid_cents"]),
        "provides": deepcopy(item["provides"]),
        "attributes": deepcopy(item.get("attributes", {})),
    }


def _option_as_active(
    item: dict[str, Any], index: int
) -> dict[str, Any]:
    return {
        "entity_id": f"ASSIGN-{index:04d}",
        "option_id": item["option_id"],
        "paid_cents": int(item["upfront_cents"])
        + int(item.get("monthly_cents", 0))
        * int(item.get("horizon_months", 0)),
        "provides": deepcopy(item["provides"]),
        "attributes": deepcopy(item.get("attributes", {})),
    }


def _calls_from_event_log(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"name": item["tool"], "arguments": deepcopy(item["arguments"])}
        for item in events
        if item["state_changed"]
    ]


def _terminal_hash(
    changed: set[str], bought: list[dict[str, Any]]
) -> str:
    return _terminal_hash_from_options(
        frozenset(changed),
        frozenset(item["option_id"] for item in bought),
    )


def _terminal_hash_from_options(
    changed: frozenset[str] | set[str],
    purchased: frozenset[str] | set[str],
) -> str:
    return snapshot_hash(
        {
            "changed_boundary": sorted(changed),
            "purchased_options": sorted(purchased),
        }
    )


def _pareto_frontier(terminals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = [
        deepcopy(candidate)
        for candidate in terminals
        if not any(
            _vector(other).dominates(_vector(candidate))
            for other in terminals
        )
    ]
    return sorted(
        _deduplicate_terminals(result),
        key=lambda item: (
            item["economic_vector"]["irreversible_loss"],
            item["economic_vector"]["net_recovery_outlay"],
            item["state_hash"],
        ),
    )


def frontier_signature(
    frontier: list[dict[str, Any]],
) -> list[tuple[Any, ...]]:
    return sorted(
        (
            item["economic_vector"]["irreversible_loss"],
            item["economic_vector"]["net_recovery_outlay"],
            tuple(sorted(item["scope"].items())),
            tuple(item["active_option_ids"]),
        )
        for item in frontier
    )


def _vector(item: dict[str, Any]) -> EconomicVector:
    return EconomicVector(
        int(item["economic_vector"]["irreversible_loss"]),
        int(item["economic_vector"]["net_recovery_outlay"]),
    )


def _deduplicate_terminals(
    terminals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    result = []
    for item in terminals:
        key = (
            item["state_hash"],
            item["economic_vector"]["irreversible_loss"],
            item["economic_vector"]["net_recovery_outlay"],
        )
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _deduplicate(items: list[Any]) -> list[Any]:
    result = []
    for item in items:
        if item not in result:
            result.append(item)
    return result
