from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from repairscope_bench.domain_tools import tool_definitions_for_task
from repairscope_bench.loader import load_tasks
from repairscope_bench.runner import summarize_runs
from repairscope_bench.validation import validate_dataset
from repairscope_bench.v3_environment import NativeRecoveryEnvironmentV3
from repairscope_bench.v3_evaluator import evaluate_v3_environment
from repairscope_bench.v3_oracle import scope_key, solve_task_v3


ROOT = Path(__file__).resolve().parents[1]


class V3ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tasks = load_tasks(ROOT / "data" / "v3")
        cls.gold = json.loads(
            (ROOT / "data" / "gold" / "v3.json").read_text(
                encoding="utf-8"
            )
        )

    def test_release_shape_and_balance(self) -> None:
        self.assertEqual(len(self.tasks), 80)
        self.assertEqual(len(self.gold), 80)
        self.assertEqual(
            sum(task["domain"] == "travel" for task in self.tasks), 40
        )
        self.assertEqual(
            sum(task["domain"] == "after_sales" for task in self.tasks), 40
        )
        self.assertEqual(
            sum(task["split"] == "dev" for task in self.tasks), 40
        )
        self.assertEqual(
            sum(task["split"] == "test" for task in self.tasks), 40
        )
        structures = [
            self.gold[task["task_id"]]["metadata"]["reasoning_structure"]
            for task in self.tasks
        ]
        self.assertEqual(len(set(structures)), 10)
        for structure in set(structures):
            self.assertEqual(structures.count(structure), 8)

    def test_every_task_uses_a_native_state_runtime(self) -> None:
        observed = {
            NativeRecoveryEnvironmentV3(task).native_runtime_name()
            for task in self.tasks
        }
        self.assertEqual(
            observed,
            {
                "state_bench.domains.travel.TravelEnvironment",
                "state_bench.domains.customer_support.CustomerSupportEnvironment",
            },
        )

    def test_domains_have_distinct_public_tool_surfaces(self) -> None:
        travel = next(
            task for task in self.tasks if task["domain"] == "travel"
        )
        support = next(
            task for task in self.tasks if task["domain"] == "after_sales"
        )
        travel_names = {
            item["name"] for item in tool_definitions_for_task(travel)
        }
        support_names = {
            item["name"] for item in tool_definitions_for_task(support)
        }
        self.assertEqual(len(travel_names), 8)
        self.assertEqual(len(support_names), 8)
        self.assertFalse(travel_names & support_names)

    def test_all_gold_scopes_are_unique_material_and_replayable(self) -> None:
        for task in self.tasks:
            oracle = solve_task_v3(task)
            self.assertTrue(oracle.feasible)
            self.assertTrue(oracle.unique)
            self.assertIsNotNone(oracle.gold)
            self.assertGreaterEqual(oracle.feasible_scope_count, 3)
            self.assertGreaterEqual(
                oracle.cost_margin_minor, oracle.required_margin_minor
            )
            environment = NativeRecoveryEnvironmentV3(task)
            for call in oracle.gold["tool_calls"]:
                result = environment.execute_tool(
                    call["name"], deepcopy(call["arguments"])
                )
                self.assertTrue(result.ok, (task["task_id"], call, result))
            score = evaluate_v3_environment(task, environment)
            self.assertTrue(score["goal_pass"])
            self.assertTrue(score["unique_scope_pass"])
            self.assertTrue(score["clean_execution"])
            self.assertEqual(score["cost_regret_minor"], 0)

    def test_counterfactual_pairs_change_one_fact_and_flip_gold(self) -> None:
        pairs: dict[str, list[dict]] = {}
        for task in self.tasks:
            metadata = self.gold[task["task_id"]]["metadata"]
            pairs.setdefault(metadata["pair_id"], []).append(task)
        self.assertEqual(len(pairs), 40)
        for pair_id, members in pairs.items():
            self.assertEqual(len(members), 2, pair_id)
            left, right = sorted(
                members,
                key=lambda task: self.gold[task["task_id"]]["metadata"][
                    "variant_role"
                ],
            )
            self.assertEqual(
                left["failure_snapshot"], right["failure_snapshot"], pair_id
            )
            self.assertEqual(left["instruction"], right["instruction"], pair_id)
            left_gold = solve_task_v3(left).gold["scope_signature"]
            right_gold = solve_task_v3(right).gold["scope_signature"]
            self.assertNotEqual(scope_key(left_gold), scope_key(right_gold))

    def test_every_hard_constraint_has_visible_evidence(self) -> None:
        for task in self.tasks:
            metadata = self.gold[task["task_id"]]["metadata"]
            evidence_by_id = {
                item["evidence_id"]: item
                for item in metadata["evidence_manifest"]
            }
            for constraint in (
                task["hard_goals"]["capabilities"]
                + task["hard_goals"]["attributes"]
                + task["compatibility_rules"]
            ):
                refs = constraint.get("evidence_refs", [])
                self.assertTrue(refs, (task["task_id"], constraint))
                self.assertTrue(set(refs).issubset(evidence_by_id))
                for evidence_id in refs:
                    self.assertNotEqual(
                        evidence_by_id[evidence_id]["source_type"],
                        "tool_rule",
                        (task["task_id"], constraint),
                    )

    def test_relationship_rules_are_structured_public_results(self) -> None:
        observed_types = set()
        for task in self.tasks:
            environment = NativeRecoveryEnvironmentV3(task)
            terms_tool = (
                "get_travel_terms"
                if task["domain"] == "travel"
                else "get_product_terms"
            )
            compatibility_tool = (
                "check_travel_compatibility"
                if task["domain"] == "travel"
                else "check_product_compatibility"
            )
            for rule in task["compatibility_rules"]:
                observed_types.add(rule["type"])
                if rule["type"] == "forbid_pair":
                    left_key = (
                        "left_option_id"
                        if task["domain"] == "travel"
                        else "left_product_id"
                    )
                    right_key = (
                        "right_option_id"
                        if task["domain"] == "travel"
                        else "right_product_id"
                    )
                    result = environment.execute_tool(
                        compatibility_tool,
                        {
                            left_key: rule["option_ids"][0],
                            right_key: rule["option_ids"][1],
                        },
                    )
                    self.assertTrue(result.ok)
                    self.assertFalse(result.data["coexistence_allowed"])
                else:
                    result = environment.execute_tool(
                        terms_tool, {"record_id": rule["if_option_id"]}
                    )
                    self.assertTrue(result.ok)
                public = next(
                    (
                        item
                        for item in result.data["relationship_rules"]
                        if item["constraint_id"] == rule["constraint_id"]
                    ),
                    None,
                )
                self.assertIsNotNone(public, (task["task_id"], rule))
                self.assertEqual(public["type"], rule["type"])
                if rule["type"] == "requires_any":
                    self.assertEqual(
                        public["if_option_id"], rule["if_option_id"]
                    )
                    self.assertEqual(
                        public["any_option_ids"],
                        sorted(rule["any_option_ids"]),
                    )
        self.assertEqual(observed_types, {"forbid_pair", "requires_any"})

    def test_equivalent_term_query_counts_as_fact_acquisition(self) -> None:
        task = next(
            task
            for task in self.tasks
            if self.gold[task["task_id"]]["metadata"][
                "reasoning_structure"
            ]
            == "bridge_vs_replacement"
            and len(
                self.gold[task["task_id"]]["metadata"]["changed_fact"][
                    "reveal_paths"
                ]
            )
            > 1
        )
        changed = self.gold[task["task_id"]]["metadata"]["changed_fact"]
        alternate = next(
            path
            for path in changed["reveal_paths"]
            if path["arguments"]["record_id"] != changed["record_id"]
        )
        environment = NativeRecoveryEnvironmentV3(task)
        self.assertTrue(
            environment.execute_tool(
                alternate["tool"], deepcopy(alternate["arguments"])
            ).ok
        )
        score = evaluate_v3_environment(task, environment)
        self.assertTrue(
            score["changed_fact_acquisition"][
                "queried_before_first_mutation"
            ]
        )
        self.assertEqual(
            score["changed_fact_acquisition"]["observed_record_id"],
            alternate["arguments"]["record_id"],
        )

    def test_missing_added_companion_is_under_repair(self) -> None:
        task = next(
            task
            for task in self.tasks
            if self.gold[task["task_id"]]["metadata"][
                "reasoning_structure"
            ]
            == "bridge_vs_replacement"
            and self.gold[task["task_id"]]["metadata"]["variant_role"]
            == "left"
        )
        rule = next(
            rule
            for rule in task["compatibility_rules"]
            if rule["type"] == "requires_any"
        )
        environment = NativeRecoveryEnvironmentV3(task)
        tool = (
            "book_travel_option"
            if task["domain"] == "travel"
            else "purchase_product_option"
        )
        actor_key = (
            "user_id" if task["domain"] == "travel" else "customer_id"
        )
        option_key = (
            "option_id" if task["domain"] == "travel" else "product_id"
        )
        self.assertTrue(
            environment.execute_tool(
                tool,
                {
                    option_key: rule["if_option_id"],
                    actor_key: task["actor_id"],
                },
            ).ok
        )
        score = evaluate_v3_environment(task, environment)
        self.assertFalse(score["goal_pass"])
        for required in rule["any_option_ids"]:
            self.assertIn(
                f"added_option:{required}", score["under_repair"]
            )

    def test_correct_scope_can_still_have_execution_waste(self) -> None:
        selected = None
        for task in self.tasks:
            oracle = solve_task_v3(task)
            gold_added = set(
                oracle.gold["scope_signature"]["added_option_ids"]
            )
            if len(gold_added) != 1:
                continue
            gold_option = next(iter(gold_added))
            waste_option = next(
                (
                    option_id
                    for option_id, metadata in task[
                        "option_metadata"
                    ].items()
                    if metadata.get("candidate", False)
                    and metadata.get("available", False)
                    and option_id not in gold_added
                    and metadata["slot"]
                    == task["option_metadata"][gold_option]["slot"]
                ),
                None,
            )
            if waste_option is not None:
                selected = task, oracle, waste_option
                break
        self.assertIsNotNone(selected)
        task, oracle, waste_option = selected
        environment = NativeRecoveryEnvironmentV3(task)
        if task["domain"] == "travel":
            self.assertTrue(
                environment.execute_tool(
                    "book_travel_option",
                    {
                        "option_id": waste_option,
                        "user_id": task["actor_id"],
                    },
                ).ok
            )
            entity_id = next(
                item["entity_id"]
                for item in environment.active_records()
                if item["option_id"] == waste_option
            )
            self.assertTrue(
                environment.execute_tool(
                    "get_travel_terms", {"record_id": entity_id}
                ).ok
            )
            self.assertTrue(
                environment.execute_tool(
                    "preview_travel_cancellation",
                    {"reservation_id": entity_id},
                ).ok
            )
            self.assertTrue(
                environment.execute_tool(
                    "cancel_travel_reservation",
                    {"reservation_id": entity_id, "confirm": True},
                ).ok
            )
        else:
            self.assertTrue(
                environment.execute_tool(
                    "purchase_product_option",
                    {
                        "product_id": waste_option,
                        "customer_id": task["actor_id"],
                    },
                ).ok
            )
            entity_id = next(
                item["entity_id"]
                for item in environment.active_records()
                if item["option_id"] == waste_option
            )
            self.assertTrue(
                environment.execute_tool(
                    "get_product_terms", {"record_id": entity_id}
                ).ok
            )
            self.assertTrue(
                environment.execute_tool(
                    "preview_product_return", {"item_id": entity_id}
                ).ok
            )
            self.assertTrue(
                environment.execute_tool(
                    "return_product",
                    {"item_id": entity_id, "confirm": True},
                ).ok
            )
        for call in oracle.gold["tool_calls"]:
            self.assertTrue(
                environment.execute_tool(
                    call["name"], deepcopy(call["arguments"])
                ).ok
            )
        score = evaluate_v3_environment(task, environment)
        self.assertTrue(score["goal_pass"])
        self.assertTrue(score["unique_scope_pass"])
        self.assertFalse(score["clean_execution"])
        self.assertGreater(score["execution_waste_minor"], 0)

    def test_contract_settlement_is_charged_once(self) -> None:
        selected = next(
            (
                (task, solve_task_v3(task))
                for task in self.tasks
                if any(
                    event["category"] == "contract_settlement"
                    for event in solve_task_v3(task).gold[
                        "economic_events"
                    ]
                )
            ),
            None,
        )
        self.assertIsNotNone(selected)
        task, oracle = selected
        environment = NativeRecoveryEnvironmentV3(task)
        for call in oracle.gold["tool_calls"]:
            self.assertTrue(
                environment.execute_tool(
                    call["name"], deepcopy(call["arguments"])
                ).ok
            )
        before = environment.incremental_recovery_cost_minor
        contract_events_before = sum(
            item["category"] == "contract_settlement"
            for item in environment.economic_events()
        )
        query_tool = (
            "list_trip_reservations"
            if task["domain"] == "travel"
            else "list_customer_orders"
        )
        query_args = (
            {"user_id": task["actor_id"]}
            if task["domain"] == "travel"
            else {"customer_id": task["actor_id"]}
        )
        self.assertTrue(environment.execute_tool(query_tool, query_args).ok)
        self.assertEqual(environment.incremental_recovery_cost_minor, before)
        self.assertEqual(
            sum(
                item["category"] == "contract_settlement"
                for item in environment.economic_events()
            ),
            contract_events_before,
        )

    def test_model_visible_money_uses_usd_strings(self) -> None:
        for domain in ("travel", "after_sales"):
            task = next(
                task for task in self.tasks if task["domain"] == domain
            )
            category = next(
                metadata["slot"]
                for metadata in task["option_metadata"].values()
                if metadata.get("candidate", False)
            )
            environment = NativeRecoveryEnvironmentV3(task)
            result = environment.execute_tool(
                "search_travel_options"
                if domain == "travel"
                else "search_product_options",
                {"category": category},
            )
            self.assertTrue(result.ok)
            first = result.data["results"][0]
            for key in [
                "upfront_price",
                "monthly_price",
                "total_charge",
            ]:
                self.assertEqual(first[key]["currency"], "USD")
                self.assertRegex(first[key]["amount"], r"^-?\d+\.\d{2}$")

    def test_release_validator_and_weak_baseline_gates(self) -> None:
        report = validate_dataset(ROOT / "data" / "v3")
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["validated_evidence_count"], 624)
        self.assertEqual(report["evidence_reference_count"], 624)
        self.assertEqual(
            report["observable_state_atom_count"],
            report["observable_state_atom_total"],
        )
        for strategy in [
            "local_repair",
            "dependency_repair",
            "full_rollback",
            "sticker_price",
            "max_refund",
            "min_changes",
        ]:
            self.assertLess(
                report["baselines"][strategy]["scope_rate"], 0.65
            )

    def test_summary_reports_unique_scope_and_pair_success(self) -> None:
        records = []
        for task_id, variant in [("left", "left"), ("right", "right")]:
            records.append(
                {
                    "task_id": task_id,
                    "pair_id": "pair",
                    "repeat_index": 1,
                    "reasoning_structure": "threshold",
                    "score": {
                        "success": True,
                        "goal_pass": True,
                        "unique_scope_pass": True,
                        "scope_non_dominated_pass": True,
                        "clean_execution": variant == "left",
                        "optimal_repair": variant == "left",
                        "scope_signature": {"variant": variant},
                        "cost_regret_minor": 0
                        if variant == "left"
                        else 1000,
                        "execution_waste_minor": 0
                        if variant == "left"
                        else 1000,
                    },
                }
            )
        summary = summarize_runs(records, expected_repeats=1)
        self.assertEqual(summary["goal_pass@1"], 1.0)
        self.assertEqual(summary["unique_scope_pass@1"], 1.0)
        self.assertEqual(summary["clean_execution@1"], 0.5)
        self.assertEqual(summary["counterfactual_pair_success@1"], 1.0)
        self.assertEqual(summary["adaptive_scope_switch@1"], 1.0)
        self.assertEqual(summary["mean_execution_waste_minor"], 500)


if __name__ == "__main__":
    unittest.main()
