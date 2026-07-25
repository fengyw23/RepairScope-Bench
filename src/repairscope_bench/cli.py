from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .baselines import make_actions
from .domain_tools import tool_definitions_for_task
from .evaluator import evaluate_actions
from .loader import load_task, load_tasks
from .oracle import solve_task
from .providers import ProviderError, create_adapter
from .runner import run_episode, run_suite, write_run
from .validation import validate_dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="repairscope")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("data", nargs="?", default="data/v3")
    validate_parser.add_argument("--gold")

    oracle_parser = subparsers.add_parser("oracle")
    oracle_parser.add_argument("task")

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("task")

    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("task")
    evaluate_parser.add_argument("actions")

    baselines_parser = subparsers.add_parser("run-baselines")
    baselines_parser.add_argument("data", nargs="?", default="data/v3")

    calibration_parser = subparsers.add_parser("calibrate-difficulty")
    calibration_parser.add_argument("runs")
    calibration_parser.add_argument("--version", required=True)
    calibration_parser.add_argument(
        "--response-field",
        default="unique_scope_pass",
    )
    calibration_parser.add_argument("--output")

    model_parser = subparsers.add_parser("run-model")
    model_parser.add_argument("task")
    _add_provider_arguments(model_parser)
    model_parser.add_argument("--output", required=True)
    model_parser.add_argument("--overwrite", action="store_true")

    suite_parser = subparsers.add_parser("run-suite")
    suite_parser.add_argument("data", nargs="?", default="data/v3")
    _add_provider_arguments(suite_parser)
    suite_parser.add_argument("--output-dir", required=True)
    suite_parser.add_argument(
        "--repeats",
        type=int,
        default=5,
        help=(
            "Independent runs per task. The official protocol uses 5 and "
            "reports both average pass@1 and strict pass^5."
        ),
    )
    suite_parser.add_argument("--overwrite", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "validate":
        return _print_result(validate_dataset(args.data, args.gold))
    if args.command == "oracle":
        return _print_result(solve_task(load_task(args.task)).as_dict())
    if args.command == "inspect":
        task = load_task(args.task)
        if task["schema_version"] in {
            "0.6",
            "1.0",
            "1.1",
            "2.0",
            "3.0",
        }:
            return _print_result(
                {
                    "task_id": task["task_id"],
                    "instruction": task["instruction"],
                    "latest_failure": task["latest_failure"],
                    "failure_snapshot_sha256": task["snapshot_sha256"],
                    "boundary_commitments": task["boundary_commitments"],
                    "reasoning_structure": task.get("reasoning_structure"),
                    "reasoning_signature": task.get(
                        "_benchmark_metadata", {}
                    ).get("reasoning_signature"),
                    "complexity_profile": task.get(
                        "_benchmark_metadata", {}
                    ).get("complexity_profile"),
                    "available_tools": [
                        item["name"] for item in tool_definitions_for_task(task)
                    ],
                }
            )
        return _print_result(
            {
                "task_id": task["task_id"],
                "instruction": task["instruction"],
                "failure_observation": task["failure_observation"],
                "failure_snapshot": task["failure_snapshot"],
                "available_tools": [
                    item["name"] for item in tool_definitions_for_task(task)
                ],
            }
            )
    if args.command == "calibrate-difficulty":
        from .difficulty import calibrate_rasch

        result = calibrate_rasch(
            _read_jsonl(args.runs),
            response_field=args.response_field,
            calibration_version=args.version,
        )
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return _print_result(result)
    if args.command == "evaluate":
        task = load_task(args.task)
        actions = _read_json(args.actions)
        return _print_result(evaluate_actions(task, actions))
    if args.command == "run-baselines":
        results: dict[str, Any] = {}
        tasks = load_tasks(args.data)
        strategies = (
            [
                "no_repair",
                "local_repair",
                "dependency_repair",
                "full_rollback",
                "sticker_price",
                "max_refund",
                "min_changes",
                "cost_oracle",
            ]
            if tasks and tasks[0]["schema_version"] == "3.0"
            else
            [
                "no_repair",
                "local_repair",
                "dependency_repair",
                "full_rollback",
                "sticker_price",
                "refund_only",
                "min_changes",
                "loss_only",
                "outlay_only",
                "pareto_oracle",
            ]
            if tasks and tasks[0]["schema_version"] in {"1.0", "1.1", "2.0"}
            else
            [
                "no_repair",
                "local_repair",
                "dependency_repair",
                "full_rollback",
                "sticker_price",
                "refund_only",
                "pareto_oracle",
            ]
            if tasks and tasks[0]["schema_version"] == "0.6"
            else [
                "no_repair",
                "local_repair",
                "dependency_repair",
                "full_rollback",
                "global_cost",
                "oracle",
            ]
        )
        for strategy in strategies:
            scores = [
                evaluate_actions(task, make_actions(task, strategy)) for task in tasks
            ]
            if tasks and tasks[0]["schema_version"] == "3.0":
                results[strategy] = {
                    "goal_pass_rate": sum(
                        score["goal_pass"] for score in scores
                    )
                    / len(scores),
                    "unique_scope_pass_rate": sum(
                        score["unique_scope_pass"] for score in scores
                    )
                    / len(scores),
                    "clean_execution_rate": sum(
                        score["clean_execution"] for score in scores
                    )
                    / len(scores),
                    "mean_cost_regret_minor": (
                        sum(
                            score["cost_regret_minor"]
                            for score in scores
                            if score["cost_regret_minor"] is not None
                        )
                        / sum(
                            score["cost_regret_minor"] is not None
                            for score in scores
                        )
                        if any(
                            score["cost_regret_minor"] is not None
                            for score in scores
                        )
                        else None
                    ),
                }
                continue
            results[strategy] = {
                "success_rate": sum(score["success"] for score in scores)
                / len(scores),
                "scope_non_dominated_rate": sum(
                    score.get(
                        "scope_non_dominated_pass",
                        score["optimal_repair"],
                    )
                    for score in scores
                )
                / len(scores),
                "realized_non_dominated_rate": sum(
                    score.get(
                        "realized_non_dominated_pass",
                        score["optimal_repair"],
                    )
                    for score in scores
                )
                / len(scores),
                "optimal_repair_rate": sum(
                    score["optimal_repair"] for score in scores
                )
                / len(scores),
                "mean_scope_distance": (
                    sum(
                        score["scope_distance"]
                        for score in scores
                        if score["scope_distance"] is not None
                    )
                    / sum(
                        score["scope_distance"] is not None for score in scores
                    )
                    if any(
                        score["scope_distance"] is not None for score in scores
                    )
                    else None
                ),
            }
        return _print_result(results)
    if args.command in {"run-model", "run-suite"}:
        try:
            if args.timeout <= 0:
                parser.error("--timeout must be positive")
            if args.max_retries < 0:
                parser.error("--max-retries cannot be negative")
            if args.max_turns <= 0:
                parser.error("--max-turns must be positive")
            if args.max_output_tokens <= 0:
                parser.error("--max-output-tokens must be positive")
            adapter = create_adapter(
                args.provider,
                args.model,
                base_url=args.base_url,
                timeout=args.timeout,
                max_retries=args.max_retries,
                max_output_tokens=args.max_output_tokens,
                reasoning_effort=args.reasoning_effort,
                qwen_enable_thinking=args.qwen_enable_thinking,
            )
            if args.command == "run-model":
                record = run_episode(
                    load_task(args.task),
                    adapter,
                    max_turns=args.max_turns,
                )
                output = write_run(
                    record, args.output, overwrite=args.overwrite
                )
                return _print_result(
                    {
                        "output": str(output.resolve()),
                        "status": record["status"],
                        "score": record["score"],
                    }
                )
            if args.repeats <= 0:
                parser.error("--repeats must be positive")
            summary = run_suite(
                load_tasks(args.data),
                adapter,
                args.output_dir,
                repeats=args.repeats,
                max_turns=args.max_turns,
                overwrite=args.overwrite,
            )
            return _print_result(summary)
        except (ProviderError, FileExistsError) as error:
            parser.error(str(error))
    return 2


def _read_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def _print_result(value: Any) -> int:
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0


def _add_provider_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--provider",
        required=True,
        choices=[
            "openai",
            "anthropic",
            "qwen",
            "deepseek",
            "openai-compatible",
        ],
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--max-turns", type=int, default=15)
    parser.add_argument("--max-output-tokens", type=int, default=4096)
    parser.add_argument(
        "--reasoning-effort",
        choices=["none", "low", "medium", "high", "xhigh"],
    )
    parser.add_argument(
        "--qwen-enable-thinking",
        action=argparse.BooleanOptionalAction,
        default=None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
