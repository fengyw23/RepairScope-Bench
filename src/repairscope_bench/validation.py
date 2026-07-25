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
    if tasks and tasks[0]["schema_version"] == "2.0":
        return _validate_v2_dataset(tasks, path, gold_path)
    if tasks and tasks[0]["schema_version"] == "1.1":
        return _validate_v11_dataset(tasks, path, gold_path)
    if tasks and tasks[0]["schema_version"] == "1.0":
        return _validate_v1_dataset(tasks, path, gold_path)
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


def _validate_v2_dataset(
    tasks: list[dict[str, Any]],
    path: str | Path,
    gold_path: str | Path | None,
) -> dict[str, Any]:
    from copy import deepcopy

    from .difficulty import build_complexity_profile, coverage_matrix
    from .v1_environment import EconomicVector
    from .v2_oracle import frontier_signature, solve_task_v2

    source = Path(path)
    gold_file = (
        Path(gold_path)
        if gold_path is not None
        else (
            source.parents[1] / "gold" / "v2.json"
            if source.is_dir() and source.parent.name == "v2"
            else _infer_gold_path(path)
        )
    )
    with gold_file.open("r", encoding="utf-8") as handle:
        gold: dict[str, dict[str, Any]] = json.load(handle)
    errors: list[str] = []
    pairs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    loss_trap_tasks = 0
    outlay_trap_tasks = 0
    both_trap_tasks = 0
    multi_frontier_tasks = 0
    positive_loss_gold_tasks = 0
    multi_step_gold_tasks = 0

    for task in tasks:
        expected = gold.get(task["task_id"])
        if expected is None:
            errors.append(f"{task['task_id']}: missing v2 gold")
            continue
        metadata = expected["metadata"]
        pairs[metadata["pair_id"]].append(task)
        oracle = solve_task_v2(task)
        if not oracle.feasible or oracle.feasible_scope_count < 4:
            errors.append(f"{task['task_id']}: insufficient feasible recovery space")
        if len(oracle.frontier) >= oracle.feasible_terminal_count:
            errors.append(f"{task['task_id']}: no dominated terminal")
        if frontier_signature(oracle.frontier) != frontier_signature(
            oracle.replay_frontier
        ):
            errors.append(f"{task['task_id']}: dual Oracles disagree")
        if frontier_signature(oracle.frontier) != frontier_signature(
            expected["oracle"]["frontier"]
        ):
            errors.append(f"{task['task_id']}: frozen frontier is stale")
        multi_frontier_tasks += len(oracle.frontier) > 1
        positive_loss_gold_tasks += any(
            int(item["scope_economic_vector"]["irreversible_loss"]) > 0
            for item in oracle.frontier
        )
        observed_profile = build_complexity_profile(task, oracle, metadata)
        if observed_profile != metadata.get("complexity_profile"):
            errors.append(f"{task['task_id']}: complexity profile is stale")
        multi_step_gold_tasks += observed_profile["minimum_mutations"] >= 3
        if not _replay_v2_boundary(task):
            errors.append(
                f"{task['task_id']}: public writes do not reproduce boundary"
            )

        frontier_vectors = [
            EconomicVector(
                int(item["scope_economic_vector"]["irreversible_loss"]),
                int(item["scope_economic_vector"]["net_recovery_outlay"]),
            )
            for item in oracle.frontier
        ]
        has_loss = has_outlay = has_both = False
        for terminal in oracle.feasible_terminals:
            observed = EconomicVector(
                int(terminal["scope_economic_vector"]["irreversible_loss"]),
                int(terminal["scope_economic_vector"]["net_recovery_outlay"]),
            )
            for accepted in frontier_vectors:
                if not accepted.dominates(observed):
                    continue
                loss_improvement = (
                    observed.irreversible_loss - accepted.irreversible_loss
                )
                outlay_improvement = (
                    observed.net_recovery_outlay
                    - accepted.net_recovery_outlay
                )
                has_loss |= loss_improvement > 0
                has_outlay |= outlay_improvement > 0
                has_both |= loss_improvement > 0 and outlay_improvement > 0
        loss_trap_tasks += has_loss
        outlay_trap_tasks += has_outlay
        both_trap_tasks += has_both

    for pair_id, members in pairs.items():
        if len(members) != 2:
            errors.append(f"{pair_id}: expected two variants")
            continue
        members.sort(
            key=lambda item: gold[item["task_id"]]["metadata"]["variant_role"]
        )
        left, right = members
        left_meta = gold[left["task_id"]]["metadata"]
        right_meta = gold[right["task_id"]]["metadata"]
        if (
            left_meta["intervention"]["json_pointer"]
            != right_meta["intervention"]["json_pointer"]
        ):
            errors.append(f"{pair_id}: variants change different facts")
        normalized_left = deepcopy(
            {key: value for key, value in left.items() if not key.startswith("_")}
        )
        normalized_right = deepcopy(
            {key: value for key, value in right.items() if not key.startswith("_")}
        )
        normalized_left["task_id"] = normalized_right["task_id"] = "<opaque>"
        differences: list[str] = []
        _v2_diff(normalized_left, normalized_right, "", differences)
        if differences != [left_meta["intervention"]["json_pointer"]]:
            errors.append(
                f"{pair_id}: expected one source fact, found {differences}"
            )
        left_scopes = {
            item["scope_key"]
            for item in gold[left["task_id"]]["oracle"]["frontier"]
        }
        right_scopes = {
            item["scope_key"]
            for item in gold[right["task_id"]]["oracle"]["frontier"]
        }
        if left_scopes & right_scopes:
            errors.append(f"{pair_id}: counterfactual gold scopes overlap")

    if len(tasks) != 24 or len(pairs) != 12:
        errors.append("v2 pilot requires 24 tasks in 12 pairs")
    domain_counts = Counter(task["domain"] for task in tasks)
    if set(domain_counts.values()) != {6} or len(domain_counts) != 4:
        errors.append(f"v2 pilot domains are unbalanced: {domain_counts}")
    if multi_frontier_tasks < 3:
        errors.append("v2 pilot requires at least three multi-point frontiers")
    if positive_loss_gold_tasks < 3:
        errors.append("v2 pilot requires positive-loss accepted outcomes")
    if multi_step_gold_tasks < len(tasks) / 2:
        errors.append("fewer than half the pilot tasks require three mutations")

    strategies = [
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
    baselines: dict[str, dict[str, int | float]] = {}
    for strategy in strategies:
        scores = [
            evaluate_actions(task, make_actions(task, strategy)) for task in tasks
        ]
        baselines[strategy] = {
            "goal_pass": sum(item["goal_pass"] for item in scores),
            "scope_pass": sum(
                item["scope_non_dominated_pass"] for item in scores
            ),
            "realized_pass": sum(
                item["realized_non_dominated_pass"] for item in scores
            ),
            "scope_rate": sum(
                item["scope_non_dominated_pass"] for item in scores
            )
            / len(scores),
        }
    if baselines["pareto_oracle"]["realized_pass"] != len(tasks):
        errors.append("v2 Pareto Oracle does not pass every task")
    for strategy in [
        "local_repair",
        "dependency_repair",
        "full_rollback",
        "sticker_price",
        "refund_only",
        "min_changes",
    ]:
        if baselines[strategy]["scope_rate"] >= 0.60:
            errors.append(f"{strategy}: exceeds the 60% pilot ceiling")

    return {
        "valid": not errors,
        "schema_version": "2.0",
        "track": "strict-pilot",
        "task_count": len(tasks),
        "counterfactual_pair_count": len(pairs),
        "domain_counts": dict(domain_counts),
        "construction_strata": dict(
            Counter(
                record["metadata"]["construction_stratum"]
                for record in gold.values()
            )
        ),
        "loss_trap_task_count": loss_trap_tasks,
        "outlay_trap_task_count": outlay_trap_tasks,
        "both_trap_task_count": both_trap_tasks,
        "multi_frontier_task_count": multi_frontier_tasks,
        "positive_loss_gold_task_count": positive_loss_gold_tasks,
        "three_plus_mutation_gold_task_count": multi_step_gold_tasks,
        "coverage_matrix": coverage_matrix(gold),
        "errors": errors,
        "gold_path": str(gold_file.resolve()),
        "baselines": baselines,
    }


def _v2_diff(left: Any, right: Any, path: str, result: list[str]) -> None:
    if type(left) is not type(right):
        result.append(path)
        return
    if isinstance(left, dict):
        for key in sorted(set(left) | set(right)):
            next_path = f"{path}/{key}"
            if key not in left or key not in right:
                result.append(next_path)
            else:
                _v2_diff(left[key], right[key], next_path, result)
        return
    if isinstance(left, list):
        if len(left) != len(right):
            result.append(path)
            return
        for index, (left_item, right_item) in enumerate(
            zip(left, right, strict=True)
        ):
            _v2_diff(left_item, right_item, f"{path}/{index}", result)
        return
    if left != right:
        result.append(path)


def _replay_v2_boundary(task: dict[str, Any]) -> bool:
    from copy import deepcopy

    from .v2_environment import DomainRecoveryEnvironmentV2

    replay_task = deepcopy(
        {key: value for key, value in task.items() if not key.startswith("_")}
    )
    replay_task["failure_snapshot"] = deepcopy(task["initial_snapshot"])
    replay_task["boundary_commitments"] = []
    boundary_options = {
        item["option_id"] for item in task["boundary_commitments"]
    }
    for option in replay_task["inventory"]:
        if option["option_id"] in boundary_options:
            option["available"] = True
    environment = DomainRecoveryEnvironmentV2(replay_task)
    for expected in task["pre_failure_trace"]:
        result = environment.execute_tool(
            expected["tool"], expected["arguments"]
        )
        if result.as_dict() != expected["result"]:
            return False
    failure = task["latest_failure"]
    result = environment.execute_tool(failure["tool"], failure["arguments"])
    replayed = sorted(
        environment.active_commitments(),
        key=lambda item: item["entity_id"],
    )
    for item in replayed:
        item.pop("refund_cents", None)
        source = next(
            option
            for option in task["inventory"]
            if option["option_id"] == item["option_id"]
        )
        item["refund_policy_id"] = source["refund_policy_id"]
        item["created_after_boundary"] = False
    return (
        not result.ok
        and result.as_dict() == failure["result"]
        and {"commitments": replayed} == task["failure_snapshot"]
        and environment.ledger == task["prefix_ledger"]
    )


def _validate_v11_dataset(
    tasks: list[dict[str, Any]],
    path: str | Path,
    gold_path: str | Path | None,
) -> dict[str, Any]:
    from .v1_oracle import frontier_signature, solve_task_v1

    gold_file = (
        Path(gold_path) if gold_path is not None else _infer_gold_path(path)
    )
    with gold_file.open("r", encoding="utf-8") as handle:
        gold: dict[str, dict[str, Any]] = json.load(handle)
    errors: list[str] = []
    pairs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    frontier_sizes: list[int] = []
    positive_gold = 0
    gold_changes_existing = 0
    gold_three_mutations = 0
    single_addition_infeasible = 0

    for task in tasks:
        record = gold.get(task["task_id"])
        if record is None:
            errors.append(f"{task['task_id']}: missing v1.1 private gold")
            continue
        metadata = record.get("metadata", {})
        pair_id = metadata.get("pair_id")
        if not pair_id:
            errors.append(f"{task['task_id']}: missing private pair metadata")
            continue
        pairs[pair_id].append(task)
        leaked = {
            "variant_role",
            "changed_fact",
            "frontier_profile",
            "reasoning_structure",
            "counterfactual_pair_id",
            "pair_id",
        }.intersection(key for key in task if not key.startswith("_"))
        if leaked:
            errors.append(
                f"{task['task_id']}: public metadata leak {sorted(leaked)}"
            )
        oracle = solve_task_v1(task)
        expected = record.get("oracle", {})
        certificate = record.get("validity_certificate", {})
        if not oracle.feasible or oracle.feasible_scope_count < 3:
            errors.append(f"{task['task_id']}: insufficient feasible scopes")
        if oracle.feasible_terminal_count <= len(oracle.frontier):
            errors.append(f"{task['task_id']}: no dominated feasible repair")
        if frontier_signature(oracle.frontier) != frontier_signature(
            oracle.independent_frontier
        ):
            errors.append(f"{task['task_id']}: independent Oracles disagree")
        if frontier_signature(oracle.frontier) != frontier_signature(
            expected.get("frontier", [])
        ):
            errors.append(f"{task['task_id']}: checked-in gold is stale")
        if not all(
            certificate.get(key, False)
            for key in [
                "public_metadata_absent",
                "prefix_generated_by_public_tools",
                "failure_generated_by_public_tool",
                "snapshot_hash_verified",
                "dual_oracle_agreement",
                "irrelevant_wording_invariant",
                "dominated_terminal_exists",
                "gold_replay_within_15_turns",
                "candidate_discoverable_by_capability_search",
                "domain_semantics_linted",
                "counterfactual_frontier_changed",
                "single_logical_fact_intervention",
            ]
        ):
            errors.append(f"{task['task_id']}: invalid validity certificate")
        if not _replay_v1_boundary(task):
            errors.append(f"{task['task_id']}: failure boundary replay failed")
        frontier_sizes.append(len(oracle.frontier))
        if any(
            item["economic_vector"]["irreversible_loss"] > 0
            for item in oracle.frontier
        ):
            positive_gold += 1
        if any(
            any(value != "KEEP" for value in item["scope"].values())
            for item in oracle.frontier
        ):
            gold_changes_existing += 1
        if min(len(item["tool_calls"]) for item in oracle.frontier) >= 3:
            gold_three_mutations += 1
        if not _single_addition_repair_feasible(task):
            single_addition_infeasible += 1

    if len(tasks) != 160:
        errors.append(f"expected 160 v1.1 tasks, found {len(tasks)}")
    if len(pairs) != 80:
        errors.append(f"expected 80 v1.1 pairs, found {len(pairs)}")
    structure_counts = Counter(
        gold[task["task_id"]]["metadata"]["reasoning_structure"]
        for task in tasks
        if task["task_id"] in gold
    )
    domain_counts = Counter(task["domain"] for task in tasks)
    structure_domain_counts = Counter(
        (
            gold[task["task_id"]]["metadata"]["reasoning_structure"],
            task["domain"],
        )
        for task in tasks
        if task["task_id"] in gold
    )
    if set(structure_counts.values()) != {16} or len(structure_counts) != 10:
        errors.append(f"reasoning structures are unbalanced: {structure_counts}")
    if len(domain_counts) != 4 or min(domain_counts.values(), default=0) < 20:
        errors.append(f"domains lack meaningful coverage: {domain_counts}")
    if (
        len(structure_domain_counts) != 40
        or set(structure_domain_counts.values()) != {4}
    ):
        errors.append(
            "reasoning-structure/domain cells are not a balanced 10x4 grid"
        )

    for pair_id, members in pairs.items():
        if len(members) != 2:
            errors.append(f"{pair_id}: expected exactly two variants")
            continue
        first, second = sorted(members, key=lambda item: item["task_id"])
        first_record = gold[first["task_id"]]
        second_record = gold[second["task_id"]]
        if (
            first_record["intervention"]["logical_fact"]
            != second_record["intervention"]["logical_fact"]
        ):
            errors.append(f"{pair_id}: pair changes different logical facts")
        if (
            first_record["intervention"]["value"]
            == second_record["intervention"]["value"]
        ):
            errors.append(f"{pair_id}: intervention values are identical")
        if _normalized_v11_pair_task(first, first_record) != _normalized_v11_pair_task(
            second, second_record
        ):
            errors.append(f"{pair_id}: more than one logical fact changed")
        first_scopes = {
            tuple(sorted(item["scope"].items()))
            for item in first_record["oracle"]["frontier"]
        }
        second_scopes = {
            tuple(sorted(item["scope"].items()))
            for item in second_record["oracle"]["frontier"]
        }
        if first_scopes == second_scopes:
            errors.append(f"{pair_id}: Pareto recovery scope did not change")

    multi_frontier_rate = (
        sum(size >= 2 for size in frontier_sizes) / len(frontier_sizes)
        if frontier_sizes
        else 0
    )
    positive_loss_rate = positive_gold / len(tasks) if tasks else 0
    existing_change_rate = gold_changes_existing / len(tasks) if tasks else 0
    three_mutation_rate = gold_three_mutations / len(tasks) if tasks else 0
    local_infeasible_rate = single_addition_infeasible / len(tasks) if tasks else 0
    pareto_task_ids = [
        task["task_id"]
        for task in tasks
        if gold[task["task_id"]]["metadata"]["reasoning_structure"]
        == "pareto_tradeoff"
    ]
    if any(
        len(gold[task_id]["oracle"]["frontier"]) < 2
        for task_id in pareto_task_ids
    ):
        errors.append("not every Pareto task has a multi-point frontier")
    if existing_change_rate < 0.50:
        errors.append("fewer than 50% of tasks have gold that changes commitments")
    if three_mutation_rate < 0.30:
        errors.append("fewer than 30% of tasks require at least three mutations")
    if local_infeasible_rate < 0.30:
        errors.append("fewer than 30% of tasks reject a one-step local addition")

    strategies = [
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
    baseline_summary: dict[str, dict[str, int | float]] = {}
    for strategy in strategies:
        results = [
            evaluate_actions(task, make_actions(task, strategy)) for task in tasks
        ]
        non_dominated = sum(
            result["non_dominated_repair"] for result in results
        )
        baseline_summary[strategy] = {
            "goal_pass": sum(result["goal_pass"] for result in results),
            "non_dominated_pass": non_dominated,
            "non_dominated_rate": non_dominated / len(tasks),
        }
    if baseline_summary["pareto_oracle"]["non_dominated_pass"] != len(tasks):
        errors.append("Pareto Oracle does not pass every task")
    for strategy in [
        "local_repair",
        "full_rollback",
        "sticker_price",
        "refund_only",
        "min_changes",
    ]:
        if baseline_summary[strategy]["non_dominated_rate"] >= 0.65:
            errors.append(f"{strategy}: heuristic exceeds the 65% ceiling")

    return {
        "valid": not errors,
        "schema_version": "1.1",
        "task_count": len(tasks),
        "scenario_count": len(pairs),
        "counterfactual_pair_count": len(pairs),
        "domain_counts": dict(domain_counts),
        "reasoning_structure_counts": dict(structure_counts),
        "difficulty_counts": dict(
            Counter(
                gold[task["task_id"]]["metadata"]["difficulty_level"]
                for task in tasks
            )
        ),
        "split_counts": dict(Counter(task["split"] for task in tasks)),
        "multi_frontier_rate": multi_frontier_rate,
        "positive_loss_gold_rate": positive_loss_rate,
        "gold_changes_existing_rate": existing_change_rate,
        "three_mutation_gold_rate": three_mutation_rate,
        "single_addition_infeasible_rate": local_infeasible_rate,
        "errors": errors,
        "gold_path": str(gold_file.resolve()),
        "baselines": baseline_summary,
    }


def _single_addition_repair_feasible(task: dict[str, Any]) -> bool:
    from .v1_environment import CommitmentRecoveryEnvironment

    names = CommitmentRecoveryEnvironment(task).names
    for option in task["inventory"]:
        if not option.get("available", False):
            continue
        environment = CommitmentRecoveryEnvironment(task)
        result = environment.execute_tool(
            names["book"], {names["option"]: option["option_id"]}
        )
        passed, _ = environment.goal_status()
        if result.ok and passed:
            return True
    return False


def _normalized_v11_pair_task(
    task: dict[str, Any], record: dict[str, Any]
) -> dict[str, Any]:
    from copy import deepcopy

    normalized = deepcopy({k: v for k, v in task.items() if not k.startswith("_")})
    normalized["task_id"] = "<OPAQUE>"
    normalized["snapshot_sha256"] = "<DERIVED>"
    structure = record["metadata"]["reasoning_structure"]

    if structure in {"sunk_vs_marginal", "pareto_tradeoff"}:
        option_id = normalized["boundary_commitments"][0]["option_id"]
        for item in normalized["inventory"]:
            if item["option_id"] == option_id:
                item["refund_after_purchase_cents"] = "<INTERVENTION>"
        for field in ["failure_snapshot", "boundary_commitments"]:
            values = (
                normalized[field]["commitments"]
                if field == "failure_snapshot"
                else normalized[field]
            )
            for item in values:
                if item["option_id"] == option_id:
                    item["refund_cents"] = "<INTERVENTION>"
    elif structure == "multi_hop_propagation":
        normalized["compatibility_rules"][0]["any_option_ids"] = [
            "<INTERVENTION>"
        ]
    elif structure == "shared_commitment":
        combined = normalized["inventory"][3]
        shared = next(
            capability
            for capability in normalized["hard_goals"]["capabilities"]
            if capability["capability"].endswith("_secondary_use")
        )["capability"]
        combined["provides"][shared] = "<INTERVENTION>"
    elif structure == "nonlinear_threshold":
        contract = normalized["contracts"][0]
        contract["trigger"]["threshold_cents"] = "<INTERVENTION>"
        contract["description"] = "<INTERVENTION>"
    elif structure == "conditional_contract":
        contract = normalized["contracts"][0]
        contract["trigger"]["type"] = "<INTERVENTION>"
        contract["description"] = "<INTERVENTION>"
    elif structure == "partial_quantity":
        normalized["inventory"][4]["upfront_cents"] = "<INTERVENTION>"
    elif structure == "bridge_vs_replacement":
        normalized["inventory"][3]["upfront_cents"] = "<INTERVENTION>"
    elif structure == "joint_bundle_selection":
        normalized["inventory"][5]["upfront_cents"] = "<INTERVENTION>"
    elif structure == "explicit_horizon":
        normalized["inventory"][3]["monthly_cents"] = "<INTERVENTION>"
    return normalized


def _validate_v1_dataset(
    tasks: list[dict[str, Any]],
    path: str | Path,
    gold_path: str | Path | None,
) -> dict[str, Any]:
    from .v1_oracle import frontier_signature, solve_task_v1

    gold_file = (
        Path(gold_path) if gold_path is not None else _infer_gold_path(path)
    )
    with gold_file.open("r", encoding="utf-8") as handle:
        gold: dict[str, dict[str, Any]] = json.load(handle)
    errors: list[str] = []
    pairs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    scenarios: dict[str, list[dict[str, Any]]] = defaultdict(list)
    frontier_sizes: list[int] = []
    positive_gold = 0
    for task in tasks:
        pairs[task["counterfactual_pair_id"]].append(task)
        scenarios[task["scenario_id"]].append(task)
        oracle = solve_task_v1(task)
        expected = gold.get(task["task_id"])
        if expected is None:
            errors.append(f"{task['task_id']}: missing v1 gold")
            continue
        if not oracle.feasible or oracle.feasible_scope_count < 3:
            errors.append(f"{task['task_id']}: insufficient feasible scopes")
        if oracle.feasible_terminal_count <= len(oracle.frontier):
            errors.append(f"{task['task_id']}: no dominated feasible repair")
        if frontier_signature(oracle.frontier) != frontier_signature(
            oracle.independent_frontier
        ):
            errors.append(f"{task['task_id']}: independent Oracles disagree")
        if frontier_signature(oracle.frontier) != frontier_signature(
            expected["frontier"]
        ):
            errors.append(f"{task['task_id']}: checked-in gold is stale")
        frontier_sizes.append(len(oracle.frontier))
        if any(
            item["economic_vector"]["irreversible_loss"] > 0
            for item in oracle.frontier
        ):
            positive_gold += 1
        if not _replay_v1_boundary(task):
            errors.append(f"{task['task_id']}: failure boundary replay failed")

    if len(tasks) != 160:
        errors.append(f"expected 160 v1 tasks, found {len(tasks)}")
    if len(scenarios) != 80 or len(pairs) != 80:
        errors.append("expected 80 independent scenarios and pairs")
    structure_counts = Counter(task["reasoning_structure"] for task in tasks)
    domain_counts = Counter(task["domain"] for task in tasks)
    if set(structure_counts.values()) != {16} or len(structure_counts) != 10:
        errors.append(f"reasoning structures are unbalanced: {structure_counts}")
    if set(domain_counts.values()) != {40} or len(domain_counts) != 4:
        errors.append(f"domains are unbalanced: {domain_counts}")
    for pair_id, members in pairs.items():
        if len(members) != 2:
            errors.append(f"{pair_id}: expected two variants")
            continue
        first, second = sorted(members, key=lambda item: item["variant_role"])
        if _normalized_pair_task(first) != _normalized_pair_task(second):
            errors.append(f"{pair_id}: more than the declared fact changed")
        first_scopes = {
            tuple(sorted(item["scope"].items()))
            for item in gold[first["task_id"]]["frontier"]
        }
        second_scopes = {
            tuple(sorted(item["scope"].items()))
            for item in gold[second["task_id"]]["frontier"]
        }
        if first_scopes == second_scopes:
            errors.append(f"{pair_id}: Pareto recovery scope did not change")

    multi_frontier_rate = (
        sum(size >= 2 for size in frontier_sizes) / len(frontier_sizes)
        if frontier_sizes
        else 0
    )
    positive_gold_rate = positive_gold / len(tasks) if tasks else 0
    if multi_frontier_rate < 0.40:
        errors.append("fewer than 40% of tasks have multi-point frontiers")
    if positive_gold_rate < 0.40:
        errors.append("fewer than 40% of tasks have positive-loss gold points")

    strategies = [
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
    baseline_summary: dict[str, dict[str, int | float]] = {}
    for strategy in strategies:
        results = [
            evaluate_actions(task, make_actions(task, strategy)) for task in tasks
        ]
        nd_pass = sum(result["non_dominated_repair"] for result in results)
        baseline_summary[strategy] = {
            "goal_pass": sum(result["goal_pass"] for result in results),
            "non_dominated_pass": nd_pass,
            "non_dominated_rate": nd_pass / len(tasks),
        }
    if baseline_summary["pareto_oracle"]["non_dominated_pass"] != len(tasks):
        errors.append("Pareto Oracle does not pass every task")
    for strategy in [
        "local_repair",
        "full_rollback",
        "sticker_price",
        "refund_only",
        "min_changes",
    ]:
        if baseline_summary[strategy]["non_dominated_rate"] >= 0.65:
            errors.append(f"{strategy}: heuristic exceeds the 65% ceiling")

    return {
        "valid": not errors,
        "schema_version": "1.0",
        "task_count": len(tasks),
        "scenario_count": len(scenarios),
        "counterfactual_pair_count": len(pairs),
        "domain_counts": dict(domain_counts),
        "reasoning_structure_counts": dict(structure_counts),
        "difficulty_counts": dict(
            Counter(task["difficulty_level"] for task in tasks)
        ),
        "split_counts": dict(Counter(task["split"] for task in tasks)),
        "multi_frontier_rate": multi_frontier_rate,
        "positive_loss_gold_rate": positive_gold_rate,
        "errors": errors,
        "gold_path": str(gold_file.resolve()),
        "baselines": baseline_summary,
    }


def _normalized_pair_task(task: dict[str, Any]) -> dict[str, Any]:
    from copy import deepcopy

    normalized = deepcopy({k: v for k, v in task.items() if not k.startswith("_")})
    for field in [
        "task_id",
        "variant_role",
        "changed_fact",
        "snapshot_sha256",
    ]:
        normalized.pop(field, None)
    changed_path = task["changed_fact"]["changed_path"]
    if changed_path.startswith("boundary_option"):
        option_id = task["boundary_commitments"][0]["option_id"]
        for item in normalized["inventory"]:
            if item["option_id"] == option_id:
                item["refund_after_purchase_cents"] = "<CHANGED>"
        for item in normalized["failure_snapshot"]["commitments"]:
            if item["option_id"] == option_id:
                item["refund_cents"] = "<CHANGED>"
        for item in normalized["boundary_commitments"]:
            if item["option_id"] == option_id:
                item["refund_cents"] = "<CHANGED>"
    else:
        for contract in normalized["contracts"]:
            if contract["contract_id"] == "PAIR-TERM":
                contract["charge_cents"] = "<CHANGED>"
                contract["description"] = "<CHANGED>"
    return normalized


def _replay_v1_boundary(task: dict[str, Any]) -> bool:
    from copy import deepcopy

    from .v1_environment import CommitmentRecoveryEnvironment, snapshot_hash

    replay_task = deepcopy(task)
    replay_task["failure_snapshot"] = deepcopy(task["initial_snapshot"])
    replay_task["boundary_commitments"] = []
    replay_task["contracts"] = []
    replay_task["inventory"] = deepcopy(task["inventory"])
    boundary_options = {
        item["option_id"] for item in task["boundary_commitments"]
    }
    for option in replay_task["inventory"]:
        if option["option_id"] in boundary_options:
            option["available"] = True
    environment = CommitmentRecoveryEnvironment(replay_task)
    for expected in task["pre_failure_trace"]:
        result = environment.execute_tool(expected["tool"], expected["arguments"])
        if result.as_dict() != expected["result"]:
            return False
    failure = task["latest_failure"]
    result = environment.execute_tool(failure["tool"], failure["arguments"])
    replayed_commitments = sorted(
        (deepcopy(item) for item in environment.commitments.values()),
        key=lambda item: item["entity_id"],
    )
    for item in replayed_commitments:
        item["created_after_boundary"] = False
    return (
        not result.ok
        and result.as_dict() == failure["result"]
        and snapshot_hash(
            {
                "commitments": replayed_commitments
            }
        )
        == task["snapshot_sha256"]
        and environment.ledger == task["prefix_ledger"]
    )


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
