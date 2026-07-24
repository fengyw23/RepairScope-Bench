from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .baselines import make_actions
from .evaluator import evaluate_actions
from .loader import load_task, load_tasks
from .oracle import solve_task
from .validation import validate_dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="repairscope")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("data")

    oracle_parser = subparsers.add_parser("oracle")
    oracle_parser.add_argument("task")

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("task")

    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("task")
    evaluate_parser.add_argument("actions")

    baselines_parser = subparsers.add_parser("run-baselines")
    baselines_parser.add_argument("data")

    args = parser.parse_args(argv)
    if args.command == "validate":
        return _print_result(validate_dataset(args.data))
    if args.command == "oracle":
        return _print_result(solve_task(load_task(args.task)).as_dict())
    if args.command == "inspect":
        task = load_task(args.task)
        return _print_result(
            {
                "task_id": task["task_id"],
                "instruction": task["instruction"],
                "failure_observation": task["failure_observation"],
                "failure_snapshot": task["failure_snapshot"],
                "available_tools": [
                    "query_state",
                    "list_options",
                    "cancel",
                    "book",
                    "modify",
                    "finish",
                    "report_infeasible",
                ],
            }
        )
    if args.command == "evaluate":
        task = load_task(args.task)
        actions = _read_json(args.actions)
        return _print_result(evaluate_actions(task, actions))
    if args.command == "run-baselines":
        results: dict[str, Any] = {}
        tasks = load_tasks(args.data)
        for strategy in [
            "no_repair",
            "local_repair",
            "dependency_repair",
            "full_rollback",
            "oracle",
        ]:
            scores = [
                evaluate_actions(task, make_actions(task, strategy)) for task in tasks
            ]
            results[strategy] = {
                "success_rate": sum(score["success"] for score in scores)
                / len(scores),
                "optimal_repair_rate": sum(
                    score["optimal_repair"] for score in scores
                )
                / len(scores),
                "mean_scope_distance": sum(
                    score["scope_distance"] for score in scores
                )
                / len(scores),
            }
        return _print_result(results)
    return 2


def _read_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _print_result(value: Any) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

