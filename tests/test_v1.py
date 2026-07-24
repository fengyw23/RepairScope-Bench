from __future__ import annotations

from collections import Counter
from pathlib import Path
import unittest

from repairscope_bench.baselines import make_actions
from repairscope_bench.domain_tools import tool_definitions_for_task
from repairscope_bench.loader import load_tasks
from repairscope_bench.providers.base import ModelTurn, ToolCall
from repairscope_bench.runner import run_episode
from repairscope_bench.v1_environment import CommitmentRecoveryEnvironment
from repairscope_bench.v1_evaluator import evaluate_v1_environment
from repairscope_bench.v1_oracle import frontier_signature, solve_task_v1
from repairscope_bench.validation import validate_dataset


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "v1"


class ScriptedAdapter:
    provider = "fake"
    model = "scripted-v1"

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
            return ModelTurn("Done.", [], {})
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


class V1DatasetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tasks = load_tasks(DATA)

    def test_balanced_reasoning_matrix(self) -> None:
        self.assertEqual(len(self.tasks), 160)
        self.assertEqual(len({task["scenario_id"] for task in self.tasks}), 80)
        self.assertEqual(
            len({task["counterfactual_pair_id"] for task in self.tasks}), 80
        )
        self.assertEqual(
            set(Counter(task["domain"] for task in self.tasks).values()), {40}
        )
        self.assertEqual(
            set(
                Counter(
                    task["reasoning_structure"] for task in self.tasks
                ).values()
            ),
            {16},
        )

    def test_tasks_contain_no_authored_oracle_macros(self) -> None:
        for task in self.tasks:
            self.assertNotIn("oracle_actions", task)
            self.assertNotIn("candidate_scopes", task)
            self.assertTrue(
                task["construction"]["necessary_action_order_invariant"]
            )

    def test_independent_oracles_agree(self) -> None:
        for task in self.tasks:
            oracle = solve_task_v1(task)
            self.assertGreaterEqual(oracle.feasible_scope_count, 3)
            self.assertGreater(
                oracle.feasible_terminal_count, len(oracle.frontier)
            )
            self.assertEqual(
                frontier_signature(oracle.frontier),
                frontier_signature(oracle.independent_frontier),
            )

    def test_counterfactual_pairs_change_frontier_scope(self) -> None:
        pairs = {}
        for task in self.tasks:
            pairs.setdefault(task["counterfactual_pair_id"], []).append(task)
        for members in pairs.values():
            self.assertEqual(len(members), 2)
            scopes = [
                {
                    tuple(sorted(item["scope"].items()))
                    for item in solve_task_v1(task).frontier
                }
                for task in members
            ]
            self.assertNotEqual(scopes[0], scopes[1])

    def test_frontiers_include_real_tradeoffs(self) -> None:
        oracles = [solve_task_v1(task) for task in self.tasks]
        self.assertGreaterEqual(
            sum(len(item.frontier) >= 2 for item in oracles) / len(oracles),
            0.40,
        )
        self.assertGreaterEqual(
            sum(
                any(
                    point["economic_vector"]["irreversible_loss"] > 0
                    for point in item.frontier
                )
                for item in oracles
            )
            / len(oracles),
            0.40,
        )

    def test_model_surface_has_no_answer_or_finish(self) -> None:
        for task in self.tasks:
            names = {item["name"] for item in tool_definitions_for_task(task)}
            self.assertNotIn("finish", names)
            self.assertNotIn("get_cost_summary", names)
            self.assertEqual(len(names), 8)

    def test_runner_accepts_natural_stop(self) -> None:
        task = self.tasks[0]
        calls = make_actions(task, "pareto_oracle")
        record = run_episode(task, ScriptedAdapter(calls))
        self.assertEqual(record["status"], "model_stopped")
        self.assertTrue(record["score"]["goal_pass"])
        self.assertTrue(record["score"]["non_dominated_repair"])
        self.assertIsNone(record["harness_config"]["max_mutations"])

    def test_necessary_action_order_does_not_change_economics(self) -> None:
        task = next(
            item
            for item in self.tasks
            if any(
                point["changed_boundary_entities"]
                for point in solve_task_v1(item).frontier
            )
        )
        point = next(
            item
            for item in solve_task_v1(task).frontier
            if item["changed_boundary_entities"]
        )
        mutations = [
            call
            for call in point["tool_calls"]
            if call["name"]
            not in {
                CommitmentRecoveryEnvironment(task).names["preview"],
            }
        ]
        forward = CommitmentRecoveryEnvironment(task)
        reverse = CommitmentRecoveryEnvironment(task)
        for call in mutations:
            self.assertTrue(
                forward.execute_tool(call["name"], call["arguments"]).ok
            )
        for call in reversed(mutations):
            self.assertTrue(
                reverse.execute_tool(call["name"], call["arguments"]).ok
            )
        self.assertEqual(forward.economic_vector, reverse.economic_vector)
        self.assertEqual(forward.goal_status(), reverse.goal_status())

    def test_unnecessary_mutation_is_scored_as_execution_waste(self) -> None:
        task = self.tasks[0]
        environment = CommitmentRecoveryEnvironment(task)
        names = environment.names
        decoy = next(
            item for item in task["inventory"] if item["option_id"].endswith("-decoy")
        )
        self.assertTrue(
            environment.execute_tool(
                names["book"], {names["option"]: decoy["option_id"]}
            ).ok
        )
        new_id = max(
            environment.commitments,
            key=lambda item: int(item.split("-")[-1])
            if item.startswith("NEW-")
            else -1,
        )
        self.assertTrue(
            environment.execute_tool(
                names["cancel"], {names["id"]: new_id, "confirm": True}
            ).ok
        )
        for call in make_actions(task, "pareto_oracle"):
            environment.execute_tool(call["name"], call["arguments"])
        score = evaluate_v1_environment(task, environment)
        self.assertTrue(score["goal_pass"])
        self.assertTrue(score["dominated_repair"])
        self.assertTrue(score["correct_scope_wasteful_execution"])

    def test_full_dataset_validation(self) -> None:
        report = validate_dataset(DATA)
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["task_count"], 160)
        self.assertEqual(
            report["baselines"]["pareto_oracle"]["non_dominated_pass"], 160
        )


if __name__ == "__main__":
    unittest.main()
