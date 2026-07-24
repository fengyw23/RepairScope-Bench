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

V06_SYSTEM_PROMPTS = {
    "travel": """You are a customer service agent for a travel company.
Continue the partially executed request using the authoritative reservation,
inventory, policy, contract, preview, and booking tools. Make the best
supported decision in the customer's interests, do not invent identifiers or
tool results, and do not ask the customer to choose among alternatives. The
environment contains enough information to decide. Verify the resulting
arrangements and stop when no further tool action is needed.""",
    "customer_support": """You are a customer service agent for an online store.
Continue the partially executed request using the authoritative order,
catalog, policy, contract, compatibility, preview, and transaction tools.
Make the best supported decision in the customer's interests, do not invent
identifiers or tool results, and do not ask the customer to choose among
alternatives. The environment contains enough information to decide. Verify
the resulting orders and stop when no further tool action is needed.""",
}

V1_SYSTEM_PROMPTS = {
    "travel": """You are a travel service agent continuing a partially executed request.
Use the authoritative arrangement, inventory, cancellation-preview, contract,
compatibility, and booking tools. Make the best supported decision in the
customer's interests without inventing identifiers or asking the customer to
choose. Verify the resulting arrangements and stop when no further action is
needed.""",
    "after_sales": """You are an after-sales service agent continuing a partially executed purchase.
Use the authoritative order, product, return-preview, contract, compatibility,
and purchase tools. Make the best supported decision in the customer's
interests without inventing identifiers or asking the customer to choose.
Verify the resulting orders and stop when no further action is needed.""",
    "saas": """You are an enterprise SaaS service agent continuing a partially executed request.
Use the authoritative subscription, service-option, termination-preview,
contract, compatibility, and activation tools. Make the best supported
decision in the customer's interests without inventing identifiers or asking
the customer to choose. Verify the resulting service and stop when complete.""",
    "event_logistics": """You are an event-logistics service agent continuing a partially executed request.
Use the authoritative commitment, vendor, cancellation-preview, contract,
compatibility, and booking tools. Make the best supported decision in the
customer's interests without inventing identifiers or asking the customer to
choose. Verify the resulting event plan and stop when complete.""",
}


def build_user_prompt(task: dict[str, Any]) -> str:
    """Build the model-visible context without evaluator constraints or gold."""
    if task["schema_version"] in {"0.6", "1.0", "1.1"}:
        public = {
            "customer_request": task["instruction"],
            "earlier_successful_tool_activity": task["pre_failure_trace"],
            "latest_failed_tool_call": task["latest_failure"],
        }
        return (
            "Continue helping the customer from this fixed failure boundary.\n\n"
            + json.dumps(public, ensure_ascii=False, indent=2)
        )
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
    is_v06 = task["schema_version"] == "0.6"
    is_v1 = task["schema_version"] in {"1.0", "1.1"}
    is_stateful = is_v06 or is_v1
    effective_max_turns = (
        min(max_turns, int(task["max_turns"])) if is_stateful else max_turns
    )
    if is_v1:
        from .v1_environment import CommitmentRecoveryEnvironment
        from .v1_evaluator import evaluate_v1_environment

        environment = CommitmentRecoveryEnvironment(task)
        router = None
    elif is_v06:
        from .v06_environment import StateBackedRecoveryEnvironment
        from .v06_evaluator import evaluate_v06_environment

        environment = StateBackedRecoveryEnvironment(task)
        router = None
    else:
        environment = RepairEnvironment(task)
        router = DomainToolRouter(environment)
    user_prompt = build_user_prompt(task)
    if is_v1:
        prompts = V1_SYSTEM_PROMPTS
    elif is_v06:
        prompts = V06_SYSTEM_PROMPTS
    else:
        prompts = (
            V05_SYSTEM_PROMPTS
            if task["schema_version"] == "0.5"
            else SYSTEM_PROMPTS
        )
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

    for turn_index in range(1, effective_max_turns + 1):
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
                "model_stopped"
                if is_stateful
                else (
                    "completed"
                    if environment.terminal_mode is not None
                    else "model_stopped"
                )
            )
            break

        for call in turn.tool_calls:
            if call.parse_error:
                result = ActionResult(False, call.parse_error)
            elif call.arguments is None:
                result = ActionResult(False, "Missing tool arguments")
            elif is_stateful:
                result = environment.execute_tool(call.name, call.arguments)
            else:
                assert router is not None
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
            if not is_stateful and environment.terminal_mode is not None:
                status = "completed"
                break
        if status != "running":
            break
    else:
        status = "turn_budget_exceeded"

    if is_v1:
        score = evaluate_v1_environment(task, environment)
    elif is_v06:
        score = evaluate_v06_environment(task, environment)
    else:
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
        "pair_id": task.get(
            "pair_id",
            task.get("counterfactual_pair_id", task.get("_benchmark_metadata", {}).get("pair_id")),
        ),
        "scenario_id": task.get(
            "scenario_id", task.get("_benchmark_metadata", {}).get("scenario_id")
        ),
        "reasoning_structure": task.get(
            "reasoning_structure",
            task.get("_benchmark_metadata", {}).get("reasoning_structure"),
        ),
        "domain": task.get("domain"),
        "difficulty_level": task.get(
            "difficulty_level",
            task.get("_benchmark_metadata", {}).get("difficulty_level"),
        ),
        "evaluation_track": task.get("evaluation_track"),
        "mechanism": task.get("mechanism"),
        "split": task.get("split"),
        "task_schema_version": task["schema_version"],
        "status": status,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "harness_config": {
            "max_turns": effective_max_turns,
            "max_mutations": None if is_stateful else task.get("max_mutations"),
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
                    metadata = task.get("_benchmark_metadata", {})
                    record = {
                        "run_id": run_id,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "provider": adapter.provider,
                        "model": adapter.model,
                        "task_id": task["task_id"],
                        "family_id": task.get("family_id"),
                        "variant_id": task.get("variant_id"),
                        "pair_id": task.get(
                            "pair_id",
                            task.get(
                                "counterfactual_pair_id",
                                metadata.get("pair_id"),
                            ),
                        ),
                        "scenario_id": task.get(
                            "scenario_id", metadata.get("scenario_id")
                        ),
                        "reasoning_structure": task.get(
                            "reasoning_structure",
                            metadata.get("reasoning_structure"),
                        ),
                        "domain": task.get("domain"),
                        "difficulty_level": task.get(
                            "difficulty_level",
                            metadata.get("difficulty_level"),
                        ),
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
    aggregate_records = [
        record
        for record in records
        if not record.get("score", {}).get("exclude_from_aggregate", False)
    ]
    aggregate_task_groups = _group_records(aggregate_records, "task_id")
    goal_pass_at_1 = _record_rate(aggregate_records, "success")
    optimal_pass_at_1 = _record_rate(aggregate_records, "optimal_repair")
    goal_pass_at_k = _all_repeats_rate(
        aggregate_task_groups, "success", expected_repeats=repeats
    )
    optimal_pass_at_k = _all_repeats_rate(
        aggregate_task_groups, "optimal_repair", expected_repeats=repeats
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
        "oracle_violation_count": sum(
            bool(record.get("score", {}).get("oracle_violation", False))
            for record in records
        ),
        "task_count": len(task_groups),
        "repeats_per_task": repeats,
        "goal_pass@1": goal_pass_at_1,
        "goal_pass@1_stddev": _population_stddev(goal_repeat_rates),
        "goal_pass^k": goal_pass_at_k,
        f"goal_pass^{repeats}": goal_pass_at_k,
        "optimal_pass@1": optimal_pass_at_1,
        "non_dominated_repair_pass@1": optimal_pass_at_1,
        "dominated_repair_rate": _conditional_dominated_rate(
            aggregate_records
        ),
        "scope_optimization_gap@1": (
            goal_pass_at_1 - optimal_pass_at_1
            if goal_pass_at_1 is not None and optimal_pass_at_1 is not None
            else None
        ),
        "optimal_pass@1_stddev": _population_stddev(optimal_repeat_rates),
        "optimal_pass^k": optimal_pass_at_k,
        "non_dominated_repair_pass^k": optimal_pass_at_k,
        "scope_optimization_gap^k": (
            goal_pass_at_k - optimal_pass_at_k
            if goal_pass_at_k is not None and optimal_pass_at_k is not None
            else None
        ),
        f"optimal_pass^{repeats}": optimal_pass_at_k,
        f"non_dominated_repair_pass^{repeats}": optimal_pass_at_k,
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
        "mean_irreversible_loss_regret": _mean(
            [
                score.get("irreversible_loss_regret")
                for score in scored
                if score.get("irreversible_loss_regret") is not None
            ]
        ),
        "mean_net_outlay_regret": _mean(
            [
                score.get("net_outlay_regret")
                for score in scored
                if score.get("net_outlay_regret") is not None
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
    pair_repeat_groups: dict[tuple[str, Any], list[dict[str, Any]]] = {}
    for record in aggregate_records:
        if record.get("pair_id") is None:
            continue
        pair_repeat_groups.setdefault(
            (str(record["pair_id"]), record.get("repeat_index")), []
        ).append(record)
    if pair_repeat_groups:
        pair_success_by_repeat = {
            key: (
                len(group) == 2
                and all(
                    item.get("score", {}).get(
                        "non_dominated_repair", False
                    )
                    for item in group
                )
            )
            for key, group in pair_repeat_groups.items()
        }
        pair_successes = list(pair_success_by_repeat.values())
        summary["counterfactual_pair_success@1"] = (
            sum(pair_successes) / len(pair_successes)
        )
        pair_outcomes: dict[str, list[bool]] = {}
        for (pair_id, _repeat_index), passed in pair_success_by_repeat.items():
            pair_outcomes.setdefault(pair_id, []).append(passed)
        strict_pair_success = sum(
            len(outcomes) == repeats and all(outcomes)
            for outcomes in pair_outcomes.values()
        ) / len(pair_outcomes)
        summary["counterfactual_pair_success^k"] = strict_pair_success
        summary[
            f"counterfactual_pair_success^{repeats}"
        ] = strict_pair_success
    for field in ["domain", "reasoning_structure", "difficulty_level"]:
        groups = _group_records(records, field)
        if groups:
            summary[f"by_{field}"] = {
                key: {
                    "run_count": len(group),
                    "goal_pass@1": _record_rate(group, "success"),
                    "non_dominated_repair_pass@1": _record_rate(
                        group, "optimal_repair"
                    ),
                    "dominated_repair_rate": _conditional_dominated_rate(group),
                }
                for key, group in groups.items()
            }
    return summary


def _rate_gap(records: list[dict[str, Any]]) -> float | None:
    goal = _record_rate(records, "success")
    optimal = _record_rate(records, "optimal_repair")
    return goal - optimal if goal is not None and optimal is not None else None


def _conditional_dominated_rate(
    records: list[dict[str, Any]],
) -> float | None:
    completed = [
        record
        for record in records
        if record.get("score", {}).get("goal_pass", False)
    ]
    if not completed:
        return None
    return sum(
        bool(record.get("score", {}).get("dominated_repair", False))
        for record in completed
    ) / len(completed)


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
