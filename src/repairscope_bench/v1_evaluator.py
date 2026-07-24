from __future__ import annotations

from copy import deepcopy
from typing import Any

from .v1_environment import CommitmentRecoveryEnvironment
from .v1_oracle import solve_task_v1


def evaluate_v1_environment(
    task: dict[str, Any],
    environment: CommitmentRecoveryEnvironment,
) -> dict[str, Any]:
    metadata = task.get("_benchmark_metadata", {})
    oracle = solve_task_v1(task)
    goal_pass, failures = environment.goal_status()
    observed = environment.economic_vector
    dominators = [
        item for item in oracle.frontier_vectors if item.dominates(observed)
    ]
    oracle_violation = bool(
        goal_pass
        and oracle.frontier_vectors
        and any(observed.dominates(item) for item in oracle.frontier_vectors)
    )
    non_dominated = bool(goal_pass and not dominators)
    scope = environment.dispositions()
    over, under, distance = _scope_diagnostics(scope, oracle.optimal_scopes)
    scope_on_frontier = scope in oracle.optimal_scopes
    return {
        "task_id": task["task_id"],
        "scenario_id": task.get("scenario_id", metadata.get("scenario_id")),
        "counterfactual_pair_id": task.get(
            "counterfactual_pair_id", metadata.get("pair_id")
        ),
        "variant_role": task.get("variant_role", metadata.get("variant_role")),
        "reasoning_structure": task.get(
            "reasoning_structure", metadata.get("reasoning_structure")
        ),
        "domain": task["domain"],
        "difficulty_level": task.get(
            "difficulty_level", metadata.get("difficulty_level")
        ),
        "goal_pass": goal_pass,
        "success": goal_pass,
        "non_dominated_repair": non_dominated,
        "optimal_repair": non_dominated,
        "dominated_repair": bool(goal_pass and dominators),
        "oracle_violation": oracle_violation,
        "exclude_from_aggregate": oracle_violation,
        "economic_vector": observed.as_dict(),
        "pareto_frontier": [
            item.as_dict() for item in oracle.frontier_vectors
        ],
        "irreversible_loss": observed.irreversible_loss,
        "net_recovery_outlay": observed.net_recovery_outlay,
        "irreversible_loss_regret": (
            min(
                observed.irreversible_loss - item.irreversible_loss
                for item in dominators
            )
            if dominators
            else 0
        ),
        "net_outlay_regret": (
            min(
                observed.net_recovery_outlay - item.net_recovery_outlay
                for item in dominators
            )
            if dominators
            else 0
        ),
        "scope": scope,
        "pareto_scopes": deepcopy(oracle.optimal_scopes),
        "scope_distance": distance,
        "over_repair": over,
        "under_repair": under,
        "correct_scope_wasteful_execution": bool(
            goal_pass and scope_on_frontier and dominators
        ),
        "constraint_failures": failures,
        "state_changing_actions": environment.state_changing_actions,
        "tool_errors": [
            item for item in environment.event_log if not item["result"]["ok"]
        ],
        "event_log": deepcopy(environment.event_log),
        "transaction_ledger": deepcopy(environment.ledger),
    }


def evaluate_v1_actions(
    task: dict[str, Any], calls: list[dict[str, Any]]
) -> dict[str, Any]:
    environment = CommitmentRecoveryEnvironment(task)
    for call in calls:
        environment.execute_tool(
            call.get("name", call.get("action", "")),
            call.get("arguments", call.get("args", {})),
        )
    return evaluate_v1_environment(task, environment)


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
