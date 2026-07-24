from __future__ import annotations

import unittest
from pathlib import Path

from repairscope_bench.baselines import make_actions
from repairscope_bench.evaluator import evaluate_actions
from repairscope_bench.loader import load_tasks
from repairscope_bench.validation import validate_dataset


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "pilot"


class PilotDatasetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tasks = load_tasks(DATA)

    def test_dataset_shape(self) -> None:
        self.assertEqual(len(self.tasks), 16)
        self.assertEqual(len({task["family_id"] for task in self.tasks}), 4)
        self.assertEqual(
            {task["domain"] for task in self.tasks}, {"travel", "shopping"}
        )

    def test_all_declared_gold_is_executable(self) -> None:
        report = validate_dataset(DATA)
        self.assertTrue(report["valid"], report["errors"])

    def test_oracle_baseline_passes_every_task(self) -> None:
        for task in self.tasks:
            with self.subTest(task=task["task_id"]):
                score = evaluate_actions(task, make_actions(task, "oracle"))
                self.assertTrue(score["success"])
                self.assertTrue(score["optimal_repair"])

    def test_infeasible_tasks_require_preservation(self) -> None:
        infeasible = [
            task for task in self.tasks if not task["expected_oracle"]["feasible"]
        ]
        self.assertEqual(len(infeasible), 4)
        for task in infeasible:
            first = task["failure_snapshot"]["commitments"][0]["commitment_id"]
            actions = [
                {"action": "cancel", "args": {"commitment_id": first}},
                {
                    "action": "report_infeasible",
                    "args": {"reason": "No feasible repair."},
                },
            ]
            score = evaluate_actions(task, actions)
            self.assertFalse(score["success"])
            self.assertTrue(score["over_repair"])

    def test_counterfactuals_change_the_scope(self) -> None:
        by_family: dict[str, set[tuple[tuple[str, str], ...]]] = {}
        for task in self.tasks:
            by_family.setdefault(task["family_id"], set()).add(
                tuple(sorted(task["expected_oracle"]["scope"].items()))
            )
        self.assertTrue(all(len(scopes) >= 2 for scopes in by_family.values()))

    def test_fixed_snapshot_isolation(self) -> None:
        task = self.tasks[0]
        first = task["failure_snapshot"]["commitments"][0]["commitment_id"]
        evaluate_actions(
            task,
            [
                {"action": "cancel", "args": {"commitment_id": first}},
                {"action": "finish", "args": {}},
            ],
        )
        fresh_score = evaluate_actions(task, make_actions(task, "oracle"))
        self.assertTrue(fresh_score["optimal_repair"])


if __name__ == "__main__":
    unittest.main()
