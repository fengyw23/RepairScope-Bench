from __future__ import annotations

from copy import deepcopy
from typing import Any

from .oracle import solve_task


def make_actions(task: dict[str, Any], strategy: str) -> list[dict[str, Any]]:
    if strategy == "oracle":
        oracle = solve_task(task)
        if not oracle.feasible:
            return [
                {
                    "action": "report_infeasible",
                    "args": {"reason": "No constraint-satisfying repair exists."},
                }
            ]
        return oracle.optimal_plans[0] + [{"action": "finish", "args": {}}]
    if strategy == "no_repair":
        return [{"action": "finish", "args": {}}]
    if strategy == "local_repair":
        return _local_repair(task)
    if strategy == "full_rollback":
        return _full_rollback(task)
    if strategy == "dependency_repair":
        return _dependency_repair(task)
    if strategy == "global_cost":
        cost_task = deepcopy(task)
        cost_task["objective"]["terms"] = [
            "financial_cost",
            "recovery_loss",
            "mutated_prior_commitments",
            "state_changing_actions",
        ]
        oracle = solve_task(cost_task)
        if not oracle.feasible:
            return [
                {
                    "action": "report_infeasible",
                    "args": {"reason": "No constraint-satisfying repair exists."},
                }
            ]
        return oracle.optimal_plans[0] + [{"action": "finish", "args": {}}]
    raise ValueError(f"Unknown baseline strategy: {strategy}")


def _local_repair(task: dict[str, Any]) -> list[dict[str, Any]]:
    active_slots = {
        item["slot"]
        for item in task["failure_snapshot"]["commitments"]
        if item["status"] == "confirmed"
    }
    actions: list[dict[str, Any]] = []
    for slot in task["required_slots"]:
        if slot in active_slots:
            continue
        option = _cheapest_available(task, slot)
        if option is not None:
            actions.append({"action": "book", "args": {"option_id": option["option_id"]}})
    actions.append({"action": "finish", "args": {}})
    return actions


def _full_rollback(task: dict[str, Any]) -> list[dict[str, Any]]:
    actions = [
        {
            "action": "cancel",
            "args": {"commitment_id": item["commitment_id"]},
        }
        for item in task["failure_snapshot"]["commitments"]
        if item["status"] == "confirmed"
    ]
    for slot in task["required_slots"]:
        option = _cheapest_available(task, slot)
        if option is not None:
            actions.append({"action": "book", "args": {"option_id": option["option_id"]}})
    actions.append({"action": "finish", "args": {}})
    return actions


def _dependency_repair(task: dict[str, Any]) -> list[dict[str, Any]]:
    affected = set(task.get("failure", {}).get("affected_slots", []))
    actions: list[dict[str, Any]] = []
    active_slots: set[str] = set()
    for item in task["failure_snapshot"]["commitments"]:
        if item["status"] != "confirmed":
            continue
        if item["slot"] in affected:
            actions.append(
                {
                    "action": "cancel",
                    "args": {"commitment_id": item["commitment_id"]},
                }
            )
        else:
            active_slots.add(item["slot"])
    for slot in task["required_slots"]:
        if slot in active_slots:
            continue
        option = _cheapest_available(task, slot)
        if option is not None:
            actions.append({"action": "book", "args": {"option_id": option["option_id"]}})
    actions.append({"action": "finish", "args": {}})
    return actions


def _cheapest_available(
    task: dict[str, Any], slot: str
) -> dict[str, Any] | None:
    options = [
        option
        for option in task["catalog"]
        if option["slot"] == slot and option.get("available", False)
    ]
    return min(options, key=lambda option: option["price"]) if options else None
