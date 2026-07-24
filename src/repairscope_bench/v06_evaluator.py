from __future__ import annotations

from copy import deepcopy
from typing import Any

from .v06_constraints import check_v06_constraints
from .v06_environment import StateBackedRecoveryEnvironment
from .v06_oracle import solve_task_v06


def evaluate_v06_environment(
    task: dict[str, Any],
    environment: StateBackedRecoveryEnvironment,
) -> dict[str, Any]:
    oracle = solve_task_v06(task)
    goal_pass, failures = check_v06_constraints(task, environment)
    observed = environment.economic_vector
    frontier_vectors = oracle.frontier_vectors
    dominators = [item for item in frontier_vectors if item.dominates(observed)]
    oracle_violation = bool(
        goal_pass
        and frontier_vectors
        and any(observed.dominates(item) for item in frontier_vectors)
    )
    non_dominated = bool(goal_pass and not dominators)
    loss_regret = (
        min(observed.irreversible_loss - item.irreversible_loss for item in dominators)
        if dominators
        else 0
    )
    outlay_regret = (
        min(
            observed.net_recovery_outlay - item.net_recovery_outlay
            for item in dominators
        )
        if dominators
        else 0
    )
    scope = environment.dispositions()
    over, under, distance = _scope_diagnostics(scope, oracle.optimal_scopes)
    return {
        "task_id": task["task_id"],
        "family_id": task["family_id"],
        "counterfactual_pair_id": task["counterfactual_pair_id"],
        "variant_id": task["variant_id"],
        "goal_pass": goal_pass,
        "success": goal_pass,
        "non_dominated_repair": non_dominated,
        "optimal_repair": non_dominated,
        "dominated_repair": bool(goal_pass and dominators),
        "oracle_violation": oracle_violation,
        "exclude_from_aggregate": oracle_violation,
        "economic_vector": observed.as_dict(),
        "pareto_frontier": [
            item.as_dict() for item in frontier_vectors
        ],
        "irreversible_loss": observed.irreversible_loss,
        "net_recovery_outlay": observed.net_recovery_outlay,
        "irreversible_loss_regret": loss_regret,
        "net_outlay_regret": outlay_regret,
        "scope": scope,
        "pareto_scopes": deepcopy(oracle.optimal_scopes),
        "scope_distance": distance,
        "over_repair": over,
        "under_repair": under,
        "constraint_failures": failures,
        "state_changing_actions": environment.state_changing_actions,
        "tool_errors": [
            item for item in environment.event_log if not item["result"]["ok"]
        ],
        "event_log": deepcopy(environment.event_log),
        "transaction_ledger": deepcopy(environment.ledger),
    }


def evaluate_v06_actions(
    task: dict[str, Any], calls: list[dict[str, Any]]
) -> dict[str, Any]:
    environment = StateBackedRecoveryEnvironment(task)
    for call in calls:
        environment.execute_tool(
            call.get("name", call.get("action", "")),
            call.get("arguments", call.get("args", {})),
        )
    return evaluate_v06_environment(task, environment)


def _scope_diagnostics(
    observed: dict[str, str], targets: list[dict[str, str]]
) -> tuple[list[str], list[str], float | None]:
    if not targets:
        return [], [], None
    keys = list(targets[0])
    distance = min(
        sum(observed.get(key) != target.get(key) for key in keys) / len(keys)
        for target in targets
    )
    must_keep = {
        key for key in keys if all(target.get(key) == "KEEP" for target in targets)
    }
    must_change = {
        key for key in keys if all(target.get(key) != "KEEP" for target in targets)
    }
    over = sorted(key for key in must_keep if observed.get(key) != "KEEP")
    under = sorted(key for key in must_change if observed.get(key) == "KEEP")
    return over, under, distance
