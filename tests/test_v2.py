from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from repairscope_bench.difficulty import calibrate_rasch, coverage_matrix
from repairscope_bench.domain_tools import tool_definitions_for_task
from repairscope_bench.loader import load_tasks
from repairscope_bench.providers.base import ModelTurn, ToolCall
from repairscope_bench.runner import run_episode, summarize_runs
from repairscope_bench.validation import validate_dataset
from repairscope_bench.v2_environment import (
    DOMAIN_INTERFACES,
    DomainRecoveryEnvironmentV2,
)
from repairscope_bench.v2_evaluator import evaluate_v2_environment
from repairscope_bench.v2_oracle import frontier_signature, solve_task_v2


ROOT = Path(__file__).resolve().parents[1]


class GoldAdapter:
    provider = "fake"
    model = "v2-gold"

    def __init__(self, calls: list[dict]) -> None:
        self.calls = calls

    def start_session(self, system_prompt, user_prompt, tool_definitions=None):
        return GoldSession(self.calls)


class GoldSession:
    def __init__(self, calls: list[dict]) -> None:
        self.calls = calls
        self.index = 0

    def advance(self, tool_results=None):
        if self.index >= len(self.calls):
            return ModelTurn("done", [], {})
        call = self.calls[self.index]
        self.index += 1
        return ModelTurn(
            "",
            [
                ToolCall(
                    f"call-{self.index}",
                    call["name"],
                    call["arguments"],
                )
            ],
            {},
        )


class V2PilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tasks = load_tasks(ROOT / "data" / "v2" / "pilot")
        cls.gold = json.loads(
            (ROOT / "data" / "gold" / "v2.json").read_text(encoding="utf-8")
        )
        active_ids = {task["task_id"] for task in cls.tasks}
        cls.gold = {
            task_id: record
            for task_id, record in cls.gold.items()
            if task_id in active_ids
        }

    def test_strict_pilot_shape_and_coverage(self) -> None:
        # Four evidence-incomplete quantity tasks were invalidated before v3.
        self.assertEqual(len(self.tasks), 20)
        self.assertEqual(
            {task["domain"] for task in self.tasks},
            {"travel", "after_sales", "saas", "event_logistics"},
        )
        pairs = {
            record["metadata"]["pair_id"] for record in self.gold.values()
        }
        self.assertEqual(len(pairs), 10)
        mechanisms = {
            mechanism
            for record in self.gold.values()
            for mechanism in record["metadata"]["reasoning_signature"]
        }
        self.assertEqual(len(mechanisms), 9)
        self.assertTrue(coverage_matrix(self.gold))

    def test_dual_oracles_agree_on_every_frontier(self) -> None:
        for task in self.tasks:
            oracle = solve_task_v2(task)
            self.assertTrue(oracle.feasible)
            self.assertGreaterEqual(oracle.feasible_scope_count, 4)
            self.assertEqual(
                frontier_signature(oracle.frontier),
                frontier_signature(oracle.replay_frontier),
            )

    def test_counterfactual_gold_scope_sets_are_disjoint(self) -> None:
        pairs: dict[str, list[str]] = {}
        for task_id, record in self.gold.items():
            pairs.setdefault(record["metadata"]["pair_id"], []).append(task_id)
        for members in pairs.values():
            self.assertEqual(len(members), 2)
            left, right = members
            left_scopes = {
                item["scope_key"]
                for item in self.gold[left]["oracle"]["frontier"]
            }
            right_scopes = {
                item["scope_key"]
                for item in self.gold[right]["oracle"]["frontier"]
            }
            self.assertFalse(left_scopes & right_scopes)

    def test_domain_interfaces_are_not_shared_tool_names(self) -> None:
        tool_name_sets = []
        for domain in DOMAIN_INTERFACES:
            task = next(item for item in self.tasks if item["domain"] == domain)
            names = {item["name"] for item in tool_definitions_for_task(task)}
            self.assertEqual(len(names), 8)
            tool_name_sets.append(names)
        for index, left in enumerate(tool_name_sets):
            for right in tool_name_sets[index + 1 :]:
                self.assertFalse(left & right)

    def test_scope_and_realized_economics_are_separate(self) -> None:
        task = self.tasks[0]
        oracle = solve_task_v2(task)
        environment = DomainRecoveryEnvironmentV2(task)
        interface = DOMAIN_INTERFACES[task["domain"]]
        gold_added = set(
            oracle.frontier[0]["scope_signature"]["added_option_ids"]
        )
        waste = next(
            option
            for option in task["inventory"]
            if option.get("available", False)
            and option["option_id"] not in gold_added
        )
        booked = environment.execute_tool(
            interface["book"], {interface["option"]: waste["option_id"]}
        )
        self.assertTrue(booked.ok)
        cancelled = environment.execute_tool(
            interface["cancel"],
            {
                interface["entity"]: booked.data["entity_id"],
                "confirm": True,
            },
        )
        self.assertTrue(cancelled.ok)
        for call in oracle.frontier[0]["tool_calls"]:
            self.assertTrue(
                environment.execute_tool(
                    call["name"], call["arguments"]
                ).ok
            )
        score = evaluate_v2_environment(task, environment)
        self.assertTrue(score["goal_pass"])
        self.assertTrue(score["scope_non_dominated_pass"])
        self.assertFalse(score["realized_non_dominated_pass"])
        self.assertTrue(score["correct_scope_wasteful_execution"])

    def test_changed_fact_query_is_logged_before_mutation(self) -> None:
        task = self.tasks[0]
        metadata = self.gold[task["task_id"]]["metadata"]
        task["_benchmark_metadata"] = metadata
        environment = DomainRecoveryEnvironmentV2(task)
        manifest = metadata["key_fact_manifest"]
        interface = DOMAIN_INTERFACES[task["domain"]]
        query_arguments = (
            {"record_id": manifest["record_id"]}
            if manifest["reveal_tool"] == interface["policy"]
            else {interface["category"]: manifest["record_id"]}
        )
        result = environment.execute_tool(
            manifest["reveal_tool"],
            query_arguments,
        )
        self.assertTrue(result.ok)
        for call in solve_task_v2(task).frontier[0]["tool_calls"]:
            environment.execute_tool(call["name"], call["arguments"])
        score = evaluate_v2_environment(task, environment)
        self.assertTrue(
            score["changed_fact_acquisition"][
                "queried_before_first_mutation"
            ]
        )

    def test_scope_distance_counts_wrong_added_option(self) -> None:
        selected = None
        for task in self.tasks:
            oracle = solve_task_v2(task)
            accepted = oracle.accepted_scope_keys
            accepted_boundaries = {
                json.dumps(
                    item["scope_signature"]["boundary"], sort_keys=True
                )
                for item in oracle.frontier
            }
            for terminal in oracle.feasible_terminals:
                signature = terminal["scope_signature"]
                if (
                    terminal["scope_key"] not in accepted
                    and json.dumps(signature["boundary"], sort_keys=True)
                    in accepted_boundaries
                ):
                    selected = (task, terminal)
                    break
            if selected is not None:
                break
        self.assertIsNotNone(selected)
        task, terminal = selected
        environment = DomainRecoveryEnvironmentV2(task)
        interface = DOMAIN_INTERFACES[task["domain"]]
        for entity_id in terminal["changed_boundary_entities"]:
            self.assertTrue(
                environment.execute_tool(
                    interface["cancel"],
                    {interface["entity"]: entity_id, "confirm": True},
                ).ok
            )
        for option_id in terminal["scope_signature"]["added_option_ids"]:
            self.assertTrue(
                environment.execute_tool(
                    interface["book"], {interface["option"]: option_id}
                ).ok
            )
        score = evaluate_v2_environment(task, environment)
        self.assertTrue(score["goal_pass"])
        self.assertFalse(score["scope_non_dominated_pass"])
        self.assertGreater(score["scope_distance"], 0.0)

    def test_changed_fact_acquisition_normalizes_search_alias(self) -> None:
        task = next(
            item
            for item in self.tasks
            if item["domain"] == "saas"
            and self.gold[item["task_id"]]["metadata"][
                "key_fact_manifest"
            ]["reveal_tool"]
            == DOMAIN_INTERFACES["saas"]["search"]
        )
        metadata = self.gold[task["task_id"]]["metadata"]
        environment = DomainRecoveryEnvironmentV2(task)
        manifest = metadata["key_fact_manifest"]
        interface = DOMAIN_INTERFACES["saas"]
        self.assertTrue(
            environment.execute_tool(
                interface["search"],
                {interface["category"]: manifest["record_id"]},
            ).ok
        )
        score = evaluate_v2_environment(task, environment)
        self.assertTrue(
            score["changed_fact_acquisition"][
                "queried_before_first_mutation"
            ]
        )

    def test_changed_fact_acquisition_accepts_equivalent_option_id(self) -> None:
        selected = None
        for task in self.tasks:
            metadata = self.gold[task["task_id"]]["metadata"]
            manifest = metadata["key_fact_manifest"]
            interface = DOMAIN_INTERFACES[task["domain"]]
            if manifest["reveal_tool"] != interface["policy"]:
                continue
            commitment = next(
                (
                    item
                    for item in task["boundary_commitments"]
                    if item["entity_id"] == manifest["record_id"]
                ),
                None,
            )
            if commitment is not None:
                selected = (task, commitment["option_id"])
                break
        self.assertIsNotNone(selected)
        task, equivalent_option_id = selected
        interface = DOMAIN_INTERFACES[task["domain"]]
        environment = DomainRecoveryEnvironmentV2(task)
        self.assertTrue(
            environment.execute_tool(
                interface["policy"],
                {"record_id": equivalent_option_id},
            ).ok
        )
        score = evaluate_v2_environment(task, environment)
        self.assertTrue(
            score["changed_fact_acquisition"][
                "queried_before_first_mutation"
            ]
        )

    def test_rasch_calibration_orders_easy_and_hard_items(self) -> None:
        records = []
        for model in ["small", "large"]:
            for repeat in range(4):
                records.extend(
                    [
                        {
                            "provider": "test",
                            "model": model,
                            "task_id": "easy",
                            "score": {"scope_non_dominated_pass": True},
                        },
                        {
                            "provider": "test",
                            "model": model,
                            "task_id": "hard",
                            "score": {
                                "scope_non_dominated_pass": (
                                    model == "large" and repeat == 0
                                )
                            },
                        },
                    ]
                )
        result = calibrate_rasch(
            records, calibration_version="unit-test"
        )
        self.assertLess(
            result["items"]["easy"]["difficulty_beta"],
            result["items"]["hard"]["difficulty_beta"],
        )
        self.assertEqual(result["calibration_version"], "unit-test")

    def test_repository_validator_rejects_incomplete_legacy_pilot(self) -> None:
        result = validate_dataset(ROOT / "data" / "v2" / "pilot")
        self.assertFalse(result["valid"])
        self.assertIn(
            "v2 pilot requires 24 tasks in 12 pairs", result["errors"]
        )

    def test_evaluation_reads_frozen_gold_without_searching(self) -> None:
        task = self.tasks[0]
        calls = solve_task_v2(task).frontier[0]["tool_calls"]
        with patch(
            "repairscope_bench.v2_evaluator.solve_task_v2",
            side_effect=AssertionError("evaluation should use frozen gold"),
        ):
            environment = DomainRecoveryEnvironmentV2(task)
            for call in calls:
                environment.execute_tool(call["name"], call["arguments"])
            score = evaluate_v2_environment(task, environment)
        self.assertTrue(score["scope_non_dominated_pass"])

    def test_summary_preserves_scope_execution_gap(self) -> None:
        records = [
            {
                "task_id": "left",
                "pair_id": "pair",
                "repeat_index": 1,
                "score": {
                    "success": True,
                    "scope_non_dominated_pass": True,
                    "optimal_repair": False,
                    "scope_signature": {"added": ["A"]},
                },
            },
            {
                "task_id": "right",
                "pair_id": "pair",
                "repeat_index": 1,
                "score": {
                    "success": True,
                    "scope_non_dominated_pass": True,
                    "optimal_repair": True,
                    "scope_signature": {"added": ["B"]},
                },
            },
        ]
        summary = summarize_runs(records, expected_repeats=1)
        self.assertEqual(summary["goal_pass@1"], 1.0)
        self.assertEqual(summary["scope_non_dominated_pass@1"], 1.0)
        self.assertEqual(summary["realized_non_dominated_pass@1"], 0.5)
        self.assertEqual(summary["execution_efficiency_gap@1"], 0.5)
        self.assertEqual(summary["adaptive_scope_switch@1"], 1.0)

    def test_model_runner_executes_v2_public_tool_trace(self) -> None:
        task = self.tasks[0]
        calls = solve_task_v2(task).frontier[0]["tool_calls"]
        record = run_episode(task, GoldAdapter(calls))
        self.assertEqual(record["status"], "model_stopped")
        self.assertTrue(record["score"]["goal_pass"])
        self.assertTrue(record["score"]["scope_non_dominated_pass"])
        self.assertTrue(record["score"]["realized_non_dominated_pass"])
        self.assertEqual(
            record["harness_config"]["max_turns"], task["max_turns"]
        )


if __name__ == "__main__":
    unittest.main()
