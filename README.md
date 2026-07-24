# RepairScope-Bench

**Can an agent repair a partially executed task without destroying useful
commitments or paying avoidable recovery costs?**

An agent has already booked flights, a hotel, a transfer, and a conference
pass when a dinner reservation fails. Completing the task is not enough: a
full rollback can still reach a valid final state while forfeiting refunds and
package credits. RepairScope-Bench evaluates whether the agent explores the
current environment, executes a valid repair, and selects the
minimum-additional-loss repair scope.

> Status: **v0.5.1 research challenge set**. The repository contains the
> original 16-task protocol pilot and a new 12-task paired challenge set.
> This remains a research artifact, not a leaderboard-scale dataset.

[中文说明](README.zh-CN.md) · [Data card](docs/DATA_CARD.md) ·
[Evaluation protocol](docs/EVALUATION.md) ·
[Research positioning](docs/RESEARCH_STORY.md)

## What v0.5 changes

- **Larger repair graphs:** each challenge task has 486–729 raw candidate
  repairs, 18–235 feasible repairs, 4–30 feasible scope patterns, and 4–30
  objectively distinct recovery-loss levels.
- **Paired objective demand:** every failure state appears once as a
  feasibility-only request and once with a natural request to avoid waste.
- **Non-local loss:** cancelling or changing one record can forfeit a package
  credit, product rebate, license, or service term attached to another record.
- **Distributed discovery:** the model must separately inspect records,
  category-filtered live inventory, refund/exchange quotes, compatibility, and
  linked settlement terms. Search never depends on a hidden exact-match phrase.
- **Mechanism splits:** package breakage is development data, compatibility
  cascade is test data, and service-contract cascade is a held-out mechanism.
- **Correct budget semantics:** the official limit is 15 model turns. Read
  calls do not consume a mutation budget. v0.5 exposes no `finish()` tool:
  feasible tasks are scored from the resulting environment state.
- **Optimization gap:** reports now include
  `Goal Pass - Optimal Pass`, exposing agents that complete the goal but
  choose a dominated repair scope.

## Scientific target

Every model starts from the same authoritative failure boundary. It receives:

1. the customer request;
2. the public trace of successful earlier operations;
3. the latest failed tool result;
4. executable domain tools.

It does **not** receive evaluator constraints, the objective tuple, global
loss totals, optimal scopes, or an answer trajectory. It must query the
environment and mutate persistent state. This controlled track isolates
post-commit repair-scope selection; it does not claim to score pre-failure
planning quality.

## Objective and metrics

Hard constraints are checked first. Among goal-satisfying terminal states, the
oracle minimizes:

```text
(recovery_loss,
 lifecycle_cost,
 mutated_prior_commitments,
 state_changing_actions)
```

`recovery_loss` is computed from auditable transactions:

```text
unrefunded cancelled value
+ wasted recovery purchases
+ positive in-place modification cash
+ triggered linked settlement charges
```

All exact ties are accepted. Primary reports contain Goal Pass@1/Pass^5,
Optimal Pass@1/Pass^5, Scope-Optimization Gap, extra loss, financial regret,
scope distance, over-repair, under-repair, and tool errors.

## Challenge-set design

| Family | Persistent prefix | Failed operation | Counterfactual scope flip |
|---|---|---|---|
| Shanghai conference | flights, hotel, transfer, pass | dinner sold out | keep hotel vs replace hotel and settle a package term |
| Radiology workstation | laptop, monitor, key, warranty, software | dock rejected | add universal dock vs replace laptop, warranty, and software |
| Clinic cold chain | freezer, sensor, gateway, service, installation | battery out of stock | add legacy battery vs replace freezer and service contract |

Each A/B counterfactual changes one decisive availability or compatibility
fact. The public failure message stays the same while the oracle-optimal scope
changes.

Quality gates reject a loss-aware task unless it has at least:

- 100 raw candidate plans;
- 8 goal-satisfying plans;
- 4 feasible repair-scope patterns;
- 3 recovery-loss levels.

Actual checked-in tasks exceed these minima.

## Install, validate, and test

```bash
python -m pip install -e .
python scripts/build_pilot.py
python scripts/build_challenge.py
repairscope validate data/pilot
repairscope validate data/challenge
python -m unittest discover -s tests -v
repairscope run-baselines data/challenge
```

Challenge regression results:

| Baseline | Goal Pass | Optimal Pass |
|---|---:|---:|
| No repair | 0 / 12 | 0 / 12 |
| Repair only failed slot | 0 / 12 | 0 / 12 |
| Dependency-declared repair | 0 / 12 | 0 / 12 |
| Full rollback and rebuild | 12 / 12 | 0 / 12 |
| Globally cheapest valid final state | 12 / 12 | 6 / 12 |
| Loss-aware exhaustive oracle | 12 / 12 | 12 / 12 |

This is the intended diagnostic separation: a strategy can complete every
task and still fail every repair-scope judgment.

## Run current models

The harness supports OpenAI Responses, Anthropic Messages, and
OpenAI-compatible Chat Completions for Qwen, DeepSeek, and gateways. API keys
are read from environment variables and are never written to task logs.

```bash
repairscope run-suite data/challenge --provider openai \
  --model YOUR_MODEL_ID --output-dir results/openai

repairscope run-suite data/challenge --provider anthropic \
  --model YOUR_MODEL_ID --output-dir results/anthropic

repairscope run-suite data/challenge --provider deepseek \
  --model YOUR_MODEL_ID --output-dir results/deepseek

repairscope run-suite data/challenge --provider openai-compatible \
  --model YOUR_MODEL_ID --base-url https://gateway.example/v1 \
  --output-dir results/gateway
```

The official protocol uses five independent runs per task and at most 15
model turns per run. A single run is only a smoke test.

## Repository layout

```text
data/pilot/                    v0.4 protocol pilot
data/challenge/                v0.5 paired challenge tasks
data/gold/                     evaluator-only solver output
scripts/build_pilot.py         deterministic pilot generator
scripts/build_challenge.py     deterministic challenge generator
src/repairscope_bench/         environment, oracle, evaluator, runner
tests/                         accounting, data, provider, and runner tests
docs/                          protocol and research documentation
```

## Honest scope

The contribution is not “the first partial rollback.” Compensation and
partial recovery predate language agents. The defensible contribution is an
executable, controlled evaluation of **post-commit repair-scope selection
under hard goals and objective additional losses**.

The current challenge set proves the mechanism and evaluation separation, but
a conference submission still needs more independently authored domains,
larger hidden test sets, second-oracle verification, and broad model results.
