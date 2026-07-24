from __future__ import annotations

from typing import Any

from .constraints import check_constraints
from .environment import RepairEnvironment
from .oracle import solve_task


def evaluate_actions(
    task: dict[str, Any], actions: list[dict[str, Any]]
) -> dict[str, Any]:
    environment = RepairEnvironment(task)
    for action in actions:
        environment.execute(action)

    oracle = solve_task(task)
    goal_pass, constraint_failures = check_constraints(task, environment)
    dispositions = environment.dispositions()

    if oracle.feasible:
        terminal_correct = environment.terminal_mode == "finish"
        success = bool(goal_pass and terminal_correct)
        optimal = bool(
            success and environment.repair_loss == oracle.optimal_repair_loss
        )
        repair_regret = (
            environment.repair_loss - oracle.optimal_repair_loss
            if success and oracle.optimal_repair_loss is not None
            else None
        )
        scope_distance = _scope_distance(dispositions, oracle.optimal_scopes)
        over_repair, under_repair = _scope_errors(
            dispositions, oracle.optimal_scopes
        )
    else:
        preserved = all(value == "KEEP" for value in dispositions.values())
        terminal_correct = environment.terminal_mode == "infeasible"
        success = bool(terminal_correct and preserved)
        optimal = success
        repair_regret = 0 if success else None
        preserve_scope = [
            {
                item["commitment_id"]: "KEEP"
                for item in task["failure_snapshot"]["commitments"]
                if item["status"] == "confirmed"
            }
        ]
        scope_distance = _scope_distance(dispositions, preserve_scope)
        over_repair, under_repair = _scope_errors(dispositions, preserve_scope)

    return {
        "task_id": task["task_id"],
        "family_id": task["family_id"],
        "variant_id": task["variant_id"],
        "oracle_feasible": oracle.feasible,
        "goal_pass": goal_pass,
        "terminal_correct": terminal_correct,
        "success": success,
        "optimal_repair": optimal,
        "repair_loss": environment.repair_loss,
        "optimal_repair_loss": oracle.optimal_repair_loss,
        "repair_regret": repair_regret,
        "lifecycle_cost": environment.lifecycle_cost,
        "scope": dispositions,
        "optimal_scopes": oracle.optimal_scopes,
        "scope_distance": scope_distance,
        "over_repair": over_repair,
        "under_repair": under_repair,
        "constraint_failures": constraint_failures,
        "tool_errors": [
            event for event in environment.event_log if not event["result"]["ok"]
        ],
        "event_log": environment.event_log,
    }


def _scope_distance(
    observed: dict[str, str], targets: list[dict[str, str]]
) -> float | None:
    if not targets:
        return None
    if not observed:
        return 0.0
    return min(
        sum(observed.get(key) != value for key, value in target.items())
        / len(target)
        for target in targets
    )


def _scope_errors(
    observed: dict[str, str], targets: list[dict[str, str]]
) -> tuple[list[str], list[str]]:
    if not targets:
        return [], []
    keys = targets[0].keys()
    must_keep = {
        key for key in keys if all(target.get(key) == "KEEP" for target in targets)
    }
    must_change = {
        key for key in keys if all(target.get(key) != "KEEP" for target in targets)
    }
    over = sorted(key for key in must_keep if observed.get(key) != "KEEP")
    under = sorted(key for key in must_change if observed.get(key) == "KEEP")
    return over, under

