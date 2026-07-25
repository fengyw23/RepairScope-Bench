from __future__ import annotations

from copy import deepcopy
from typing import Any

from .v1_environment import EconomicVector
from .v2_environment import DomainRecoveryEnvironmentV2
from .v2_oracle import V2OracleResult, observed_terminal_key, solve_task_v2


def evaluate_v2_environment(
    task: dict[str, Any],
    environment: DomainRecoveryEnvironmentV2,
) -> dict[str, Any]:
    metadata = task.get("_benchmark_metadata", {})
    frozen = task.get("_benchmark_gold", {}).get("oracle")
    oracle = (
        V2OracleResult.from_dict(frozen)
        if frozen is not None
        else solve_task_v2(task)
    )
    goal_pass, failures = environment.goal_status()
    terminal_key = observed_terminal_key(task, environment)
    terminal = next(
        (
            item
            for item in oracle.feasible_terminals
            if item["terminal_key"] == terminal_key
        ),
        None,
    )
    scope_vector = _vector(terminal["scope_economic_vector"]) if terminal else None
    realized_vector = environment.economic_vector
    frontier_vectors = [
        _vector(item["scope_economic_vector"]) for item in oracle.frontier
    ]

    scope_dominators = (
        [item for item in frontier_vectors if item.dominates(scope_vector)]
        if scope_vector is not None
        else []
    )
    realized_dominators = [
        item for item in frontier_vectors if item.dominates(realized_vector)
    ]
    scope_pass = bool(goal_pass and scope_vector is not None and not scope_dominators)
    realized_pass = bool(goal_pass and not realized_dominators)
    oracle_violation = bool(
        goal_pass
        and (
            (scope_vector is not None and any(scope_vector.dominates(x) for x in frontier_vectors))
            or any(realized_vector.dominates(x) for x in frontier_vectors)
        )
    )

    accepted_scopes = [
        item["scope_signature"] for item in oracle.frontier
    ]
    observed_scope = (
        terminal["scope_signature"]
        if terminal is not None
        else _observed_scope_signature(task, environment)
    )
    over, under, distance = _scope_diagnostics(
        observed_scope, accepted_scopes
    )
    acquisition = _changed_fact_acquisition(task, environment)

    return {
        "task_id": task["task_id"],
        "pair_id": metadata.get("pair_id"),
        "scenario_id": metadata.get("scenario_id"),
        "variant_role": metadata.get("variant_role"),
        "reasoning_signature": deepcopy(metadata.get("reasoning_signature", [])),
        "mechanism_card_id": metadata.get("mechanism_card_id"),
        "construction_stratum": metadata.get("construction_stratum"),
        "domain": task["domain"],
        "goal_pass": goal_pass,
        "success": goal_pass,
        "scope_non_dominated_pass": scope_pass,
        "realized_non_dominated_pass": realized_pass,
        "non_dominated_repair": realized_pass,
        "optimal_repair": realized_pass,
        "dominated_scope": bool(goal_pass and scope_dominators),
        "dominated_execution": bool(goal_pass and realized_dominators),
        "dominated_repair": bool(goal_pass and realized_dominators),
        "correct_scope_wasteful_execution": bool(scope_pass and not realized_pass),
        "oracle_violation": oracle_violation,
        "exclude_from_aggregate": oracle_violation,
        "scope_economic_vector": (
            scope_vector.as_dict() if scope_vector is not None else None
        ),
        "realized_economic_vector": realized_vector.as_dict(),
        "pareto_frontier": [item.as_dict() for item in frontier_vectors],
        "scope_loss_regret": _regret(scope_vector, scope_dominators, "loss"),
        "scope_outlay_regret": _regret(scope_vector, scope_dominators, "outlay"),
        "realized_loss_regret": _regret(
            realized_vector, realized_dominators, "loss"
        ),
        "realized_outlay_regret": _regret(
            realized_vector, realized_dominators, "outlay"
        ),
        "terminal_key": terminal_key,
        "scope_signature": (
            deepcopy(terminal["scope_signature"]) if terminal is not None else None
        ),
        "scope_distance": distance,
        "over_repair": over,
        "under_repair": under,
        "changed_fact_acquisition": acquisition,
        "constraint_failures": failures,
        "state_changing_actions": environment.state_changing_actions,
        "tool_errors": [
            item for item in environment.event_log if not item["result"]["ok"]
        ],
        "event_log": deepcopy(environment.event_log),
        "transaction_ledger": deepcopy(environment.ledger),
    }


def evaluate_v2_actions(
    task: dict[str, Any], calls: list[dict[str, Any]]
) -> dict[str, Any]:
    environment = DomainRecoveryEnvironmentV2(task)
    for call in calls:
        environment.execute_tool(
            call.get("name", call.get("action", "")),
            call.get("arguments", call.get("args", {})),
        )
    return evaluate_v2_environment(task, environment)


def _vector(raw: dict[str, Any]) -> EconomicVector:
    return EconomicVector(
        int(raw["irreversible_loss"]),
        int(raw["net_recovery_outlay"]),
    )


def _regret(
    observed: EconomicVector | None,
    dominators: list[EconomicVector],
    dimension: str,
) -> int | None:
    if observed is None:
        return None
    if not dominators:
        return 0
    if dimension == "loss":
        return max(
            observed.irreversible_loss - item.irreversible_loss
            for item in dominators
        )
    return max(
        observed.net_recovery_outlay - item.net_recovery_outlay
        for item in dominators
    )


def _scope_diagnostics(
    observed: dict[str, Any],
    targets: list[dict[str, Any]],
) -> tuple[list[str], list[str], float | None]:
    if not targets:
        return [], [], None
    observed_boundary = observed["boundary"]
    target_boundaries = [target["boundary"] for target in targets]
    boundary_keys = sorted(target_boundaries[0])
    option_ids = set(observed.get("added_option_ids", []))
    for target in targets:
        option_ids.update(target.get("added_option_ids", []))
    denominator = len(boundary_keys) + len(option_ids)
    distance = min(
        (
            sum(
                observed_boundary.get(key) != target["boundary"].get(key)
                for key in boundary_keys
            )
            + sum(
                (option_id in observed.get("added_option_ids", []))
                != (option_id in target.get("added_option_ids", []))
                for option_id in option_ids
            )
        )
        / denominator
        for target in targets
    )
    must_keep = {
        key
        for key in boundary_keys
        if all(target.get(key) == "KEEP" for target in target_boundaries)
    }
    must_change = {
        key
        for key in boundary_keys
        if all(target.get(key) != "KEEP" for target in target_boundaries)
    }
    over = sorted(
        key for key in must_keep if observed_boundary.get(key) != "KEEP"
    )
    under = sorted(
        key for key in must_change if observed_boundary.get(key) == "KEEP"
    )
    return over, under, distance


def _observed_scope_signature(
    task: dict[str, Any],
    environment: DomainRecoveryEnvironmentV2,
) -> dict[str, Any]:
    boundary_ids = {
        item["entity_id"] for item in task["boundary_commitments"]
    }
    return {
        "boundary": environment.dispositions(),
        "added_option_ids": sorted(
            item["option_id"]
            for item in environment.active_commitments()
            if item["entity_id"] not in boundary_ids
        ),
    }


def _changed_fact_acquisition(
    task: dict[str, Any], environment: DomainRecoveryEnvironmentV2
) -> dict[str, Any] | None:
    manifest = task.get("_benchmark_metadata", {}).get("key_fact_manifest")
    if not manifest:
        return None
    first_mutation = next(
        (
            index
            for index, event in enumerate(environment.event_log)
            if event.get("state_changed") and event["result"].get("ok")
        ),
        len(environment.event_log),
    )
    required_tool = manifest["reveal_tool"]
    required_record = manifest.get("record_id")
    equivalent_records = _equivalent_record_ids(task, required_record)
    observed = False
    for event in environment.event_log[:first_mutation]:
        if not event["result"].get("ok"):
            continue
        if environment.public_tool_name(event["tool"]) != required_tool:
            continue
        if required_record is None or equivalent_records.intersection(
            event["arguments"].values()
        ):
            observed = True
            break
    return {
        "queried_before_first_mutation": observed,
        "reveal_tool": required_tool,
        "record_id": required_record,
    }


def _equivalent_record_ids(
    task: dict[str, Any], record_id: str | None
) -> set[str]:
    if record_id is None:
        return set()
    equivalent = {record_id}
    commitments = list(task.get("boundary_commitments", []))
    commitments.extend(
        task.get("failure_snapshot", {}).get("commitments", [])
    )
    for commitment in commitments:
        identifiers = {
            value
            for value in (
                commitment.get("entity_id"),
                commitment.get("option_id"),
            )
            if value
        }
        if record_id in identifiers:
            equivalent.update(identifiers)
    return equivalent


__all__ = ["evaluate_v2_actions", "evaluate_v2_environment"]
