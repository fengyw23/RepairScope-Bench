from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from itertools import product
import json
from typing import Any

from .constraints import check_constraints
from .environment import RepairEnvironment


@dataclass
class OracleResult:
    feasible: bool
    optimal_recovery_loss: int | float | None
    optimal_financial_cost: int | float | None
    minimum_feasible_financial_cost: int | float | None
    optimal_objective: tuple[int | float, ...] | None
    optimal_plans: list[list[dict[str, Any]]]
    optimal_scopes: list[dict[str, str]]
    feasible_plan_count: int
    feasible_scope_count: int
    raw_plan_count: int
    feasible_recovery_losses: list[int | float]
    feasible_objectives: list[tuple[int | float, ...]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "feasible": self.feasible,
            "optimal_recovery_loss": self.optimal_recovery_loss,
            "optimal_financial_cost": self.optimal_financial_cost,
            "minimum_feasible_financial_cost": self.minimum_feasible_financial_cost,
            "optimal_objective": list(self.optimal_objective)
            if self.optimal_objective is not None
            else None,
            "optimal_plans": self.optimal_plans,
            "optimal_scopes": self.optimal_scopes,
            "feasible_plan_count": self.feasible_plan_count,
            "feasible_scope_count": self.feasible_scope_count,
            "raw_plan_count": self.raw_plan_count,
            "feasible_recovery_losses": self.feasible_recovery_losses,
            "feasible_objectives": [
                list(objective) for objective in self.feasible_objectives
            ],
        }


_ORACLE_CACHE: dict[str, OracleResult] = {}


def solve_task(task: dict[str, Any]) -> OracleResult:
    """Solve a task exactly, reusing results across evaluator and baselines."""
    public_task = {key: value for key, value in task.items() if not key.startswith("_")}
    cache_key = json.dumps(public_task, sort_keys=True, separators=(",", ":"))
    if cache_key not in _ORACLE_CACHE:
        _ORACLE_CACHE[cache_key] = _solve_task(public_task)
    return deepcopy(_ORACLE_CACHE[cache_key])


def _solve_task(task: dict[str, Any]) -> OracleResult:
    slot_choices = [_choices_for_slot(task, slot) for slot in task["required_slots"]]
    raw_plan_count = 1
    for choices in slot_choices:
        raw_plan_count *= len(choices)
    feasible: list[
        tuple[
            tuple[int | float, ...],
            list[dict[str, Any]],
            dict[str, str],
            int | float,
            int | float,
        ]
    ] = []

    for combination in product(*slot_choices):
        actions = _merge_actions(combination)
        environment = RepairEnvironment(task)
        if not _run_valid_actions(environment, actions):
            continue
        passed, _ = check_constraints(task, environment)
        if not passed:
            continue
        objective = environment.objective_tuple()
        feasible.append(
            (
                objective,
                actions,
                environment.dispositions(),
                environment.recovery_loss,
                environment.lifecycle_cost,
            )
        )

    if not feasible:
        return OracleResult(
            False, None, None, None, None, [], [], 0, 0, raw_plan_count, [], []
        )

    feasible.sort(key=lambda item: item[0])
    best = feasible[0][0]
    optimal = [item for item in feasible if item[0] == best]
    unique_plans = _deduplicate([item[1] for item in optimal])
    unique_scopes = _deduplicate([item[2] for item in optimal])
    return OracleResult(
        True,
        optimal[0][3],
        optimal[0][4],
        min(item[4] for item in feasible),
        best,
        unique_plans,
        unique_scopes,
        len(feasible),
        len(_deduplicate([item[2] for item in feasible])),
        raw_plan_count,
        sorted({item[3] for item in feasible}),
        sorted({item[0] for item in feasible}),
    )


def _choices_for_slot(
    task: dict[str, Any], slot: str
) -> list[list[dict[str, Any]]]:
    commitments = [
        item
        for item in task["failure_snapshot"]["commitments"]
        if item["slot"] == slot and item["status"] == "confirmed"
    ]
    if len(commitments) > 1:
        raise ValueError(f"Oracle expects at most one active commitment in slot {slot}")
    existing = commitments[0] if commitments else None
    choices: list[list[dict[str, Any]]] = []
    if existing is not None:
        choices.append([])

    for option in task["catalog"]:
        if option["slot"] != slot or not option.get("available", False):
            continue
        if existing is None:
            choices.append([{"action": "book", "args": {"option_id": option["option_id"]}}])
            continue
        if option["option_id"] == existing["option_id"]:
            continue
        choices.append(
            [
                {
                    "action": "cancel",
                    "args": {"commitment_id": existing["commitment_id"]},
                },
                {"action": "book", "args": {"option_id": option["option_id"]}},
            ]
        )
    if existing is not None:
        for rule in task["modification_rules"]:
            if (
                rule["commitment_id"] == existing["commitment_id"]
                and rule.get("from_option_id", existing["option_id"])
                == existing["option_id"]
                and rule.get("available", True)
            ):
                choices.append(
                    [
                        {
                            "action": "modify",
                            "args": {
                                "commitment_id": existing["commitment_id"],
                                "to_option_id": rule["to_option_id"],
                            },
                        }
                    ]
                )
    return choices


def _merge_actions(
    combination: tuple[list[dict[str, Any]], ...]
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for choice in combination:
        actions.extend(deepcopy(choice))
    return actions


def _run_valid_actions(
    environment: RepairEnvironment, actions: list[dict[str, Any]]
) -> bool:
    for action in actions:
        if not environment.execute(action).ok:
            return False
    return True


def _deduplicate(items: list[Any]) -> list[Any]:
    result: list[Any] = []
    for item in items:
        if item not in result:
            result.append(item)
    return result
