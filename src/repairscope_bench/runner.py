from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import pstdev
import time
from typing import Any
from uuid import uuid4

from .domain_tools import DomainToolRouter, tool_definitions_for_task
from .environment import ActionResult, RepairEnvironment
from .evaluator import evaluate_environment
from .providers.base import ModelAdapter, ToolResult


SYSTEM_PROMPTS = {
    "travel": """You are a customer service agent for a travel company.
Use the available reservation, inventory, policy-preview, and booking tools to
resolve the customer's request. Inspect authoritative records before changing
them and do not invent identifiers or tool results. The request and tool
environment contain enough information for you to decide: do not ask the
customer to choose among alternatives or ask a follow-up question. Make and
execute the best supported decision yourself. Verify the resulting
arrangements, then call finish. If and only if the request is objectively
impossible, call report_infeasible.""",
    "shopping": """You are a shopping assistant for an online store.
Use the available order, product-search, return-preview, compatibility, and
purchase tools to resolve the customer's request. Inspect authoritative
records and do not invent identifiers or tool results. The request and tool
environment contain enough information for you to decide: do not ask the
customer to choose among alternatives or ask a follow-up question. Make and
execute the best supported decision yourself. Verify the resulting order,
then call finish. If and only if the request is objectively impossible, call
report_infeasible.""",
}

V05_SYSTEM_PROMPTS = {
    "travel": """You are a customer service agent for a travel company.
Use the available reservation, inventory, policy-preview, and booking tools to
resolve the customer's request. Inspect authoritative records before changing
them and do not invent identifiers or tool results. The request and tool
environment contain enough information for you to decide: do not ask the
customer to choose among alternatives or ask a follow-up question. Make and
execute the best supported decision yourself. Verify the resulting
arrangements and stop when no further tool action is needed. If and only if
the request is objectively impossible, call report_infeasible.""",
    "shopping": """You are a shopping assistant for an online store.
Use the available order, product-search, return-preview, compatibility, and
purchase tools to resolve the customer's request. Inspect authoritative
records and do not invent identifiers or tool results. The request and tool
environment contain enough information for you to decide: do not ask the
customer to choose among alternatives or ask a follow-up question. Make and
execute the best supported decision yourself. Verify the resulting order and
stop when no further tool action is needed. If and only if the request is
objectively impossible, call report_infeasible.""",
}


def build_user_prompt(task: dict[str, Any]) -> str:
    """Build the model-visible context without evaluator constraints or gold."""
    public = {
        "customer_request": task["instruction"],
        "latest_tool_result": task["failure_observation"],
        "earlier_tool_activity": task["pre_failure_trace"],
    }
    return (
        "Continue helping the customer from the current point.\n\n"
        + json.dumps(public, ensure_ascii=False, indent=2)
    )


def run_episode(
    task: dict[str, Any],
    adapter: ModelAdapter,
    *,
    max_turns: int = 15,
    run_id: str | None = None,
) -> dict[str, Any]:
    environment = RepairEnvironment(task)
    router = DomainToolRouter(environment)
    user_prompt = build_user_prompt(task)
    prompts = V05_SYSTEM_PROMPTS if task["schema_version"] == "0.5" else SYSTEM_PROMPTS
    system_prompt = prompts[task["domain"]]
    session = adapter.start_session(
        system_prompt, user_prompt, tool_definitions_for_task(task)
    )
    episode_id = run_id or uuid4().hex
    model_trace: list[dict[str, Any]] = []
    total_usage: dict[str, int | float] = {}
    pending_results: list[ToolResult] | None = None
    status = "running"
    started = time.monotonic()

    for turn_index in range(1, max_turns + 1):
        turn = session.advance(pending_results)
        pending_results = []
        for key, value in turn.usage.items():
            total_usage[key] = total_usage.get(key, 0) + value
        turn_record: dict[str, Any] = {
            "turn": turn_index,
            "text": turn.text,
            "stop_reason": turn.stop_reason,
            "usage": turn.usage,
            "tool_calls": [],
        }
        model_trace.append(turn_record)

        if not turn.tool_calls:
            status = (
                "completed"
                if environment.terminal_mode is not None
                else "model_stopped"
            )
            break

        for call in turn.tool_calls:
            mutation_limit = task.get("max_mutations")
            mutation_call = call.name in {
                "cancel_reservation",
                "book_travel_option",
                "change_reservation",
                "return_product",
                "purchase_product",
                "exchange_product",
            }
            if (
                mutation_limit is not None
                and mutation_call
                and environment.state_changing_actions() >= mutation_limit
            ):
                status = "action_budget_exceeded"
                break
            if call.parse_error:
                result = ActionResult(False, call.parse_error)
            elif call.arguments is None:
                result = ActionResult(False, "Missing tool arguments")
            else:
                result = router.execute(call.name, call.arguments)
            pending_results.append(
                ToolResult(call.call_id, call.name, result.as_dict())
            )
            turn_record["tool_calls"].append(
                {
                    "call_id": call.call_id,
                    "name": call.name,
                    "arguments": call.arguments,
                    "parse_error": call.parse_error,
                    "result": result.as_dict(),
                }
            )
            if environment.terminal_mode is not None:
                status = "completed"
                break
        if status != "running":
            break
    else:
        status = "turn_budget_exceeded"

    action_budget_exceeded = status == "action_budget_exceeded"
    score = evaluate_environment(task, environment, action_budget_exceeded)
    return {
        "run_id": episode_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provider": adapter.provider,
        "model": adapter.model,
        "task_id": task["task_id"],
        "family_id": task.get("family_id"),
        "variant_id": task.get("variant_id"),
        "pair_id": task.get("pair_id"),
        "evaluation_track": task.get("evaluation_track"),
        "mechanism": task.get("mechanism"),
        "split": task.get("split"),
        "task_schema_version": task["schema_version"],
        "status": status,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "harness_config": {
            "max_turns": max_turns,
            "max_mutations": task.get("max_mutations"),
            "max_output_tokens": getattr(adapter, "max_output_tokens", None),
            "reasoning_effort": getattr(adapter, "reasoning_effort", None),
        },
        "model_input": {
            "system": system_prompt,
            "user": user_prompt,
        },
        "usage": total_usage,
        "model_trace": model_trace,
        "score": score,
    }


def write_run(
    record: dict[str, Any], path: str | Path, *, overwrite: bool = False
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not overwrite:
        raise FileExistsError(
            f"Refusing to overwrite existing run file: {output}"
        )
    output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def run_suite(
    tasks: list[dict[str, Any]],
    adapter: ModelAdapter,
    output_dir: str | Path,
    *,
    repeats: int = 1,
    max_turns: int = 15,
    overwrite: bool = False,
) -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    jsonl_path = root / "runs.jsonl"
    if jsonl_path.exists() and not overwrite:
        raise FileExistsError(
            f"Refusing to mix a new experiment with {jsonl_path}; choose a "
            "new output directory or pass overwrite=True"
        )
    records: list[dict[str, Any]] = []
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for repeat in range(repeats):
            for task in tasks:
                run_id = f"{task['task_id']}-r{repeat + 1}-{uuid4().hex[:8]}"
                try:
                    record = run_episode(
                        task, adapter, max_turns=max_turns, run_id=run_id
                    )
                except Exception as error:
                    record = {
                        "run_id": run_id,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "provider": adapter.provider,
                        "model": adapter.model,
                        "task_id": task["task_id"],
                        "family_id": task.get("family_id"),
                        "variant_id": task.get("variant_id"),
                        "pair_id": task.get("pair_id"),
                        "evaluation_track": task.get("evaluation_track"),
                        "mechanism": task.get("mechanism"),
                        "split": task.get("split"),
                        "status": "provider_error",
                        "error": f"{type(error).__name__}: {error}",
                    }
                record["repeat_index"] = repeat + 1
                records.append(record)
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
    summary = summarize_runs(records, expected_repeats=repeats)
    (root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def summarize_runs(
    records: list[dict[str, Any]], *, expected_repeats: int | None = None
) -> dict[str, Any]:
    scored = [record["score"] for record in records if "score" in record]
    count = len(records)
    scored_count = len(scored)
    task_groups = _group_records(records, "task_id")
    repeats = expected_repeats or max(
        (len(group) for group in task_groups.values()), default=0
    )
    repeat_groups = _group_records(records, "repeat_index")
    goal_pass_at_1 = _record_rate(records, "success")
    optimal_pass_at_1 = _record_rate(records, "optimal_repair")
    goal_pass_at_k = _all_repeats_rate(
        task_groups, "success", expected_repeats=repeats
    )
    optimal_pass_at_k = _all_repeats_rate(
        task_groups, "optimal_repair", expected_repeats=repeats
    )
    goal_repeat_rates = [
        rate
        for group in repeat_groups.values()
        if (rate := _record_rate(group, "success")) is not None
    ]
    optimal_repeat_rates = [
        rate
        for group in repeat_groups.values()
        if (rate := _record_rate(group, "optimal_repair")) is not None
    ]
    numeric_extra = [
        score.get("extra_loss")
        for score in scored
        if score.get("extra_loss") is not None
    ]
    numeric_financial = [
        score.get("financial_regret")
        for score in scored
        if score.get("financial_regret") is not None
    ]
    summary = {
        "provider": records[0].get("provider") if records else None,
        "model": records[0].get("model") if records else None,
        "run_count": count,
        "scored_run_count": scored_count,
        "provider_error_count": count - scored_count,
        "task_count": len(task_groups),
        "repeats_per_task": repeats,
        "goal_pass@1": goal_pass_at_1,
        "goal_pass@1_stddev": _population_stddev(goal_repeat_rates),
        "goal_pass^k": goal_pass_at_k,
        f"goal_pass^{repeats}": goal_pass_at_k,
        "optimal_pass@1": optimal_pass_at_1,
        "scope_optimization_gap@1": (
            goal_pass_at_1 - optimal_pass_at_1
            if goal_pass_at_1 is not None and optimal_pass_at_1 is not None
            else None
        ),
        "optimal_pass@1_stddev": _population_stddev(optimal_repeat_rates),
        "optimal_pass^k": optimal_pass_at_k,
        "scope_optimization_gap^k": (
            goal_pass_at_k - optimal_pass_at_k
            if goal_pass_at_k is not None and optimal_pass_at_k is not None
            else None
        ),
        f"optimal_pass^{repeats}": optimal_pass_at_k,
        # Backward-compatible aliases. Unlike the pre-v0.3.2 implementation,
        # provider errors are now failures in these primary rates rather than
        # silently disappearing from the denominator.
        "success_rate": _record_rate(records, "success"),
        "optimal_repair_rate": _record_rate(records, "optimal_repair"),
        "mean_extra_loss_on_completed_feasible": _mean(numeric_extra),
        "mean_financial_regret_on_completed_feasible": _mean(numeric_financial),
        "mean_scope_distance": _mean(
            [
                score.get("scope_distance")
                for score in scored
                if score.get("scope_distance") is not None
            ]
        ),
    }
    track_groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        track = record.get("evaluation_track")
        if track is not None:
            track_groups.setdefault(str(track), []).append(record)
    if track_groups:
        summary["by_evaluation_track"] = {
            track: {
                "run_count": len(group),
                "goal_pass@1": _record_rate(group, "success"),
                "optimal_pass@1": _record_rate(group, "optimal_repair"),
                "scope_optimization_gap@1": _rate_gap(group),
            }
            for track, group in track_groups.items()
        }
    return summary


def _rate_gap(records: list[dict[str, Any]]) -> float | None:
    goal = _record_rate(records, "success")
    optimal = _record_rate(records, "optimal_repair")
    return goal - optimal if goal is not None and optimal is not None else None


def _record_rate(records: list[dict[str, Any]], key: str) -> float | None:
    if not records:
        return None
    return sum(
        bool(record.get("score", {}).get(key, False)) for record in records
    ) / len(records)


def _group_records(
    records: list[dict[str, Any]], key: str
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        value = record.get(key)
        if value is None:
            continue
        groups.setdefault(str(value), []).append(record)
    return groups


def _all_repeats_rate(
    groups: dict[str, list[dict[str, Any]]],
    key: str,
    *,
    expected_repeats: int,
) -> float | None:
    if not groups:
        return None
    passed = 0
    for records in groups.values():
        complete = len(records) == expected_repeats
        all_passed = all(
            bool(record.get("score", {}).get(key, False)) for record in records
        )
        passed += int(complete and all_passed)
    return passed / len(groups)


def _mean(values: list[int | float]) -> float | None:
    return sum(values) / len(values) if values else None


def _population_stddev(values: list[int | float]) -> float | None:
    return pstdev(values) if values else None
