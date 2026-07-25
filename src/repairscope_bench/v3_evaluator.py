from __future__ import annotations

from copy import deepcopy
from typing import Any

from .v3_constraints import check_v3_constraints
from .v3_environment import NativeRecoveryEnvironmentV3
from .v3_oracle import V3OracleResult, scope_key, solve_task_v3


def evaluate_v3_environment(
    task: dict[str, Any],
    environment: NativeRecoveryEnvironmentV3,
) -> dict[str, Any]:
    frozen = task.get("_benchmark_gold", {}).get("oracle")
    oracle = (
        V3OracleResult.from_dict(frozen)
        if frozen is not None
        else solve_task_v3(task)
    )
    goal_pass, failures = check_v3_constraints(task, environment)
    observed_scope = environment.canonical_scope()
    gold_scope = oracle.gold["scope_signature"] if oracle.gold else None
    gold_cost = (
        int(oracle.gold["incremental_cost_minor"]) if oracle.gold else None
    )
    realized_cost = environment.incremental_recovery_cost_minor
    scope_pass = bool(
        goal_pass
        and gold_scope is not None
        and scope_key(observed_scope) == scope_key(gold_scope)
    )
    cost_regret = (
        realized_cost - gold_cost
        if goal_pass and gold_cost is not None
        else None
    )
    clean_execution = bool(scope_pass and cost_regret == 0)
    oracle_violation = bool(goal_pass and cost_regret is not None and cost_regret < 0)
    over, under, distance = _scope_diagnostics(
        observed_scope, gold_scope
    )
    acquisition = _changed_fact_acquisition(task, environment)
    metadata = task.get("_benchmark_metadata", {})
    return {
        "task_id": task["task_id"],
        "pair_id": metadata.get("pair_id"),
        "scenario_id": metadata.get("scenario_id"),
        "variant_role": metadata.get("variant_role"),
        "domain": task["domain"],
        "reasoning_structure": metadata.get("reasoning_structure"),
        "goal_pass": goal_pass,
        "success": goal_pass,
        "unique_scope_pass": scope_pass,
        "dominated_repair": bool(
            goal_pass and not scope_pass and not oracle_violation
        ),
        "scope_non_dominated_pass": scope_pass,
        "clean_execution": clean_execution,
        "optimal_repair": clean_execution,
        "incremental_recovery_cost_minor": realized_cost,
        "gold_incremental_recovery_cost_minor": gold_cost,
        "cost_regret_minor": cost_regret,
        "execution_waste_minor": (
            max(0, int(cost_regret))
            if scope_pass and cost_regret is not None
            else None
        ),
        "correct_scope_wasteful_execution": bool(
            scope_pass and not clean_execution
        ),
        "oracle_violation": oracle_violation,
        "exclude_from_aggregate": oracle_violation,
        "scope_signature": observed_scope,
        "gold_scope_signature": deepcopy(gold_scope),
        "scope_distance": distance,
        "over_repair": over,
        "under_repair": under,
        "changed_fact_acquisition": acquisition,
        "constraint_failures": failures,
        "state_changing_actions": environment.state_changing_actions,
        "tool_errors": [
            item
            for item in environment.event_log
            if not item["result"].get("ok", False)
        ],
        "event_log": deepcopy(environment.event_log),
        "economic_events": environment.economic_events(),
    }


def evaluate_v3_actions(
    task: dict[str, Any], calls: list[dict[str, Any]]
) -> dict[str, Any]:
    environment = NativeRecoveryEnvironmentV3(task)
    for call in calls:
        environment.execute_tool(
            call.get("name", call.get("action", "")),
            call.get("arguments", call.get("args", {})),
        )
    return evaluate_v3_environment(task, environment)


def _scope_diagnostics(
    observed: dict[str, Any],
    gold: dict[str, Any] | None,
) -> tuple[list[str], list[str], float | None]:
    if gold is None:
        return [], [], None
    observed_boundary = observed["boundary"]
    gold_boundary = gold["boundary"]
    boundary_ids = sorted(set(observed_boundary) | set(gold_boundary))
    option_ids = sorted(
        set(observed.get("added_option_ids", []))
        | set(gold.get("added_option_ids", []))
    )
    denominator = len(boundary_ids) + len(option_ids)
    mismatches = sum(
        observed_boundary.get(key) != gold_boundary.get(key)
        for key in boundary_ids
    ) + sum(
        (option_id in observed.get("added_option_ids", []))
        != (option_id in gold.get("added_option_ids", []))
        for option_id in option_ids
    )
    over = sorted(
        key
        for key, disposition in gold_boundary.items()
        if disposition == "KEEP"
        and observed_boundary.get(key) != "KEEP"
    )
    under = sorted(
        key
        for key, disposition in gold_boundary.items()
        if disposition != "KEEP"
        and observed_boundary.get(key) == "KEEP"
    )
    observed_added = set(observed.get("added_option_ids", []))
    gold_added = set(gold.get("added_option_ids", []))
    over.extend(
        f"added_option:{option_id}"
        for option_id in sorted(observed_added - gold_added)
    )
    under.extend(
        f"added_option:{option_id}"
        for option_id in sorted(gold_added - observed_added)
    )
    return over, under, mismatches / denominator if denominator else 0.0


def _changed_fact_acquisition(
    task: dict[str, Any],
    environment: NativeRecoveryEnvironmentV3,
) -> dict[str, Any] | None:
    manifest = task.get("_benchmark_metadata", {}).get("changed_fact")
    if not manifest:
        return None
    first_mutation = next(
        (
            index
            for index, event in enumerate(environment.event_log)
            if event.get("state_changed") and event["result"].get("ok", False)
        ),
        len(environment.event_log),
    )
    reveal_paths = manifest.get("reveal_paths") or [
        {
            "tool": manifest["reveal_tool"],
            "arguments": {"record_id": manifest["record_id"]},
            "match": manifest.get("match"),
        }
    ]
    observed_event = next(
        (
            event
            for event in environment.event_log[:first_mutation]
            if event["result"].get("ok", False)
            and any(
                event["tool"] == path["tool"]
                and _matches_changed_fact(
                    event["result"].get("data") or {}, path.get("match")
                )
                for path in reveal_paths
            )
        ),
        None,
    )
    return {
        "queried_before_first_mutation": observed_event is not None,
        "reveal_tool": manifest["reveal_tool"],
        "record_id": manifest["record_id"],
        "equivalent_reveal_path_count": len(reveal_paths),
        "observed_tool": (
            observed_event["tool"] if observed_event is not None else None
        ),
        "observed_record_id": (
            observed_event.get("arguments", {}).get("record_id")
            if observed_event is not None
            else None
        ),
    }


def _matches_changed_fact(
    data: dict[str, Any], match: dict[str, Any] | None
) -> bool:
    if not match:
        return False
    term = next(
        (
            item
            for item in data.get("linked_terms", [])
            if item.get("term_id") == match.get("term_id")
        ),
        None,
    )
    if term is None:
        return False
    field = str(match.get("field", ""))
    if field == "charge_minor":
        observed = _money_minor(term.get("one_time_charge"))
    elif field == "credit_minor":
        observed = _money_minor(term.get("credit"))
    elif field == "monthly_minor":
        observed = _money_minor(term.get("monthly_charge"))
    elif field.startswith("trigger/"):
        observed = term.get("trigger", {}).get(field.split("/", 1)[1])
        if isinstance(observed, dict) and "amount" in observed:
            observed = _money_minor(observed)
    else:
        return False
    return observed == match.get("expected")


def _money_minor(value: Any) -> int | None:
    if not isinstance(value, dict) or value.get("currency") != "USD":
        return None
    amount = str(value.get("amount", ""))
    sign = -1 if amount.startswith("-") else 1
    amount = amount.lstrip("-")
    if "." not in amount:
        return None
    dollars, cents = amount.split(".", 1)
    if len(cents) != 2 or not dollars.isdigit() or not cents.isdigit():
        return None
    return sign * (int(dollars) * 100 + int(cents))


__all__ = ["evaluate_v3_actions", "evaluate_v3_environment"]
