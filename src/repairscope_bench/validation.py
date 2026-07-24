from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any

from .baselines import make_actions
from .evaluator import evaluate_actions
from .loader import load_tasks
from .oracle import solve_task


def validate_dataset(
    path: str | Path, gold_path: str | Path | None = None
) -> dict[str, Any]:
    tasks = load_tasks(path)
    if tasks and tasks[0]["schema_version"] == "0.6":
        return _validate_v06_dataset(tasks, path, gold_path)
    gold_file = Path(gold_path) if gold_path is not None else _infer_gold_path(path)
    with gold_file.open("r", encoding="utf-8") as handle:
        gold: dict[str, dict[str, Any]] = json.load(handle)
    errors: list[str] = []
    families: dict[str, list[dict[str, Any]]] = defaultdict(list)
    feasible_count = 0

    for task in tasks:
        families[task["family_id"]].append(task)
        oracle = solve_task(task)
        expected = gold.get(task["task_id"])
        if expected is None:
            errors.append(f"{task['task_id']}: missing evaluator gold")
            continue
        if oracle.feasible:
            feasible_count += 1
        if (
            task.get("evaluation_class") == "loss_sensitive"
            or task.get("evaluation_track") == "loss_aware"
        ):
            requirements = task.get("challenge_requirements", {})
            minimum_plans = requirements.get("min_feasible_plans", 2)
            minimum_scopes = requirements.get("min_feasible_scopes", 1)
            minimum_loss_levels = requirements.get("min_loss_levels", 2)
            minimum_raw_plans = requirements.get("min_raw_plans", 1)
            if oracle.feasible_plan_count < minimum_plans:
                errors.append(
                    f"{task['task_id']}: loss-sensitive task has fewer than "
                    f"{minimum_plans} goal-satisfying repairs"
                )
            if oracle.feasible_scope_count < minimum_scopes:
                errors.append(
                    f"{task['task_id']}: loss-sensitive task has fewer than "
                    f"{minimum_scopes} feasible repair-scope patterns"
                )
            if len(oracle.feasible_recovery_losses) < minimum_loss_levels:
                errors.append(
                    f"{task['task_id']}: feasible repairs do not differ in "
                    f"at least {minimum_loss_levels} recovery-loss levels"
                )
            if oracle.raw_plan_count < minimum_raw_plans:
                errors.append(
                    f"{task['task_id']}: raw repair graph has fewer than "
                    f"{minimum_raw_plans} candidate plans"
                )
        if oracle.feasible != expected["feasible"]:
            errors.append(f"{task['task_id']}: feasible mismatch")
        expected_objective = (
            tuple(expected["optimal_objective"])
            if expected["optimal_objective"] is not None
            else None
        )
        if oracle.optimal_objective != expected_objective:
            errors.append(
                f"{task['task_id']}: objective {oracle.optimal_objective} "
                f"!= {expected.get('optimal_objective')}"
            )
        if oracle.feasible:
            if expected["optimal_scopes"] != oracle.optimal_scopes:
                errors.append(
                    f"{task['task_id']}: optimal scopes differ from gold"
                )
            score = evaluate_actions(task, make_actions(task, "oracle"))
            if not score["optimal_repair"]:
                errors.append(f"{task['task_id']}: oracle replay did not pass")
        else:
            score = evaluate_actions(task, make_actions(task, "oracle"))
            if not score["optimal_repair"]:
                errors.append(
                    f"{task['task_id']}: infeasibility report did not pass"
                )

    for family_id, members in families.items():
        if len(members) < 2:
            errors.append(f"{family_id}: counterfactual family has <2 variants")
        comparison_members = [
            task
            for task in members
            if task.get("evaluation_track", "loss_aware") == "loss_aware"
        ]
        recovery_outcomes = {
            (
                "feasible",
                tuple(
                    sorted(
                        gold[task["task_id"]]["optimal_scopes"][0].items()
                    )
                ),
            )
            if gold[task["task_id"]]["optimal_scopes"]
            else ("infeasible", ())
            for task in comparison_members
        }
        feasible_values = {
            gold[task["task_id"]]["feasible"] for task in comparison_members
        }
        if len(recovery_outcomes) < 2:
            errors.append(
                f"{family_id}: expected recovery outcome never changes"
            )
        if (
            all(task["schema_version"] == "0.4" for task in members)
            and len(feasible_values) < 2
        ):
            errors.append(f"{family_id}: no feasible/infeasible contrast")

    baseline_summary: dict[str, dict[str, int]] = {}
    for strategy in [
        "no_repair",
        "local_repair",
        "dependency_repair",
        "full_rollback",
        "global_cost",
        "oracle",
    ]:
        results = [
            evaluate_actions(task, make_actions(task, strategy)) for task in tasks
        ]
        baseline_summary[strategy] = {
            "success": sum(result["success"] for result in results),
            "optimal": sum(result["optimal_repair"] for result in results),
        }

    return {
        "valid": not errors,
        "task_count": len(tasks),
        "family_count": len(families),
        "domain_counts": dict(Counter(task["domain"] for task in tasks)),
        "track_counts": dict(
            Counter(task.get("evaluation_track", "legacy") for task in tasks)
        ),
        "mechanism_counts": dict(
            Counter(task.get("mechanism", "legacy") for task in tasks)
        ),
        "feasible_count": feasible_count,
        "infeasible_count": len(tasks) - feasible_count,
        "errors": errors,
        "gold_path": str(gold_file.resolve()),
        "baselines": baseline_summary,
    }


def _infer_gold_path(path: str | Path) -> Path:
    source = Path(path)
    dataset_name = source.stem if source.is_file() else source.name
    parent = source.parent
    if parent.name == "data":
        data_root = parent
    elif parent.parent.name == "data":
        data_root = parent.parent
    else:
        data_root = parent
    return data_root / "gold" / f"{dataset_name}.json"


def _validate_v06_dataset(
    tasks: list[dict[str, Any]],
    path: str | Path,
    gold_path: str | Path | None,
) -> dict[str, Any]:
    from .v06_constraints import constraint_is_effective
    from .v06_oracle import solve_task_v06

    gold_file = (
        Path(gold_path) if gold_path is not None else _infer_gold_path(path)
    )
    with gold_file.open("r", encoding="utf-8") as handle:
        gold: dict[str, dict[str, Any]] = json.load(handle)
    errors: list[str] = []
    families: dict[str, list[dict[str, Any]]] = defaultdict(list)
    pairs: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for task in tasks:
        families[task["family_id"]].append(task)
        pairs[task["counterfactual_pair_id"]].append(task)
        oracle = solve_task_v06(task)
        expected = gold.get(task["task_id"])
        if expected is None:
            errors.append(f"{task['task_id']}: missing v0.6 Pareto gold")
            continue
        if not oracle.feasible:
            errors.append(f"{task['task_id']}: task unexpectedly infeasible")
        if oracle.feasible_scope_count < 3:
            errors.append(
                f"{task['task_id']}: fewer than three semantic feasible scopes"
            )
        if oracle.feasible_terminal_count <= len(oracle.frontier):
            errors.append(
                f"{task['task_id']}: no feasible economically dominated distractor"
            )
        if any(len(item["tool_calls"]) > 12 for item in oracle.frontier):
            errors.append(
                f"{task['task_id']}: reference execution exceeds 12 tool calls"
            )
        for index, constraint in enumerate(task["hard_constraints"]):
            if not constraint_is_effective(task, constraint):
                errors.append(
                    f"{task['task_id']}: hard constraint {index} excludes no "
                    "available option"
                )
        if _frontier_signature(oracle.frontier) != _frontier_signature(
            oracle.independent_frontier
        ):
            errors.append(
                f"{task['task_id']}: search and independent oracle disagree"
            )
        if _frontier_signature(oracle.frontier) != _frontier_signature(
            expected["frontier"]
        ):
            errors.append(f"{task['task_id']}: checked-in frontier is stale")
        if not _replay_failure_boundary(task):
            errors.append(
                f"{task['task_id']}: prefix replay did not reproduce failure boundary"
            )

    for family_id, members in families.items():
        if len(members) != 4:
            errors.append(
                f"{family_id}: expected four independent counterfactual variants"
            )
        if len({item["variant_id"] for item in members}) != 4:
            errors.append(f"{family_id}: duplicate variant IDs")
    for pair_id, members in pairs.items():
        if len(members) != 2:
            errors.append(f"{pair_id}: expected exactly two paired variants")
            continue
        first, second = sorted(members, key=lambda item: item["variant_id"])
        invariant_fields = [
            "split",
            "instruction",
            "initial_snapshot",
            "initial_snapshot_sha256",
            "failure_snapshot",
            "snapshot_sha256",
            "option_metadata",
            "compatibility_rules",
            "required_slots",
            "hard_constraints",
            "boundary_commitments",
            "pre_failure_trace",
            "prefix_ledger",
            "latest_failure",
            "oracle_actions",
            "candidate_scopes",
        ]
        changed_invariants = [
            field for field in invariant_fields if first[field] != second[field]
        ]
        if changed_invariants:
            errors.append(
                f"{pair_id}: fields beyond the named fact differ: "
                f"{changed_invariants}"
            )
        first_refund = first["contracts"][0]["refund_adjustment"]
        second_refund = second["contracts"][0]["refund_adjustment"]
        first_penalty = first["contracts"][1]["settlement_charge"]
        second_penalty = second["contracts"][1]["settlement_charge"]
        if pair_id.endswith("-refund"):
            if {first_refund, second_refund} != {-800, 0}:
                errors.append(f"{pair_id}: refund fact did not flip as declared")
            if first_penalty != second_penalty:
                errors.append(f"{pair_id}: penalty changed in refund pair")
        else:
            if first_refund != second_refund:
                errors.append(f"{pair_id}: refund changed in penalty pair")
            if {first_penalty, second_penalty} != {0, 900}:
                errors.append(f"{pair_id}: penalty fact did not flip as declared")
        first_scope = solve_task_v06(first).optimal_scopes
        second_scope = solve_task_v06(second).optimal_scopes
        if first_scope == second_scope:
            errors.append(f"{pair_id}: Pareto recovery scope did not flip")

    strategies = [
        "no_repair",
        "local_repair",
        "dependency_repair",
        "full_rollback",
        "sticker_price",
        "refund_only",
        "pareto_oracle",
    ]
    baseline_summary: dict[str, dict[str, int]] = {}
    for strategy in strategies:
        results = [
            evaluate_actions(task, make_actions(task, strategy)) for task in tasks
        ]
        baseline_summary[strategy] = {
            "goal_pass": sum(result["goal_pass"] for result in results),
            "non_dominated_pass": sum(
                result["non_dominated_repair"] for result in results
            ),
            "dominated_goal_completions": sum(
                result["dominated_repair"] for result in results
            ),
        }
    if baseline_summary["pareto_oracle"]["non_dominated_pass"] != len(tasks):
        errors.append("Pareto oracle baseline did not pass every task")
    if (
        baseline_summary["local_repair"]["goal_pass"]
        != len(tasks)
        or baseline_summary["local_repair"]["non_dominated_pass"] >= len(tasks)
    ):
        errors.append(
            "Local baseline does not separate completion from economic quality"
        )

    return {
        "valid": not errors,
        "schema_version": "0.6",
        "task_count": len(tasks),
        "family_count": len(families),
        "counterfactual_pair_count": len(pairs),
        "domain_counts": dict(Counter(task["domain"] for task in tasks)),
        "split_counts": dict(Counter(task["split"] for task in tasks)),
        "errors": errors,
        "gold_path": str(gold_file.resolve()),
        "baselines": baseline_summary,
    }


def _replay_failure_boundary(task: dict[str, Any]) -> bool:
    from copy import deepcopy

    from .v06_environment import StateBackedRecoveryEnvironment, snapshot_hash

    replay_task = deepcopy(task)
    replay_task["failure_snapshot"] = deepcopy(task["initial_snapshot"])
    replay_task["snapshot_sha256"] = task["initial_snapshot_sha256"]
    replay_task["boundary_commitments"] = []
    replay_task["contracts"] = []
    environment = StateBackedRecoveryEnvironment(replay_task)
    environment.set_phase("prefix")
    for expected in task["pre_failure_trace"]:
        result = environment.execute_tool(
            expected["tool"], expected["arguments"]
        )
        if result.as_dict() != expected["result"]:
            return False
    failure = task["latest_failure"]
    result = environment.execute_tool(failure["tool"], failure["arguments"])
    if result.as_dict() != failure["result"] or result.ok:
        return False
    return (
        snapshot_hash(environment.normalized_state())
        == task["snapshot_sha256"]
        and environment.ledger == task["prefix_ledger"]
    )


def _frontier_signature(
    frontier: list[dict[str, Any]],
) -> list[tuple[Any, ...]]:
    return sorted(
        (
            item["economic_vector"]["irreversible_loss"],
            item["economic_vector"]["net_recovery_outlay"],
            tuple(sorted(item["scope"].items())),
        )
        for item in frontier
    )
