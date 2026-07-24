from __future__ import annotations

from copy import deepcopy
import unittest
from pathlib import Path

from repairscope_bench.environment import RepairEnvironment
from repairscope_bench.domain_tools import DomainToolRouter, tool_definitions_for_task
from repairscope_bench.evaluator import evaluate_actions
from repairscope_bench.loader import load_task
from repairscope_bench.oracle import solve_task


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "legacy" / "v0.5" / "pilot"


class AccountingAndSafetyTest(unittest.TestCase):
    def test_modification_uses_full_net_cash_delta(self) -> None:
        task = load_task(DATA / "short-trip-a-modify-car.json")
        score = evaluate_actions(
            task,
            [
                {
                    "action": "modify",
                    "args": {
                        "commitment_id": "CR-184",
                        "to_option_id": "CAR-SEA-SHORT",
                    },
                },
                {"action": "finish", "args": {}},
            ],
        )
        self.assertEqual(score["financial_delta"], 30)
        self.assertEqual(score["lifecycle_cost"], 1120)
        self.assertEqual(score["recovery_loss"], 30)
        self.assertTrue(score["optimal_repair"])

    def test_positive_modification_cash_is_recovery_loss(self) -> None:
        task = load_task(DATA / "short-trip-a-modify-car.json")
        score = evaluate_actions(
            task,
            [
                {
                    "action": "modify",
                    "args": {
                        "commitment_id": "CR-184",
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
        task = load_task(DATA / "short-trip-c-keep-extra-day.json")
        environment = RepairEnvironment(task)
        self.assertTrue(environment.finish().ok)
        result = environment.execute(
            {"action": "cancel", "args": {"commitment_id": "CR-184"}}
        )
        self.assertFalse(result.ok)
        self.assertTrue(environment.state_matches_failure_boundary())

    def test_policies_require_targeted_queries(self) -> None:
        task = load_task(DATA / "short-trip-a-modify-car.json")
        environment = RepairEnvironment(task)
        router = DomainToolRouter(environment)
        quote = router.execute(
            "get_change_quote",
            {"reservation_id": "CR-184", "to_option_id": "CAR-SEA-SHORT"},
        )
        assert isinstance(quote.data, dict)
        self.assertTrue(quote.data["available"])
        self.assertEqual(quote.data["net_cash_delta"], 30)
        cancellation = router.execute(
            "preview_cancellation", {"reservation_id": "CR-184"}
        )
        assert isinstance(cancellation.data, dict)
        self.assertNotIn("irrecoverable_loss", cancellation.data)
        self.assertNotIn(
            "get_cost_summary",
            {item["name"] for item in tool_definitions_for_task(task)},
        )

    def test_search_hides_unavailable_options(self) -> None:
        task = load_task(DATA / "workstation-b.json")
        environment = RepairEnvironment(task)
        options = environment.search_options("dock").data
        assert isinstance(options, list)
        option_ids = {item["option_id"] for item in options}
        self.assertIn("PROBOOK-DOCK-V2", option_ids)
        self.assertIn("LEGACY-USB-A-DOCK", option_ids)
        self.assertIn("PROBOOK-DOCK-LATE", option_ids)
        self.assertNotIn("PROBOOK-DOCK-SOLD-OUT", option_ids)

    def test_compatibility_must_be_checked_for_specific_options(self) -> None:
        task = load_task(DATA / "workstation-b.json")
        environment = RepairEnvironment(task)
        incompatible = environment.check_compatibility(
            "CREATORBOOK-15", "PROBOOK-DOCK-V2"
        )
        compatible = environment.check_compatibility(
            "PROBOOK-14", "PROBOOK-DOCK-V2"
        )
        assert isinstance(incompatible.data, dict)
        assert isinstance(compatible.data, dict)
        self.assertFalse(incompatible.data["compatible"])
        self.assertTrue(compatible.data["compatible"])

    def test_full_refund_replacement_beats_costly_change(self) -> None:
        task = load_task(DATA / "destination-hotel-b.json")
        score = evaluate_actions(
            task,
            [
                {
                    "action": "cancel",
                    "args": {"commitment_id": "HR-183"},
                },
                {"action": "book", "args": {"option_id": "HOTEL-OAK-ALT"}},
                {"action": "finish", "args": {}},
            ],
        )
        self.assertTrue(score["success"])
        self.assertEqual(score["extra_loss"], 0)
        self.assertTrue(score["optimal_repair"])
        self.assertEqual(score["financial_regret"], 0)
        self.assertEqual(score["over_repair"], [])

    def test_extra_loss_is_oracle_relative_and_nonnegative(self) -> None:
        task = load_task(DATA / "destination-hotel-a.json")
        score = evaluate_actions(
            task,
            [
                {
                    "action": "cancel",
                    "args": {"commitment_id": "HR-183"},
                },
                {"action": "book", "args": {"option_id": "HOTEL-OAK-ALT"}},
                {"action": "finish", "args": {}},
            ],
        )
        self.assertTrue(score["success"])
        self.assertEqual(score["cancellation_loss"], 300)
        self.assertEqual(score["optimal_recovery_loss"], 0)
        self.assertEqual(score["extra_loss"], 300)

    def test_read_calls_do_not_block_late_finish(self) -> None:
        task = load_task(DATA / "short-trip-c-keep-extra-day.json")
        actions = [
            {"action": "list_commitments", "args": {}}
        ] * task["max_actions"]
        actions.append({"action": "finish", "args": {}})
        score = evaluate_actions(task, actions)
        self.assertFalse(score["action_budget_exceeded"])
        self.assertTrue(score["success"])

    def test_same_modification_cannot_be_applied_twice(self) -> None:
        task = load_task(DATA / "short-trip-a-modify-car.json")
        environment = RepairEnvironment(task)
        action = {
            "action": "modify",
            "args": {
                "commitment_id": "CR-184",
                "to_option_id": "CAR-SEA-SHORT",
            },
        }
        self.assertTrue(environment.execute(action).ok)
        self.assertFalse(environment.execute(action).ok)
        self.assertEqual(environment.modification_net_cash, 30)

    def test_oracle_treats_modification_availability_separately(self) -> None:
        task = deepcopy(
            load_task(DATA / "short-trip-a-modify-car.json")
        )
        for option in task["catalog"]:
            if option["option_id"] == "CAR-SEA-SHORT":
                option["available"] = False
        oracle = solve_task(task)
        self.assertTrue(oracle.feasible)
        self.assertEqual(
            oracle.optimal_scopes[0]["CR-184"], "MODIFY"
        )


if __name__ == "__main__":
    unittest.main()
