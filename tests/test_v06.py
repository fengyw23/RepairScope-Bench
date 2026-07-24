from __future__ import annotations

import unittest
from pathlib import Path

from state_bench.domains.customer_support.environment import (
    CustomerSupportEnvironment,
)
from state_bench.domains.travel.environment import TravelEnvironment

from repairscope_bench.baselines import make_actions
from repairscope_bench.domain_tools import tool_definitions_for_task
from repairscope_bench.evaluator import evaluate_actions
from repairscope_bench.loader import load_tasks
from repairscope_bench.providers.base import ModelTurn, ToolCall
from repairscope_bench.runner import run_episode
from repairscope_bench.v06_environment import (
    EconomicVector,
    StateBackedRecoveryEnvironment,
)
from repairscope_bench.v06_oracle import solve_task_v06
from repairscope_bench.validation import validate_dataset


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "v06"


class ScriptedAdapter:
    provider = "fake"
    model = "scripted-v06"

    def __init__(self, calls):
        self.calls = calls

    def start_session(self, system_prompt, user_prompt, tool_definitions=None):
        return ScriptedSession(self.calls)


class ScriptedSession:
    def __init__(self, calls):
        self.calls = list(calls)
        self.index = 0

    def advance(self, tool_results=None):
        if self.index >= len(self.calls):
            return ModelTurn("The recovery is complete.", [], {})
        call = self.calls[self.index]
        self.index += 1
        return ModelTurn(
            "",
            [
                ToolCall(
                    f"call-{self.index}",
                    call["name"],
                    call.get("arguments", {}),
                )
            ],
            {},
        )


class V06DatasetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tasks = load_tasks(DATA)

    def test_dataset_has_independent_counterfactual_states(self) -> None:
        self.assertEqual(len(self.tasks), 24)
        self.assertEqual(len({task["family_id"] for task in self.tasks}), 6)
        self.assertEqual(
            len({task["counterfactual_pair_id"] for task in self.tasks}), 12
        )
        self.assertTrue(all(task["max_turns"] == 15 for task in self.tasks))
        self.assertNotIn("evaluation_track", self.tasks[0])

    def test_runtime_reuses_state_bench_environments(self) -> None:
        travel = next(task for task in self.tasks if task["domain"] == "travel")
        support = next(
            task for task in self.tasks if task["domain"] == "customer_support"
        )
        self.assertIsInstance(
            StateBackedRecoveryEnvironment(travel).upstream, TravelEnvironment
        )
        self.assertIsInstance(
            StateBackedRecoveryEnvironment(support).upstream,
            CustomerSupportEnvironment,
        )

    def test_prefix_is_real_and_failure_is_persistent(self) -> None:
        for task in self.tasks:
            self.assertGreaterEqual(len(task["pre_failure_trace"]), 5)
            self.assertTrue(
                all(step["result"]["ok"] for step in task["pre_failure_trace"])
            )
            self.assertFalse(task["latest_failure"]["result"]["ok"])
            self.assertGreaterEqual(len(task["boundary_commitments"]), 5)
            self.assertTrue(task["prefix_ledger"])

    def test_search_and_independent_oracles_agree(self) -> None:
        for task in self.tasks:
            oracle = solve_task_v06(task)
            self.assertTrue(oracle.feasible)
            self.assertGreaterEqual(oracle.feasible_scope_count, 3)
            self.assertEqual(
                _frontier_signature(oracle.frontier),
                _frontier_signature(oracle.independent_frontier),
            )

    def test_counterfactual_fact_flips_pareto_scope(self) -> None:
        pairs = {}
        for task in self.tasks:
            pairs.setdefault(task["counterfactual_pair_id"], []).append(task)
        for members in pairs.values():
            self.assertEqual(len(members), 2)
            first, second = members
            self.assertEqual(first["initial_snapshot"], second["initial_snapshot"])
            self.assertEqual(first["option_metadata"], second["option_metadata"])
            self.assertNotEqual(
                solve_task_v06(first).optimal_scopes,
                solve_task_v06(second).optimal_scopes,
            )

    def test_economic_dominance_has_no_subjective_weights(self) -> None:
        self.assertTrue(EconomicVector(0, 100).dominates(EconomicVector(20, 120)))
        self.assertFalse(EconomicVector(0, 150).dominates(EconomicVector(20, 100)))
        self.assertFalse(EconomicVector(20, 100).dominates(EconomicVector(0, 150)))
        self.assertFalse(EconomicVector(0, 100).dominates(EconomicVector(0, 100)))

    def test_goal_completion_and_scope_quality_are_separate(self) -> None:
        local_goal = 0
        local_nondominated = 0
        for task in self.tasks:
            score = evaluate_actions(
                task, make_actions(task, "local_repair")
            )
            local_goal += score["goal_pass"]
            local_nondominated += score["non_dominated_repair"]
        self.assertEqual(local_goal, 24)
        self.assertEqual(local_nondominated, 12)

    def test_contract_adjustment_is_auditable(self) -> None:
        task = next(
            item
            for item in self.tasks
            if item["task_id"] == "conference-dinner-refund-low"
        )
        score = evaluate_actions(
            task, make_actions(task, "full_rollback")
        )
        contract_events = [
            item
            for item in score["transaction_ledger"]
            if item["tool"] == "contract_settlement"
        ]
        self.assertTrue(contract_events)
        self.assertEqual(
            sum(item["irreversible_loss_delta"] for item in contract_events),
            800,
        )
        self.assertTrue(score["goal_pass"])
        self.assertTrue(score["dominated_repair"])
        environment = StateBackedRecoveryEnvironment(task)
        for call in make_actions(task, "full_rollback"):
            environment.execute_tool(call["name"], call["arguments"])
        self.assertEqual(environment.integrity_violations(), [])

    def test_model_tool_surface_has_no_answer_or_finish_tool(self) -> None:
        for task in self.tasks:
            names = {
                item["name"] for item in tool_definitions_for_task(task)
            }
            self.assertNotIn("finish", names)
            self.assertNotIn("get_cost_summary", names)
            self.assertNotIn("get_linked_loss_quote", names)
            self.assertIn("get_contract_terms", names)

    def test_runner_scores_terminal_state_without_finish(self) -> None:
        task = next(
            item
            for item in self.tasks
            if item["task_id"] == "conference-dinner-refund-low"
        )
        calls = make_actions(task, "local_repair")
        record = run_episode(task, ScriptedAdapter(calls))
        self.assertEqual(record["status"], "model_stopped")
        self.assertTrue(record["score"]["goal_pass"])
        self.assertTrue(record["score"]["non_dominated_repair"])
        self.assertIsNone(record["harness_config"]["max_mutations"])
        self.assertEqual(record["harness_config"]["max_turns"], 15)

    def test_full_validation_and_baseline_separation(self) -> None:
        report = validate_dataset(DATA)
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(
            report["baselines"]["pareto_oracle"]["non_dominated_pass"], 24
        )
        self.assertEqual(
            report["baselines"]["full_rollback"]["goal_pass"], 24
        )
        self.assertEqual(
            report["baselines"]["full_rollback"]["non_dominated_pass"], 0
        )


def _frontier_signature(frontier):
    return sorted(
        (
            item["economic_vector"]["irreversible_loss"],
            item["economic_vector"]["net_recovery_outlay"],
            tuple(sorted(item["scope"].items())),
        )
        for item in frontier
    )


if __name__ == "__main__":
    unittest.main()
