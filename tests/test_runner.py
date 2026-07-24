from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from repairscope_bench.loader import load_task
from repairscope_bench.providers.base import ModelTurn, ToolCall
from repairscope_bench.runner import (
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

    def start_session(self, system_prompt, user_prompt):
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return ScriptedSession()


class ScriptedSession:
    def __init__(self):
        self.index = 0

    def advance(self, tool_results=None):
        self.index += 1
        if self.index == 1:
            return ModelTurn(
                "",
                [ToolCall("c1", "list_commitments", {})],
                {"input_tokens": 10, "output_tokens": 2},
            )
        return ModelTurn(
            "",
            [ToolCall("c2", "finish", {})],
            {"input_tokens": 11, "output_tokens": 1},
        )


class RunnerTest(unittest.TestCase):
    def test_runner_executes_tool_loop_and_scores(self) -> None:
        task = load_task(DATA / "short-trip-a-keep-extra-day.json")
        adapter = ScriptedAdapter()
        record = run_episode(task, adapter)
        self.assertEqual(record["status"], "completed")
        self.assertTrue(record["score"]["optimal_repair"])
        self.assertEqual(record["usage"]["input_tokens"], 21)
        self.assertEqual(record["score"]["action_count"], 2)

    def test_model_prompt_excludes_gold_and_evaluator_internals(self) -> None:
        task = load_task(DATA / "short-trip-a-keep-extra-day.json")
        prompt = build_user_prompt(task)
        self.assertNotIn("optimal_plans", prompt)
        self.assertNotIn('"constraints"', prompt)
        self.assertNotIn('"catalog"', prompt)
        self.assertIn("failure_observation", prompt)
        self.assertNotIn("fully refundable", prompt)
        self.assertNotIn("available for", prompt)

    def test_counterfactual_family_does_not_narrate_hidden_solution(self) -> None:
        prompts = [
            build_user_prompt(
                load_task(DATA / f"travel-package-{suffix}.json")
            )
            for suffix in [
                "a-local-car",
                "b-replace-hotel",
                "c-modify-flight",
                "d-infeasible",
            ]
        ]
        for prompt in prompts:
            self.assertIn("inventory_changed", prompt)
            self.assertNotIn("refundable", prompt)
            self.assertNotIn("replacement car", prompt)
            self.assertNotIn("saver change", prompt)

    def test_suite_writes_jsonl_summary_and_refuses_silent_mix(self) -> None:
        task = load_task(DATA / "short-trip-a-keep-extra-day.json")
        with TemporaryDirectory() as directory:
            summary = run_suite([task], ScriptedAdapter(), directory)
            self.assertEqual(summary["run_count"], 1)
            self.assertEqual(summary["goal_pass@1"], 1.0)
            self.assertEqual(summary["goal_pass^k"], 1.0)
            self.assertEqual(summary["goal_pass^1"], 1.0)
            self.assertEqual(summary["optimal_pass@1"], 1.0)
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


if __name__ == "__main__":
    unittest.main()
