# RepairScope-Bench

**An executable diagnostic benchmark for post-commit agent recovery.**

An agent has already booked a flight and hotel when a later car reservation
fails. It may need to keep, modify, or replace different existing commitments:
the failure location alone does not determine the correct repair scope.

RepairScope-Bench evaluates that decision from a standardized failure state.
Every model receives the same instruction, public pre-failure tool trace,
failure observation, and executable tools. It is not a static classifier: the
agent must query and mutate persistent state.

> Status: **research pilot, v0.3.2**. The release contains 16 counterfactual
> tasks in two domains. It establishes the protocol and executable harness; it
> is not yet large enough for a leaderboard claim.

[中文说明](README.zh-CN.md) · [Data card](docs/DATA_CARD.md) ·
[Evaluation protocol](docs/EVALUATION.md) ·
[Provider setup](docs/PROVIDERS.md) · [Research positioning](docs/RESEARCH_STORY.md)

## Research question

> After earlier actions have created persistent commitments and a later action
> fails, can an agent satisfy the goal while preserving useful commitments and
> avoiding objectively measurable extra loss?

The protocol has four defining properties:

1. **Fixed failure boundary.** Every model starts from identical state.
2. **Real post-boundary mutations.** Calls cancel, book, modify, and verify
   records in an executable environment.
3. **No single gold trajectory.** An exhaustive solver accepts every plan tied
   on the declared lexicographic objective.
4. **Counterfactual families.** Small changes to refunds, compatibility,
   deadlines, or availability change the optimal repair scope.
5. **Tool-mediated discovery.** The initial failure message is the raw failed
   call, not a prose diagnosis. Refunds, alternatives, modification quotes,
   compatibility, and current cost must be discovered through targeted tools.

This is a conditional recovery track. It intentionally does not score planning
and execution before the failure boundary; a later end-to-end track can add
those stages.

## Pilot

The pilot uses newly authored counterfactuals inspired by coordination
structures in four STATE-Bench cases.

| Family | Fixed failure boundary | Counterfactual outcomes |
|---|---|---|
| Denver package | flights and hotel confirmed; car fails | book car only; replace hotel; modify flight; infeasible |
| Destination change | SFO flight confirmed; requested hotel sells out | replace old hotel; keep it when allowed; use another SFO hotel; infeasible |
| Shortened trip | final hotel night removed; car date change fails | keep extra rental day; replace car; modify car; infeasible |
| Workstation | laptop and monitor ordered; dock order voided | add dock; replace laptop and dock; use adapter-dock; infeasible |

Public files in `data/pilot` contain no expected answer. Evaluator-only gold is
stored separately in `data/gold/pilot.json` and is recomputed by
`repairscope validate`.

## Objective accounting

The evaluator keeps three auditable ledgers instead of mixing unlike economic
concepts with fitted weights:

- `lifecycle_cost`: all cash ultimately retained by providers across the task;
- `recovery_loss`: unrefunded cancelled value, wasted post-failure purchases,
  and positive net cash paid for in-place modifications;
- `financial_regret`: lifecycle cost minus the cheapest feasible lifecycle cost
  from the identical failure state.

The primary scalar `extra_loss` is the agent's `recovery_loss` minus the
minimum feasible recovery loss. After hard constraints, current tasks minimize:

```text
(recovery_loss,
 lifecycle_cost,
 mutated_prior_commitments,
 state_changing_actions)
```

This is an unweighted lexicographic rule: irreversible loss comes first,
followed by total lifecycle cost; commitment preservation is only a later
tie-breaker. All plans tied on the complete tuple are accepted. The evaluator
also reports scope distance, over-repair,
under-repair, tool errors, and correct infeasibility. An infeasibility report
receives credit only if no successful state-changing action has damaged the
failure-boundary state.

See [docs/EVALUATION.md](docs/EVALUATION.md) for exact definitions.

## Install and validate

```bash
python -m pip install -e .
python scripts/build_pilot.py
repairscope validate data/pilot
python -m unittest discover -s tests -v
repairscope run-baselines data/pilot
```

Expected implementation-check summary:

| Baseline | Success | Optimal |
|---|---:|---:|
| No repair | 2 / 16 | 1 / 16 |
| Repair only the missing slot | 4 / 16 | 3 / 16 |
| Repair declared affected slots | 7 / 16 | 5 / 16 |
| Greedy full rollback | 8 / 16 | 0 / 16 |
| Exhaustive oracle | 16 / 16 | 16 / 16 |

These are regression checks, not language-model results.

## Run GPT, Claude, Qwen, or DeepSeek

The harness implements OpenAI Responses, Anthropic Messages, and
OpenAI-compatible Chat Completions for Qwen and DeepSeek. API keys are read
only from environment variables and are never stored in run logs.

```bash
# GPT
export OPENAI_API_KEY=...
repairscope run-suite data/pilot --provider openai --model gpt-5.6-sol \
  --output-dir results/gpt

# Claude: use a model ID available in your Anthropic account
export ANTHROPIC_API_KEY=...
repairscope run-suite data/pilot --provider anthropic \
  --model YOUR_CLAUDE_MODEL --output-dir results/claude

# Qwen / DashScope
export DASHSCOPE_API_KEY=...
repairscope run-suite data/pilot --provider qwen --model qwen3.7-plus \
  --output-dir results/qwen

# DeepSeek
export DEEPSEEK_API_KEY=...
repairscope run-suite data/pilot --provider deepseek --model deepseek-chat \
  --output-dir results/deepseek

# Any OpenAI-compatible gateway
export OPENAI_COMPATIBLE_API_KEY=...
repairscope run-suite data/pilot --provider openai-compatible \
  --model YOUR_MODEL_ID --base-url https://gateway.example/v1 \
  --output-dir results/gateway-model
```

On PowerShell, replace `export NAME=...` with `$env:NAME="..."`.

A single episode uses:

```bash
repairscope run-model data/pilot/short-trip-a-keep-extra-day.json \
  --provider openai --model gpt-5.6-sol --output run.json
```

Batch execution uses five independent runs per task by default, writes one
auditable record per episode to `runs.jsonl`, and writes an aggregate
`summary.json` containing Goal/Optimal Pass@1 and strict Pass^5. Provider
errors count as failed episodes. Use `--repeats 1` only for a smoke test.
Model IDs are explicit so vendor alias changes cannot silently alter an
experiment.

## Model-visible protocol

The prompt is constructed from an allowlist:

- `instruction`;
- `failure_observation`;
- public `pre_failure_trace`;
- the tool interface.

It excludes evaluator constraints, catalog internals, gold scopes, and oracle
plans. Options and authoritative state must be obtained through tools.

```text
list_commitments()
get_commitment_details(commitment_id)
get_cancellation_quote(commitment_id)
search_options(slot)
get_modification_quote(commitment_id, to_option_id)
check_compatibility(left_option_id, right_option_id)
get_cost_summary()
cancel(commitment_id)
book(option_id)
modify(commitment_id, to_option_id)
finish()
report_infeasible(reason)
```

Every run uses a fresh deep copy. Side-effecting calls are serialized, actions
after termination are rejected, and action/turn budgets are enforced.

The read tools are intentionally separated. `list_commitments` does not expose
refund policies or modification rules, `search_options` returns only currently
available alternatives for the requested slot, and quotes are revealed only
for the requested commitment or target. The evaluator's constraints, oracle,
and loss calculations remain inaccessible to the model.

## Repository layout

```text
data/pilot/                  public task instances
data/gold/pilot.json         evaluator-only solver output
src/repairscope_bench/       environment, solver, evaluator, provider harness
scripts/build_pilot.py       deterministic data and gold generator
tests/                       accounting, safety, protocol, and runner tests
docs/                        data card, protocol, research positioning
```

## Scope and limitations

- 16 tasks are sufficient for protocol debugging, not broad empirical claims.
- The oracle currently enumerates a finite single-commitment-per-slot search
  space.
- Dollar-like deterministic units are used; taxes and time-varying exchange
  rates are out of scope.
- Provider adapters are protocol-tested with deterministic mock responses.
  Live calls require the user's own API keys and selected model access.

## License and attribution

Code and newly authored task data are MIT licensed. Source inspirations and
transformation boundaries are recorded in each task and in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
