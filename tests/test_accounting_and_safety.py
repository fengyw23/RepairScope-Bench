from __future__ import annotations

from copy import deepcopy
import unittest
from pathlib import Path

from repairscope_bench.environment import RepairEnvironment
from repairscope_bench.evaluator import evaluate_actions
from repairscope_bench.loader import load_task
from repairscope_bench.oracle import solve_task


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "pilot"


class AccountingAndSafetyTest(unittest.TestCase):
    def test_modification_uses_full_net_cash_delta(self) -> None:
        task = load_task(DATA / "travel-package-c-modify-flight.json")
        score = evaluate_actions(
            task,
            [
                {
                    "action": "modify",
                    "args": {
                        "commitment_id": "C-FLIGHT-OUT",
                        "to_option_id": "UA-DEN-OUT-SAVER",
                    },
                },
                {"action": "book", "args": {"option_id": "CAR-DEN-ALT"}},
                {"action": "finish", "args": {}},
            ],
        )
        self.assertEqual(score["financial_delta"], 130)
        self.assertEqual(score["lifecycle_cost"], 899)
        self.assertEqual(score["recovery_loss"], 0)
        self.assertTrue(score["optimal_repair"])

    def test_positive_modification_cash_is_recovery_loss(self) -> None:
        task = load_task(DATA / "short-trip-c-modify-car.json")
        score = evaluate_actions(
            task,
            [
                {
                    "action": "modify",
                    "args": {
                        "commitment_id": "C-CAR-LONG",
                        "to_option_id": "CAR-SEA-SHORT",
                    },
                },
                {"action": "finish", "args": {}},
            ],
        )
        self.assertEqual(score["financial_delta"], 30)
        self.assertEqual(score["recovery_loss"], 30)
        self.assertEqual(score["extra_loss"], 0)
        self.assertTrue(score["optimal_repair"])

    def test_infeasible_report_cannot_hide_successful_mutation(self) -> None:
        task = load_task(DATA / "travel-package-d-infeasible.json")
        score = evaluate_actions(
            task,
            [
                {"action": "book", "args": {"option_id": "CAR-DEN-ALT"}},
                {
                    "action": "report_infeasible",
                    "args": {"reason": "No valid full repair."},
                },
            ],
        )
        self.assertFalse(score["success"])
        self.assertNotEqual(score["financial_delta"], 0)

    def test_actions_after_terminal_are_rejected(self) -> None:
        task = load_task(DATA / "short-trip-a-keep-extra-day.json")
        environment = RepairEnvironment(task)
        self.assertTrue(environment.finish().ok)
        result = environment.execute(
            {"action": "cancel", "args": {"commitment_id": "C-CAR-LONG"}}
        )
        self.assertFalse(result.ok)
        self.assertTrue(environment.state_matches_failure_boundary())

    def test_state_query_exposes_policies_without_internal_fields(self) -> None:
        task = load_task(DATA / "travel-package-c-modify-flight.json")
        environment = RepairEnvironment(task)
        data = environment.query_state().data
        assert isinstance(data, dict)
        self.assertTrue(data["available_modifications"])
        self.assertEqual(
            data["available_modifications"][0]["net_cash_delta"], -80
        )
        self.assertTrue(
            all(
                not key.startswith("_")
                for item in data["commitments"]
                for key in item
            )
        )

    def test_full_lexicographic_objective_is_checked(self) -> None:
        task = load_task(DATA / "destination-hotel-b.json")
        score = evaluate_actions(
            task,
            [
                {
                    "action": "cancel",
                    "args": {"commitment_id": "C-HOTEL-LAX"},
                },
                {"action": "book", "args": {"option_id": "HOTEL-OAK-ALT"}},
                {"action": "finish", "args": {}},
            ],
        )
        self.assertTrue(score["success"])
        self.assertEqual(score["extra_loss"], 0)
        self.assertFalse(score["optimal_repair"])
        self.assertEqual(score["over_repair"], ["C-HOTEL-LAX"])

    def test_extra_loss_is_oracle_relative_and_nonnegative(self) -> None:
        task = load_task(DATA / "destination-hotel-b.json")
        score = evaluate_actions(
            task,
            [
                {
                    "action": "cancel",
                    "args": {"commitment_id": "C-FLIGHT-SFO"},
                },
                {"action": "book", "args": {"option_id": "UA183SFO"}},
                {"action": "finish", "args": {}},
            ],
        )
        self.assertTrue(score["success"])
        self.assertEqual(score["cancellation_loss"], 100)
        self.assertEqual(score["optimal_recovery_loss"], 0)
        self.assertEqual(score["extra_loss"], 100)

    def test_action_budget_cannot_be_bypassed_with_late_finish(self) -> None:
        task = load_task(DATA / "short-trip-a-keep-extra-day.json")
        actions = [{"action": "query_state", "args": {}}] * task["max_actions"]
        actions.append({"action": "finish", "args": {}})
        score = evaluate_actions(task, actions)
        self.assertTrue(score["action_budget_exceeded"])
        self.assertFalse(score["success"])

    def test_same_modification_cannot_be_applied_twice(self) -> None:
        task = load_task(DATA / "short-trip-c-modify-car.json")
        environment = RepairEnvironment(task)
        action = {
            "action": "modify",
            "args": {
                "commitment_id": "C-CAR-LONG",
                "to_option_id": "CAR-SEA-SHORT",
            },
        }
        self.assertTrue(environment.execute(action).ok)
        self.assertFalse(environment.execute(action).ok)
        self.assertEqual(environment.modification_net_cash, 30)

    def test_oracle_treats_modification_availability_separately(self) -> None:
        task = deepcopy(
            load_task(DATA / "short-trip-c-modify-car.json")
        )
        for option in task["catalog"]:
            if option["option_id"] == "CAR-SEA-SHORT":
                option["available"] = False
        oracle = solve_task(task)
        self.assertTrue(oracle.feasible)
        self.assertEqual(
            oracle.optimal_scopes[0]["C-CAR-LONG"], "MODIFY"
        )


if __name__ == "__main__":
    unittest.main()
