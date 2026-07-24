from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .baselines import make_actions
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
    validate_parser.add_argument("data")
    validate_parser.add_argument("--gold")

    oracle_parser = subparsers.add_parser("oracle")
    oracle_parser.add_argument("task")

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("task")

    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("task")
    evaluate_parser.add_argument("actions")

    baselines_parser = subparsers.add_parser("run-baselines")
    baselines_parser.add_argument("data")

    model_parser = subparsers.add_parser("run-model")
    model_parser.add_argument("task")
    _add_provider_arguments(model_parser)
    model_parser.add_argument("--output", required=True)
    model_parser.add_argument("--overwrite", action="store_true")

    suite_parser = subparsers.add_parser("run-suite")
    suite_parser.add_argument("data")
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
        return _print_result(
            {
                "task_id": task["task_id"],
                "instruction": task["instruction"],
                "failure_observation": task["failure_observation"],
                "failure_snapshot": task["failure_snapshot"],
                "available_tools": [
                    "list_commitments",
                    "get_commitment_details",
                    "get_cancellation_quote",
                    "search_options",
                    "get_modification_quote",
                    "check_compatibility",
                    "get_cost_summary",
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
    parser.add_argument("--max-turns", type=int, default=30)
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
