from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from repairscope_bench.loader import load_task
from repairscope_bench.providers.base import ModelTurn, ToolCall
from repairscope_bench.runner import (
    SYSTEM_PROMPTS,
    build_user_prompt,
    run_episode,
    run_suite,
    summarize_runs,
)


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "pilot"


class ScriptedAdapter:
    provider = "fake"
    model = "scripted"

    def start_session(self, system_prompt, user_prompt, tool_definitions=None):
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.tool_definitions = tool_definitions
        return ScriptedSession()


class ScriptedSession:
    def __init__(self):
        self.index = 0

    def advance(self, tool_results=None):
        self.index += 1
        if self.index == 1:
            return ModelTurn(
                "",
                [ToolCall("c1", "get_user_reservations", {})],
                {"input_tokens": 10, "output_tokens": 2},
            )
        return ModelTurn(
            "",
            [ToolCall("c2", "finish", {})],
            {"input_tokens": 11, "output_tokens": 1},
        )


class RunnerTest(unittest.TestCase):
    def test_runner_executes_tool_loop_and_scores(self) -> None:
        task = load_task(DATA / "short-trip-c-keep-extra-day.json")
        adapter = ScriptedAdapter()
        record = run_episode(task, adapter)
        self.assertEqual(record["status"], "completed")
        self.assertTrue(record["score"]["optimal_repair"])
        self.assertEqual(record["usage"]["input_tokens"], 21)
        self.assertEqual(record["score"]["action_count"], 2)
        tool_names = {item["name"] for item in adapter.tool_definitions}
        self.assertIn("get_user_reservations", tool_names)
        self.assertIn("preview_cancellation", tool_names)
        self.assertNotIn("get_cost_summary", tool_names)
        self.assertNotIn("list_commitments", tool_names)
        self.assertEqual(record["harness_config"]["max_turns"], 15)

    def test_model_prompt_excludes_gold_and_evaluator_internals(self) -> None:
        task = load_task(DATA / "short-trip-c-keep-extra-day.json")
        prompt = build_user_prompt(task)
        travel_system = " ".join(SYSTEM_PROMPTS["travel"].lower().split())
        shopping_system = " ".join(SYSTEM_PROMPTS["shopping"].lower().split())
        self.assertNotIn("optimal_plans", prompt)
        self.assertNotIn('"constraints"', prompt)
        self.assertNotIn('"catalog"', prompt)
        self.assertIn("latest_tool_result", prompt)
        self.assertNotIn(
            "minimize additional irreversible",
            travel_system,
        )
        self.assertNotIn("lexicographic", travel_system)
        self.assertIn(
            "do not ask the customer to choose",
            travel_system,
        )
        self.assertIn("then call finish", travel_system)
        self.assertIn("call report_infeasible", shopping_system)
        self.assertNotIn("fully refundable", prompt)
        self.assertNotIn("available for", prompt)

    def test_counterfactual_family_does_not_narrate_hidden_solution(self) -> None:
        prompts = [
            build_user_prompt(
                load_task(DATA / f"travel-package-{suffix}.json")
            )
            for suffix in [
                "a-keep-commitments",
                "b-replace-hotel",
                "c-replace-flight",
                "d-infeasible",
            ]
        ]
        for prompt in prompts:
            self.assertIn("inventory changed", prompt)
            self.assertNotIn("refundable", prompt)
            self.assertNotIn("replacement car", prompt)
            self.assertNotIn("saver change", prompt)

    def test_suite_writes_jsonl_summary_and_refuses_silent_mix(self) -> None:
        task = load_task(DATA / "short-trip-c-keep-extra-day.json")
        with TemporaryDirectory() as directory:
            summary = run_suite([task], ScriptedAdapter(), directory)
            self.assertEqual(summary["run_count"], 1)
            self.assertEqual(summary["goal_pass@1"], 1.0)
            self.assertEqual(summary["goal_pass^k"], 1.0)
            self.assertEqual(summary["goal_pass^1"], 1.0)
            self.assertEqual(summary["optimal_pass@1"], 1.0)
            self.assertEqual(summary["scope_optimization_gap@1"], 0.0)
            self.assertEqual(summary["optimal_pass^k"], 1.0)
            self.assertEqual(summary["optimal_pass^1"], 1.0)
            self.assertTrue((Path(directory) / "runs.jsonl").exists())
            self.assertTrue((Path(directory) / "summary.json").exists())
            with self.assertRaises(FileExistsError):
                run_suite([task], ScriptedAdapter(), directory)

    def test_strict_rates_count_provider_errors_as_failures(self) -> None:
        records = [
            {
                "task_id": "a",
                "provider": "fake",
                "model": "scripted",
                "score": {"success": True, "optimal_repair": True},
            },
            {
                "task_id": "a",
                "provider": "fake",
                "model": "scripted",
                "status": "provider_error",
            },
            {
                "task_id": "b",
                "provider": "fake",
                "model": "scripted",
                "score": {"success": True, "optimal_repair": False},
            },
            {
                "task_id": "b",
                "provider": "fake",
                "model": "scripted",
                "score": {"success": True, "optimal_repair": True},
            },
        ]
        summary = summarize_runs(records, expected_repeats=2)
        self.assertEqual(summary["goal_pass@1"], 0.75)
        self.assertEqual(summary["goal_pass^k"], 0.5)
        self.assertEqual(summary["optimal_pass@1"], 0.5)
        self.assertEqual(summary["optimal_pass^k"], 0.0)
        self.assertEqual(summary["scope_optimization_gap@1"], 0.25)


if __name__ == "__main__":
    unittest.main()
