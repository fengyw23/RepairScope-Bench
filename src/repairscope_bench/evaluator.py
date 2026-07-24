from __future__ import annotations

from typing import Any

from .constraints import check_constraints
from .environment import RepairEnvironment
from .oracle import solve_task


def evaluate_actions(
    task: dict[str, Any],
    actions: list[dict[str, Any]],
    max_actions: int | None = None,
) -> dict[str, Any]:
    if task.get("schema_version") == "0.6":
        from .v06_evaluator import evaluate_v06_actions

        return evaluate_v06_actions(task, actions)
    environment = RepairEnvironment(task)
    action_limit = max_actions or task.get("max_mutations")
    for action in actions:
        if (
            action_limit is not None
            and action.get("action") in {"cancel", "book", "modify"}
            and environment.state_changing_actions() >= action_limit
        ):
            break
        environment.execute(action)
    requested_mutations = sum(
        action.get("action") in {"cancel", "book", "modify"} for action in actions
    )
    action_budget_exceeded = (
        action_limit is not None and requested_mutations > action_limit
    )

    return evaluate_environment(
        task, environment, action_budget_exceeded, action_limit
    )


def evaluate_environment(
    task: dict[str, Any],
    environment: RepairEnvironment,
    action_budget_exceeded: bool = False,
    action_limit: int | None = None,
) -> dict[str, Any]:
    effective_action_limit = (
        action_limit if action_limit is not None else task.get("max_mutations")
    )
    oracle = solve_task(task)
    goal_pass, constraint_failures = check_constraints(task, environment)
    dispositions = environment.dispositions()
    observed_objective = environment.objective_tuple()

    if oracle.feasible:
        # A feasible episode is judged by its external state, not by whether
        # the model emitted a benchmark-specific finish token.  An explicit
        # infeasibility report is still a substantive, incorrect decision.
        terminal_correct = environment.terminal_mode != "infeasible"
        success = bool(goal_pass and terminal_correct and not action_budget_exceeded)
        optimal = bool(success and observed_objective == oracle.optimal_objective)
        extra_loss = (
            environment.recovery_loss - oracle.optimal_recovery_loss
            if success and oracle.optimal_recovery_loss is not None
            else None
        )
        financial_regret = (
            environment.lifecycle_cost - oracle.minimum_feasible_financial_cost
            if success and oracle.minimum_feasible_financial_cost is not None
            else None
        )
        scope_distance = _scope_distance(dispositions, oracle.optimal_scopes)
        over_repair, under_repair = _scope_errors(
            dispositions, oracle.optimal_scopes
        )
    else:
        pristine = (
            environment.state_matches_failure_boundary()
            and environment.financial_delta == 0
            and environment.state_changing_actions() == 0
        )
        terminal_correct = environment.terminal_mode == "infeasible"
        success = bool(
            terminal_correct and pristine and not action_budget_exceeded
        )
        optimal = success
        extra_loss = 0 if success else None
        financial_regret = 0 if success else None
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
        "finish_called": environment.terminal_mode == "finish",
        "reported_infeasible": environment.terminal_mode == "infeasible",
        "success": success,
        "optimal_repair": optimal,
        "observed_objective": list(observed_objective),
        "optimal_objective": list(oracle.optimal_objective)
        if oracle.optimal_objective is not None
        else None,
        "pre_failure_spend": environment.pre_failure_spend,
        "financial_delta": environment.financial_delta,
        "lifecycle_cost": environment.lifecycle_cost,
        "optimal_financial_cost": oracle.optimal_financial_cost,
        "minimum_feasible_financial_cost": oracle.minimum_feasible_financial_cost,
        "financial_regret": financial_regret,
        "recovery_loss": environment.recovery_loss,
        "optimal_recovery_loss": oracle.optimal_recovery_loss,
        "extra_loss": extra_loss,
        "cancellation_loss": environment.cancellation_loss,
        "post_failure_waste": environment.post_failure_waste,
        "linked_loss": environment.linked_loss,
        "rollback_damage": environment.rollback_damage,
        "scope": dispositions,
        "optimal_scopes": oracle.optimal_scopes,
        "scope_distance": scope_distance,
        "over_repair": over_repair,
        "under_repair": under_repair,
        "constraint_failures": constraint_failures,
        "action_count": len(environment.event_log),
        "action_limit": effective_action_limit,
        "action_budget_exceeded": action_budget_exceeded,
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
