from __future__ import annotations

import unittest
from pathlib import Path

from repairscope_bench.baselines import make_actions
from repairscope_bench.domain_tools import DomainToolRouter, tool_definitions_for_task
from repairscope_bench.environment import RepairEnvironment
from repairscope_bench.evaluator import evaluate_actions
from repairscope_bench.loader import load_tasks
from repairscope_bench.oracle import solve_task
from repairscope_bench.providers.base import ModelTurn, ToolCall
from repairscope_bench.runner import run_episode
from repairscope_bench.validation import validate_dataset


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "legacy" / "v0.5" / "challenge"


class ChallengeScriptedAdapter:
    provider = "fake"
    model = "challenge-scripted"

    def start_session(self, system_prompt, user_prompt, tool_definitions=None):
        return ChallengeScriptedSession()


class ChallengeScriptedSession:
    def __init__(self) -> None:
        self.index = 0

    def advance(self, tool_results=None):
        self.index += 1
        if self.index == 1:
            return ModelTurn(
                "",
                [
                    ToolCall(
                        "c1",
                        "search_travel_options",
                        {"category": "dinner"},
                    )
                ],
                {},
            )
        if self.index == 2:
            return ModelTurn(
                "",
                [
                    ToolCall(
                        "c2",
                        "book_travel_option",
                        {"option_id": "DINNER-HUANGPU"},
                    )
                ],
                {},
            )
        return ModelTurn("The requested trip is now complete.", [], {})


class ChallengeDatasetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tasks = load_tasks(DATA)

    def test_paired_shape_and_mechanism_splits(self) -> None:
        self.assertEqual(len(self.tasks), 12)
        pairs: dict[str, set[str]] = {}
        for task in self.tasks:
            pairs.setdefault(task["pair_id"], set()).add(task["evaluation_track"])
        self.assertEqual(len(pairs), 6)
        self.assertTrue(
            all(tracks == {"goal", "loss_aware"} for tracks in pairs.values())
        )
        self.assertEqual(
            {task["split"] for task in self.tasks}, {"dev", "test", "heldout"}
        )
        self.assertEqual(len({task["mechanism"] for task in self.tasks}), 3)

    def test_loss_tasks_pass_strict_repair_graph_gates(self) -> None:
        for task in self.tasks:
            if task["evaluation_track"] != "loss_aware":
                continue
            oracle = solve_task(task)
            gates = task["challenge_requirements"]
            self.assertGreaterEqual(oracle.raw_plan_count, gates["min_raw_plans"])
            self.assertGreaterEqual(
                oracle.feasible_plan_count, gates["min_feasible_plans"]
            )
            self.assertGreaterEqual(
                oracle.feasible_scope_count, gates["min_feasible_scopes"]
            )
            self.assertGreaterEqual(
                len(oracle.feasible_recovery_losses), gates["min_loss_levels"]
            )

    def test_counterfactuals_change_optimal_scope(self) -> None:
        families: dict[str, dict[str, dict[str, str]]] = {}
        for task in self.tasks:
            if task["evaluation_track"] != "loss_aware":
                continue
            families.setdefault(task["family_id"], {})[
                task["variant_id"].split("-")[0]
            ] = solve_task(task).optimal_scopes[0]
        for outcomes in families.values():
            self.assertEqual(set(outcomes), {"A", "B"})
            self.assertNotEqual(outcomes["A"], outcomes["B"])

    def test_linked_loss_is_auditable_and_charged_once(self) -> None:
        task = next(
            item
            for item in self.tasks
            if item["task_id"] == "conference-dinner-b-loss-aware"
        )
        environment = RepairEnvironment(task)
        router = DomainToolRouter(environment)
        quote = router.execute(
            "get_package_change_impact", {"reservation_id": "TR-HOTEL"}
        )
        self.assertTrue(quote.ok)
        self.assertEqual(quote.data[0]["settlement_charge"], 180)
        environment.execute(
            {"action": "cancel", "args": {"commitment_id": "TR-HOTEL"}}
        )
        self.assertEqual(environment.linked_loss, 180)

    def test_search_uses_public_category_without_hidden_literal(self) -> None:
        task = next(
            item
            for item in self.tasks
            if item["task_id"] == "conference-dinner-a-loss-aware"
        )
        router = DomainToolRouter(RepairEnvironment(task))
        result = router.execute(
            "search_travel_options", {"category": "dinner"}
        )
        self.assertGreater(len(result.data), 0)
        self.assertTrue(
            all(item["type"] == "dinner" for item in result.data)
        )

    def test_v05_tool_schema_is_domain_native_and_dynamic(self) -> None:
        shopping = next(task for task in self.tasks if task["domain"] == "shopping")
        tools = tool_definitions_for_task(shopping)
        search = next(item for item in tools if item["name"] == "search_products")
        categories = search["parameters"]["properties"]["category"]["enum"]
        self.assertEqual(set(categories), set(shopping["required_slots"]))
        self.assertEqual(search["parameters"]["required"], ["category"])
        self.assertNotIn("use_case", search["parameters"]["properties"])
        self.assertNotIn("finish", {item["name"] for item in tools})
        self.assertNotIn("search_options", {item["name"] for item in tools})

    def test_v05_model_tool_loop_reaches_oracle_state(self) -> None:
        task = next(
            item
            for item in self.tasks
            if item["task_id"] == "conference-dinner-a-loss-aware"
        )
        record = run_episode(task, ChallengeScriptedAdapter())
        self.assertEqual(record["status"], "model_stopped")
        self.assertTrue(record["score"]["optimal_repair"])
        self.assertFalse(record["score"]["finish_called"])
        self.assertEqual(record["harness_config"]["max_turns"], 15)
        self.assertEqual(record["harness_config"]["max_mutations"], 14)

    def test_feasible_state_passes_without_finish_action(self) -> None:
        task = next(
            item
            for item in self.tasks
            if item["task_id"] == "conference-dinner-a-loss-aware"
        )
        score = evaluate_actions(
            task,
            [
                {
                    "action": "book",
                    "args": {"option_id": "DINNER-HUANGPU"},
                }
            ],
        )
        self.assertTrue(score["success"])
        self.assertTrue(score["optimal_repair"])
        self.assertFalse(score["finish_called"])

    def test_wrong_infeasibility_report_still_fails(self) -> None:
        task = next(
            item
            for item in self.tasks
            if item["task_id"] == "conference-dinner-a-loss-aware"
        )
        score = evaluate_actions(
            task,
            [
                {
                    "action": "book",
                    "args": {"option_id": "DINNER-HUANGPU"},
                },
                {
                    "action": "report_infeasible",
                    "args": {"reason": "No repair exists."},
                },
            ],
        )
        self.assertTrue(score["goal_pass"])
        self.assertTrue(score["reported_infeasible"])
        self.assertFalse(score["success"])

    def test_oracle_passes_but_loss_blind_baseline_does_not_optimize(self) -> None:
        oracle_passes = 0
        cost_optimal = 0
        for task in self.tasks:
            oracle_score = evaluate_actions(task, make_actions(task, "oracle"))
            cost_score = evaluate_actions(task, make_actions(task, "global_cost"))
            oracle_passes += oracle_score["optimal_repair"]
            cost_optimal += cost_score["optimal_repair"]
            self.assertTrue(cost_score["success"])
        self.assertEqual(oracle_passes, len(self.tasks))
        self.assertLess(cost_optimal, len(self.tasks))

    def test_dataset_validation(self) -> None:
        report = validate_dataset(DATA)
        self.assertTrue(report["valid"], report["errors"])


if __name__ == "__main__":
    unittest.main()
