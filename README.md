# RepairScope-Bench

**When a tool-using agent is blocked after creating real commitments, can it
finish the task without choosing an economically dominated repair scope?**

RepairScope-Bench v0.6 is a fixed-failure-state benchmark for post-commit
agent recovery. Flights, hotels, orders, warranties, and service contracts
are first created through executable tools and persisted in a STATE-Bench
domain database. A builder then injects one changed fact, executes a failing
operation, and hashes the resulting snapshot. Every model starts from an
independent copy of that same state.

The model is not told which records to keep, cancel, or replace. It sees only
the natural customer request, a compact trace of successful earlier tool
activity, the latest failure, and ordinary domain tools for inspecting and
changing the state.

[中文说明](README.zh-CN.md) · [Data card](docs/DATA_CARD.md) ·
[Evaluation](docs/EVALUATION.md) · [Research story](docs/RESEARCH_STORY.md) ·
[Provider setup](docs/PROVIDERS.md)

## What is new in v0.6

- **Real stateful foundations.** Travel tasks instantiate STATE-Bench's
  `TravelEnvironment`; purchase tasks instantiate its
  `CustomerSupportEnvironment`. The dependency is pinned to commit
  `4efcbf2d4fe60df04878859b692d9391f3d5b33a`.
- **Verifiable failure boundaries.** Every prior commitment is traceable to a
  successful write-tool result. The final pre-evaluation operation really
  fails, and the serialized state, event log, and transaction ledger are
  replay-checked.
- **No answer-leaking cost tool.** Agents must combine item-level orders,
  refund previews, compatibility facts, and contract terms. There is no
  global cost summary, hidden loss field, benchmark `finish()` action, or
  mutation budget.
- **Objective multi-criteria scoring.** Hard goals are checked first.
  Goal-satisfying outcomes are accepted iff no feasible repair is no worse in
  both irreversible loss and net recovery outlay and strictly better in at
  least one. No subjective utility weights are used.
- **Counterfactual scope flips.** Each family has four variants. One refund
  fact or one bundle/licence term changes while the operational state remains
  the same, causing the Pareto-optimal repair scope to flip.
- **Two independent gold checks.** A bounded semantic state search and a
  separately implemented candidate-scope enumerator must agree before a task
  is released.

## Dataset

The default set contains 24 independently materialized failure snapshots:

| Domain | Family | Already committed | Failed operation |
|---|---|---|---|
| Travel | Shanghai conference dinner | flight, hotel, transfer, conference pass | restaurant booking |
| Travel | destination-linked ground plan | changed flight, hotel, ground transport, pass | replacement hotel |
| Travel | shortened trip | flight, hotel, rental car, event pass | date-aligned replacement |
| Customer support | radiology workstation | computer, monitor, warranty, software | dock purchase |
| Customer support | clinic cold chain | freezer, sensor, gateway, service, installation | battery purchase |
| Customer support | media production kit | camera, storage, lens, protection, software | accessory purchase |

Each family has `refund-low`, `refund-full`, `penalty-none`, and
`penalty-high` variants. Every task has three executable semantic recovery
scopes, including local repair and non-local replacement. At least one
goal-satisfying scope is economically dominated.

This is a controlled recovery-stage benchmark. It deliberately does not score
planning before the failure boundary.

## Economic criterion

For every feasible terminal state:

```text
irreversible_loss =
    cancellation and modification fees
  + non-refundable value
  + rebate or licence clawbacks
  + wasted recovery purchases

net_recovery_outlay =
    post-boundary charges
  + fees and settlements
  - post-boundary refunds and compensation
```

Outcome A dominates B iff A is no worse on both values and strictly better on
at least one. All non-dominated outcomes are accepted. The number of changed
commitments and tool calls are diagnostic only.

Primary metrics are:

- Goal Pass@1 and Goal Pass^5;
- Non-Dominated Repair Pass@1 and Pass^5;
- Dominated Repair Rate;
- irreversible-loss and net-outlay regret;
- over-repair, under-repair, tool errors, and turn exhaustion.

If a model reaches a feasible outcome better than the computed frontier, the
run is marked `oracle_violation`, is not penalized, and is excluded from the
official aggregate.

## Install and verify

Python 3.12 or later and Git are required because STATE-Bench is installed
from the pinned Git revision.

```bash
python -m pip install -e .
python scripts/build_v06.py
repairscope validate data/v06
repairscope run-baselines data/v06
python -m unittest discover -s tests -v
```

The checked-in v0.6 data currently yields:

| Baseline | Goal Pass | Non-Dominated Repair Pass |
|---|---:|---:|
| No repair | 0 / 24 | 0 / 24 |
| Repair only the failed part | 24 / 24 | 12 / 24 |
| Dependency-closure repair | 24 / 24 | 12 / 24 |
| Full rollback | 24 / 24 | 0 / 24 |
| Choose by final sticker price | 24 / 24 | 12 / 24 |
| Choose by gross refund only | 24 / 24 | 0 / 24 |
| Pareto oracle | 24 / 24 | 24 / 24 |

The separation is intentional: completing the customer's task does not prove
that the agent chose a defensible recovery scope.

## Run models

```bash
repairscope run-suite data/v06 --provider openai \
  --model YOUR_MODEL_ID --repeats 5 --output-dir results/openai

repairscope run-suite data/v06 --provider anthropic \
  --model YOUR_MODEL_ID --repeats 5 --output-dir results/anthropic

repairscope run-suite data/v06 --provider qwen \
  --model YOUR_MODEL_ID --repeats 5 --output-dir results/qwen

repairscope run-suite data/v06 --provider deepseek \
  --model YOUR_MODEL_ID --repeats 5 --output-dir results/deepseek
```

The task-level limit is 15 model turns. If a larger CLI value is supplied,
v0.6 still enforces the task limit. A model may stop naturally; scoring uses
the terminal database state and does not depend on emitting `finish()`.

## Repository layout

```text
data/v06/                     public v0.6 tasks and failure snapshots
data/gold/v06.json            evaluator-only Pareto frontiers and replays
data/legacy/v0.5/             archived v0.4/v0.5 data and gold
scripts/build_v06.py          deterministic failure-boundary builder
src/repairscope_bench/        adapters, DSL, oracle, evaluator, and harness
tests/                        unit, integration, replay, and protocol tests
docs/                         data, evaluation, and research documentation
```

## Claim boundary

The contribution is not the first proposal for partial rollback. It is an
executable evaluation of whether language agents, faced with real persisted
commitments and auditable economic consequences, complete a task using a
repair scope that is not objectively dominated by another feasible repair.
