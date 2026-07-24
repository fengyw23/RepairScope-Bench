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
            for task in members
        }
        feasible_values = {gold[task["task_id"]]["feasible"] for task in members}
        if len(recovery_outcomes) < 2:
            errors.append(
                f"{family_id}: expected recovery outcome never changes"
            )
        if len(feasible_values) < 2:
            errors.append(f"{family_id}: no feasible/infeasible contrast")

    baseline_summary: dict[str, dict[str, int]] = {}
    for strategy in [
        "no_repair",
        "local_repair",
        "dependency_repair",
        "full_rollback",
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
