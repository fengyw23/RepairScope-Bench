from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import math
from statistics import median
from typing import Any


def build_complexity_profile(
    task: dict[str, Any],
    oracle: Any,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    manifests = metadata.get("key_fact_manifests")
    if manifests is None:
        manifests = [metadata["key_fact_manifest"]]
    minimum_mutations = min(
        (len(item["tool_calls"]) for item in oracle.frontier),
        default=0,
    )
    profile = {
        "boundary_commitments": len(task["boundary_commitments"]),
        "available_options": sum(
            bool(item.get("available", False)) for item in task["inventory"]
        ),
        "key_facts": len(manifests),
        "dependency_depth": int(metadata["dependency_depth"]),
        "feasible_scope_count": int(oracle.feasible_scope_count),
        "frontier_size": len(oracle.frontier),
        "minimum_mutations": minimum_mutations,
        "interacting_mechanisms": len(metadata["reasoning_signature"]),
    }
    profile["construction_score"] = construction_score(profile)
    profile["construction_stratum"] = construction_stratum(
        profile["construction_score"]
    )
    return profile


def construction_score(profile: dict[str, int]) -> int:
    """Pre-registered structural score; it is not an empirical difficulty label."""
    return (
        math.ceil(math.log2(int(profile["feasible_scope_count"]) + 1))
        + int(profile["dependency_depth"])
        + math.ceil(int(profile["key_facts"]) / 2)
        + math.ceil(int(profile["minimum_mutations"]) / 2)
        + max(0, int(profile["interacting_mechanisms"]) - 1)
    )


def construction_stratum(score: int) -> str:
    if score <= 6:
        return "C1"
    if score <= 9:
        return "C2"
    if score <= 12:
        return "C3"
    return "C4"


def calibrate_rasch(
    records: list[dict[str, Any]],
    *,
    response_field: str = "scope_non_dominated_pass",
    calibration_version: str,
    iterations: int = 80,
    regularization: float = 0.2,
) -> dict[str, Any]:
    """Fit a small regularized Rasch model to frozen calibration runs."""
    observations: list[tuple[str, str, int]] = []
    for record in records:
        score = record.get("score", record)
        if response_field not in score:
            continue
        agent = "::".join(
            [
                str(record.get("provider", "unknown")),
                str(record.get("model", "unknown")),
                str(record.get("harness_config", {}).get("reasoning_effort")),
            ]
        )
        observations.append(
            (agent, str(record["task_id"]), int(bool(score[response_field])))
        )
    if not observations:
        raise ValueError(f"No responses contain {response_field!r}")

    agents = sorted({item[0] for item in observations})
    tasks = sorted({item[1] for item in observations})
    by_agent: dict[str, list[tuple[str, int]]] = defaultdict(list)
    by_task: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for agent, task, response in observations:
        by_agent[agent].append((task, response))
        by_task[task].append((agent, response))

    theta = {agent: 0.0 for agent in agents}
    beta = {task: 0.0 for task in tasks}
    for _ in range(iterations):
        for agent in agents:
            gradient = -regularization * theta[agent]
            curvature = regularization
            for task, response in by_agent[agent]:
                probability = _sigmoid(theta[agent] - beta[task])
                gradient += response - probability
                curvature += probability * (1.0 - probability)
            theta[agent] = _clamp(theta[agent] + gradient / curvature)
        centre = median(theta.values())
        theta = {key: value - centre for key, value in theta.items()}
        for task in tasks:
            gradient = -regularization * beta[task]
            curvature = regularization
            for agent, response in by_task[task]:
                probability = _sigmoid(theta[agent] - beta[task])
                gradient += probability - response
                curvature += probability * (1.0 - probability)
            beta[task] = _clamp(beta[task] + gradient / curvature)

    item_results = {}
    for task in tasks:
        predicted = _sigmoid(-beta[task])
        raw = [response for _agent, response in by_task[task]]
        item_results[task] = {
            "difficulty_beta": round(beta[task], 6),
            "median_agent_pass_probability": round(predicted, 6),
            "difficulty_band": difficulty_band(predicted),
            "observed_pass_rate": sum(raw) / len(raw),
            "observation_count": len(raw),
        }
    return {
        "calibration_version": calibration_version,
        "response_field": response_field,
        "agent_ability": {key: round(value, 6) for key, value in theta.items()},
        "items": item_results,
        "anchor_tasks": select_anchor_tasks(item_results),
    }


def difficulty_band(median_agent_pass_probability: float) -> str:
    if median_agent_pass_probability >= 0.75:
        return "easy"
    if median_agent_pass_probability >= 0.50:
        return "medium"
    if median_agent_pass_probability >= 0.25:
        return "hard"
    return "extreme"


def select_anchor_tasks(
    item_results: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    targets = [0.85, 0.65, 0.35, 0.15]
    selected: list[dict[str, Any]] = []
    used: set[str] = set()
    for target in targets:
        candidates = [
            (abs(item["median_agent_pass_probability"] - target), task_id, item)
            for task_id, item in item_results.items()
            if task_id not in used
        ]
        if not candidates:
            break
        _distance, task_id, item = min(candidates)
        used.add(task_id)
        selected.append(
            {
                "task_id": task_id,
                "target_probability": target,
                **deepcopy(item),
            }
        )
    return selected


def coverage_matrix(
    metadata_records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    matrix: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )
    for record in metadata_records.values():
        metadata = record["metadata"]
        domain = metadata["domain"]
        stratum = metadata["construction_stratum"]
        for mechanism in metadata["reasoning_signature"]:
            matrix[mechanism][domain][stratum] += 1
    return {
        mechanism: {
            domain: dict(sorted(strata.items()))
            for domain, strata in sorted(domains.items())
        }
        for mechanism, domains in sorted(matrix.items())
    }


def _sigmoid(value: float) -> float:
    if value >= 0:
        exponent = math.exp(-value)
        return 1.0 / (1.0 + exponent)
    exponent = math.exp(value)
    return exponent / (1.0 + exponent)


def _clamp(value: float) -> float:
    return max(-6.0, min(6.0, value))


__all__ = [
    "build_complexity_profile",
    "calibrate_rasch",
    "construction_score",
    "construction_stratum",
    "coverage_matrix",
    "difficulty_band",
    "select_anchor_tasks",
]
