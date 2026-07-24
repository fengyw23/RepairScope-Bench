from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .baselines import make_actions
from .evaluator import evaluate_actions
from .loader import load_tasks
from .oracle import solve_task


def validate_dataset(path: str | Path) -> dict[str, Any]:
    tasks = load_tasks(path)
    errors: list[str] = []
    families: dict[str, list[dict[str, Any]]] = defaultdict(list)
    feasible_count = 0

    for task in tasks:
        families[task["family_id"]].append(task)
        oracle = solve_task(task)
        expected = task["expected_oracle"]
        if oracle.feasible:
            feasible_count += 1
        if oracle.feasible != expected["feasible"]:
            errors.append(f"{task['task_id']}: feasible mismatch")
        if oracle.optimal_repair_loss != expected.get("repair_loss"):
            errors.append(
                f"{task['task_id']}: repair_loss {oracle.optimal_repair_loss} "
                f"!= {expected.get('repair_loss')}"
            )
        if oracle.feasible:
            expected_scope = expected["scope"]
            if expected_scope not in oracle.optimal_scopes:
                errors.append(
                    f"{task['task_id']}: expected scope is not oracle-optimal"
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
        scopes = {
            tuple(sorted(task["expected_oracle"]["scope"].items()))
            for task in members
        }
        feasible_values = {task["expected_oracle"]["feasible"] for task in members}
        if len(scopes) < 2:
            errors.append(f"{family_id}: expected scope never changes")
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
        "baselines": baseline_summary,
    }

