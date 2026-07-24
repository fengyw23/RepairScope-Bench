from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import unittest

from repairscope_bench.baselines import make_actions
from repairscope_bench.domain_tools import tool_definitions_for_task
from repairscope_bench.evaluator import evaluate_actions
from repairscope_bench.loader import load_tasks
from repairscope_bench.v1_environment import CommitmentRecoveryEnvironment
from repairscope_bench.v1_oracle import frontier_signature, solve_task_v1
from repairscope_bench.validation import (
    _replay_v1_boundary,
    _single_addition_repair_feasible,
)


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "v11"
GOLD = ROOT / "data" / "gold" / "v11.json"


class V11ReleaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tasks = load_tasks(DATA)
        cls.gold = json.loads(GOLD.read_text(encoding="utf-8"))

    def test_reasoning_structure_domain_cross_product(self) -> None:
        self.assertEqual(len(self.tasks), 160)
        cells = Counter(
            (
                task["_benchmark_metadata"]["reasoning_structure"],
                task["domain"],
            )
            for task in self.tasks
        )
        self.assertEqual(len(cells), 40)
        self.assertEqual(set(cells.values()), {4})
        self.assertEqual(
            set(Counter(task["domain"] for task in self.tasks).values()),
            {40},
        )

    def test_public_files_do_not_leak_pair_or_reasoning_metadata(self) -> None:
        forbidden = {
            "reasoning_structure",
            "counterfactual_pair_id",
            "pair_id",
            "scenario_id",
            "variant_role",
            "changed_fact",
            "frontier_profile",
        }
        for path in DATA.glob("*.json"):
            task = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(forbidden.intersection(task), path.name)
            self.assertNotIn("oracle_actions", task)
            self.assertNotIn("candidate_scopes", task)

    def test_private_gold_has_eighty_single_fact_pairs(self) -> None:
        pairs: dict[str, list[dict]] = defaultdict(list)
        for record in self.gold.values():
            pairs[record["metadata"]["pair_id"]].append(record)
        self.assertEqual(len(pairs), 80)
        for pair in pairs.values():
            self.assertEqual(len(pair), 2)
            self.assertEqual(
                pair[0]["intervention"]["logical_fact"],
                pair[1]["intervention"]["logical_fact"],
            )
            self.assertNotEqual(
                pair[0]["intervention"]["value"],
                pair[1]["intervention"]["value"],
            )
            scopes = [
                {
                    tuple(sorted(point["scope"].items()))
                    for point in record["oracle"]["frontier"]
                }
                for record in pair
            ]
            self.assertNotEqual(scopes[0], scopes[1])

    def test_all_failure_boundaries_replay(self) -> None:
        failures = [
            task["task_id"]
            for task in self.tasks
            if not _replay_v1_boundary(task)
        ]
        self.assertEqual(failures, [])

    def test_release_certificates_cover_all_tasks(self) -> None:
        required = {
            "prefix_generated_by_public_tools",
            "failure_generated_by_public_tool",
            "snapshot_hash_verified",
            "dual_oracle_agreement",
            "dominated_terminal_exists",
            "gold_replay_within_15_turns",
            "counterfactual_frontier_changed",
            "single_logical_fact_intervention",
        }
        self.assertEqual(set(self.gold), {task["task_id"] for task in self.tasks})
        for record in self.gold.values():
            certificate = record["validity_certificate"]
            self.assertTrue(all(certificate[key] for key in required))

    def test_each_structure_has_a_recomputed_dual_oracle_witness(self) -> None:
        samples = {}
        for task in self.tasks:
            samples.setdefault(
                task["_benchmark_metadata"]["reasoning_structure"], task
            )
        self.assertEqual(len(samples), 10)
        for task in samples.values():
            oracle = solve_task_v1(task)
            self.assertGreaterEqual(oracle.feasible_scope_count, 3)
            self.assertGreater(
                oracle.feasible_terminal_count, len(oracle.frontier)
            )
            self.assertEqual(
                frontier_signature(oracle.frontier),
                frontier_signature(oracle.independent_frontier),
            )

    def test_active_service_contract_is_charged_by_public_tool(self) -> None:
        task = next(
            task
            for task in self.tasks
            if any(
                contract["trigger"]["type"] == "active_any"
                for contract in task["contracts"]
            )
        )
        contract = next(
            contract
            for contract in task["contracts"]
            if contract["trigger"]["type"] == "active_any"
        )
        option_id = contract["trigger"]["option_ids"][0]
        environment = CommitmentRecoveryEnvironment(task)
        result = environment.execute_tool(
            environment.names["book"],
            {environment.names["option"]: option_id},
        )
        self.assertTrue(result.ok)
        self.assertEqual(
            result.data["contract_charges_applied"],
            [
                {
                    "contract_id": contract["contract_id"],
                    "charge_cents": contract["charge_cents"],
                }
            ],
        )

    def test_thirty_percent_reject_one_step_addition(self) -> None:
        rejected = sum(
            not _single_addition_repair_feasible(task)
            for task in self.tasks
        )
        self.assertGreaterEqual(rejected, 48)

    def test_model_surface_has_no_finish_or_answer_revealing_cost_tool(self) -> None:
        for task in self.tasks:
            names = {
                definition["name"]
                for definition in tool_definitions_for_task(task)
            }
            self.assertNotIn("finish", names)
            self.assertNotIn("get_cost_summary", names)
            self.assertEqual(len(names), 8)

    def test_oracle_actions_are_executable_and_accepted(self) -> None:
        for task in self.tasks[:8]:
            score = evaluate_actions(task, make_actions(task, "pareto_oracle"))
            self.assertTrue(score["goal_pass"])
            self.assertTrue(score["non_dominated_repair"])


if __name__ == "__main__":
    unittest.main()
